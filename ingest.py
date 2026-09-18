"""
Embeds store policies + past support tickets into a local Chroma vector store.
Run once after seeding the DB (or whenever policies/tickets change).

    python rag/ingest.py

The Support Agent queries this at answer-time so it grounds responses in
actual store policy instead of hallucinating a refund window.
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "app"))

import requests
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.docstore.document import Document

API_BASE = "http://localhost:8000"
PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")


def build_documents():
    docs = []

    policies = requests.get(f"{API_BASE}/policies").json()
    for p in policies:
        docs.append(Document(
            page_content=f"POLICY — {p['title']}: {p['content']}",
            metadata={"type": "policy", "title": p["title"]},
        ))

    tickets = requests.get(f"{API_BASE}/tickets/recent", params={"limit": 50}).json()
    for t in tickets:
        docs.append(Document(
            page_content=f"PAST TICKET — Subject: {t['subject']}. "
                          f"Issue: {t['body']}. Resolution: {t['resolution']}",
            metadata={"type": "ticket", "subject": t["subject"]},
        ))

    return docs


def main():
    docs = build_documents()
    print(f"Embedding {len(docs)} documents ({sum(1 for d in docs if d.metadata['type']=='policy')} policies, "
          f"{sum(1 for d in docs if d.metadata['type']=='ticket')} tickets)...")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectordb = Chroma.from_documents(docs, embeddings, persist_directory=PERSIST_DIR)
    vectordb.persist()
    print(f"Persisted vector store to {PERSIST_DIR}")


if __name__ == "__main__":
    main()
