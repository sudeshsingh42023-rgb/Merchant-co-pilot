"""
LangGraph multi-agent supervisor for the Merchant Co-Pilot.

Graph shape:

               ┌──────────────┐
   user msg -> │  supervisor  │ -- routes by intent -->
               └──────────────┘
                      |
       ┌──────────────┼──────────────┬───────────────┐
       v              v              v                v
  inventory_agent reporting_agent content_agent  support_agent
       |
       v
  confirm_risky_action (interrupt) -- only reached if a tool call
       |                              was BLOCKED by the price guardrail
       v
   apply_confirmed_action

Set OPENAI_API_KEY (or swap ChatOpenAI for ChatAnthropic) before running.
"""
import os
from typing import Annotated, Literal, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage

from tools import (
    search_products, update_product_stock, update_product_price,
    get_sales_summary, get_sales_trend, get_dormant_customers,
    retrieve_policy_or_ticket_context,
)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

INVENTORY_TOOLS = [search_products, update_product_stock, update_product_price]
REPORTING_TOOLS = [get_sales_summary, get_sales_trend, get_dormant_customers]
CONTENT_TOOLS = [search_products, get_dormant_customers]
SUPPORT_TOOLS = [retrieve_policy_or_ticket_context, search_products]


class State(TypedDict):
    messages: Annotated[list, add_messages]
    route: str
    needs_confirmation: bool


# ---------- Supervisor: classify intent ----------
def supervisor(state: State) -> dict:
    last_user_msg = state["messages"][-1].content
    routing_prompt = (
        "Classify the merchant's request into exactly one label: "
        "inventory, reporting, content, support. "
        "inventory = stock/price changes or product lookups. "
        "reporting = sales numbers, trends, dormant customers. "
        "content = writing product descriptions, marketing copy, win-back emails. "
        "support = answering a customer question or ticket. "
        f"Request: {last_user_msg}\nReply with only the single label."
    )
    label = llm.invoke(routing_prompt).content.strip().lower()
    if label not in ("inventory", "reporting", "content", "support"):
        label = "support"
    return {"route": label}


def route_decision(state: State) -> Literal["inventory", "reporting", "content", "support"]:
    return state["route"]


# ---------- Specialist agents (each is itself a mini tool-calling loop) ----------
def make_agent_node(system_prompt: str, tools):
    bound_llm = llm.bind_tools(tools)

    def node(state: State) -> dict:
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = bound_llm.invoke(messages)
        return {"messages": [response]}

    return node


inventory_agent = make_agent_node(
    "You are the Inventory Agent for an apparel store. Use tools to look up and "
    "update stock/price. Price changes over 15% will be blocked by a guardrail — "
    "if blocked, tell the merchant clearly and ask them to explicitly confirm "
    "before you retry with confirmed=true.",
    INVENTORY_TOOLS,
)

reporting_agent = make_agent_node(
    "You are the Reporting Agent. Use tools to pull sales summaries, trends, and "
    "dormant-customer lists. When you see a revenue/order dip, say so explicitly "
    "and suggest one concrete next step (e.g. a win-back campaign).",
    REPORTING_TOOLS,
)

content_agent = make_agent_node(
    "You are the Content Agent. Write product descriptions, marketing copy, or "
    "win-back emails. Look up real product/customer data with tools first so "
    "copy is accurate rather than generic.",
    CONTENT_TOOLS,
)

support_agent = make_agent_node(
    "You are the Support Agent. ALWAYS call retrieve_policy_or_ticket_context "
    "before answering a customer question, and ground your answer in what it "
    "returns. Never invent a policy detail that wasn't retrieved.",
    SUPPORT_TOOLS,
)


# ---------- Tool execution nodes (one ToolNode per specialist's toolset) ----------
inventory_tools_node = ToolNode(INVENTORY_TOOLS)
reporting_tools_node = ToolNode(REPORTING_TOOLS)
content_tools_node = ToolNode(CONTENT_TOOLS)
support_tools_node = ToolNode(SUPPORT_TOOLS)


def needs_tools(state: State) -> Literal["tools", "end"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


# ---------- Build graph ----------
def build_graph():
    graph = StateGraph(State)

    graph.add_node("supervisor", supervisor)
    graph.add_node("inventory_agent", inventory_agent)
    graph.add_node("reporting_agent", reporting_agent)
    graph.add_node("content_agent", content_agent)
    graph.add_node("support_agent", support_agent)
    graph.add_node("inventory_tools", inventory_tools_node)
    graph.add_node("reporting_tools", reporting_tools_node)
    graph.add_node("content_tools", content_tools_node)
    graph.add_node("support_tools", support_tools_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", route_decision, {
        "inventory": "inventory_agent",
        "reporting": "reporting_agent",
        "content": "content_agent",
        "support": "support_agent",
    })

    for agent_name, tools_name in [
        ("inventory_agent", "inventory_tools"),
        ("reporting_agent", "reporting_tools"),
        ("content_agent", "content_tools"),
        ("support_agent", "support_tools"),
    ]:
        graph.add_conditional_edges(agent_name, needs_tools, {"tools": tools_name, "end": END})
        graph.add_edge(tools_name, agent_name)  # loop back so the agent can respond to tool output

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()
    print("Merchant Co-Pilot ready. Type a request (or 'quit').\n")
    history = []
    while True:
        user_input = input("merchant> ")
        if user_input.strip().lower() in ("quit", "exit"):
            break
        history.append(("user", user_input))
        result = app.invoke({"messages": history, "route": "", "needs_confirmation": False})
        history = [(m.type, m.content) for m in result["messages"]]
        print("copilot>", result["messages"][-1].content, "\n")
