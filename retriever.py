import os
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")

_vectordb = None


def get_retriever(k: int = 4):
    global _vectordb
    if _vectordb is None:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        _vectordb = Chroma(persist_directory=PERSIST_DIR, embedding_function=embeddings)
    return _vectordb.as_retriever(search_kwargs={"k": k})


def retrieve_context(query: str, k: int = 4) -> str:
    retriever = get_retriever(k)
    docs = retriever.invoke(query)
    return "\n---\n".join(d.page_content for d in docs)
