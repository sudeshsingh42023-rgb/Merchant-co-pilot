# Merchant Co-Pilot — Multi-Agent Store Operations Assistant

A LangGraph-orchestrated multi-agent system that lets a store owner run their
shop in natural language: check sales, restock products, get a policy-grounded
answer for a customer, or draft a win-back email — all through one chat box.

Built as a stand-in for how Urumi.AI's agentic layer sits on top of
WooCommerce: a supervisor agent routes requests to specialists, specialists
call tools against a real REST API (here, a mock store; in production,
the WooCommerce REST API), and a guardrail blocks risky actions until a
human confirms.

## Architecture

```
 merchant message
        |
        v
  ┌─────────────┐
  │ supervisor  │  classifies intent -> inventory / reporting / content / support
  └─────────────┘
        |
   ┌────┼────┬────────┬─────────┐
   v         v         v         v
inventory  reporting  content  support
 agent      agent      agent    agent
   |          |          |         |
   v          v          v         v
 tools      tools      tools     tools (+ RAG retrieval)
   |          |          |         |
   └──────────┴──────────┴─────────┘
              |
     mock WooCommerce-style REST API (FastAPI + SQLite)
```

- **Supervisor** (`agents/graph.py`) — one LLM call classifies the request, LangGraph
  routes to the right specialist node.
- **Inventory Agent** — stock/price lookups and updates. Price changes over 15%
  are rejected by the API's guardrail (`app/main.py`) unless explicitly confirmed,
  so the agent can't silently blow up your margins.
- **Reporting Agent** — pulls sales summaries and week-over-week trend data;
  the seed data includes a deliberate 2-week sales dip so it has something
  real to notice and explain.
- **Content Agent** — drafts product descriptions / win-back emails, grounded
  in real product and dormant-customer data rather than generic filler.
- **Support Agent** — always retrieves from a Chroma vector store of store
  policies + past resolved tickets (RAG) before answering, so it can't
  invent a refund window that doesn't exist.

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...          # or swap ChatOpenAI for ChatAnthropic in agents/graph.py

# 1. Start the mock store API
cd app && uvicorn main:app --reload --port 8000

# 2. Seed demo data (products, orders, tickets, policies) — separate terminal
cd app && python seed_data.py

# 3. Embed policies/tickets for RAG — separate terminal
cd .. && python rag/ingest.py

# 4. Run the chat UI
streamlit run streamlit_app.py
# or use the CLI: python agents/graph.py
```

## Example prompts to try

- "What's the sales trend over the last 4 weeks?"
- "Restock product 12 to 80 units"
- "Raise the price of product 5 to ₹6000" (triggers the >15% guardrail if applicable)
- "A customer says their refund never came for order #40 — what's our policy?"
- "Write a win-back email for customers who haven't ordered in 60 days"

## Why this design

Urumi's product is explicitly an "AI Co-pilot" that runs a merchant's day-to-day
store operations with an "Integrity engine" running AI safely in real time.
This project mirrors both halves: multi-agent tool-use over real store data
(LangGraph + LangChain), and a concrete guardrail (the price-change block)
standing in for the integrity/safety layer, with a human-in-the-loop
confirmation step rather than blind autonomy.

## Possible extensions

- Add an `interrupt()` in LangGraph for the confirmation step instead of a
  text-based "ask the merchant to confirm" instruction, so it's a real
  human-in-the-loop pause rather than a convention the LLM has to follow.
- Swap the mock FastAPI backend for the real WooCommerce REST API
  (`wc/v3/products`, `wc/v3/orders`) — tool signatures don't need to change.
- Add a DevOps angle: containerize with Docker Compose (API + Chroma +
  Streamlit), since the JD calls DevOps a plus.
