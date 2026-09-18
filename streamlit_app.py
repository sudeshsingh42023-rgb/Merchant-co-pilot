"""
Chat UI for the Merchant Co-Pilot.
Run: streamlit run streamlit_app.py
(requires app/main.py running on :8000 and rag/ingest.py already run once)
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "agents"))

import streamlit as st
from graph import build_graph

st.set_page_config(page_title="Merchant Co-Pilot", page_icon="🛍️")
st.title("🛍️ Merchant Co-Pilot")
st.caption("Multi-agent store assistant — inventory, reporting, content, support (LangGraph)")

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    with st.chat_message("user" if role == "human" else "assistant"):
        st.write(content)

prompt = st.chat_input("e.g. 'Why did sales drop last week?' or 'Restock SKU-1042 to 50'")
if prompt:
    st.session_state.history.append(("human", prompt))
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            result = st.session_state.graph.invoke({
                "messages": st.session_state.history,
                "route": "",
                "needs_confirmation": False,
            })
            reply = result["messages"][-1].content
            st.write(reply)
            st.caption(f"routed to: **{result['route']}** agent")

    st.session_state.history = [(m.type, m.content) for m in result["messages"]]
