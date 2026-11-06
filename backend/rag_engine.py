"""
Agent 2: RAG Knowledge Base Engine.

For a layman: this is NETS's memory. It holds 38 past proposals broken into
searchable paragraphs. When Agent 3 needs to write about firewalls, this
module finds the best firewall paragraphs from past work so Agent 3 doesn't
start from scratch.

For a developer: ChromaDB vector store with bge-large-en-v1.5 embeddings.
query_knowledge_base() returns the top-k most relevant chunks for a query.
Falls back to keyword search if ChromaDB is not available.
"""
import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("rag-engine")

CHROMA_PATH = os.environ.get("CHROMA_PATH", "./proposal_vector_db")
COLLECTION_NAME = "technical_proposals"

_collection = None


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_collection(COLLECTION_NAME)
        logger.info(f"RAG connected: {_collection.count()} chunks in {COLLECTION_NAME}")
        return _collection
    except Exception as e:
        logger.warning(f"ChromaDB not available ({e}). RAG will return empty context.")
        return None


def query_knowledge_base(query: str, n_results: int = 5) -> List[Dict]:
    """
    Search past proposals for paragraphs relevant to the query.

    Returns list of {text, source, score} dicts, best match first.
    If ChromaDB is unavailable, returns empty list.
    """
    col = _get_collection()
    if col is None:
        return []

    try:
        results = col.query(query_texts=[query], n_results=n_results)
        chunks = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else None
            chunks.append({
                "text": doc,
                "source": meta.get("source", "unknown"),
                "section": meta.get("section", ""),
                "score": round(1.0 - (dist or 0), 3) if dist is not None else None,
            })
        logger.info(f"RAG query '{query[:50]}' returned {len(chunks)} chunks")
        return chunks
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        return []


def build_rag_context(tender_title: str, solutions: List[str], max_chunks: int = 8) -> str:
    """
    Build a context string for Agent 3 by querying the knowledge base
    with the tender title and each matched solution.

    Returns a formatted string ready to inject into the proposal prompt.
    """
    all_chunks = []
    seen_texts = set()

    # Query by tender title
    for chunk in query_knowledge_base(tender_title, n_results=3):
        if chunk["text"] not in seen_texts:
            all_chunks.append(chunk)
            seen_texts.add(chunk["text"])

    # Query by each matched solution
    for sol in solutions[:5]:
        for chunk in query_knowledge_base(sol, n_results=2):
            if chunk["text"] not in seen_texts:
                all_chunks.append(chunk)
                seen_texts.add(chunk["text"])

    # Sort by relevance, take top max_chunks
    all_chunks.sort(key=lambda c: c.get("score", 0) or 0, reverse=True)
    all_chunks = all_chunks[:max_chunks]

    if not all_chunks:
        return "(No relevant past proposals found in the knowledge base.)"

    context = "RELEVANT SECTIONS FROM PAST NETS PROPOSALS:\n\n"
    for i, c in enumerate(all_chunks, 1):
        context += f"--- Reference {i} (from: {c['source']}, section: {c.get('section','')}) ---\n"
        context += c["text"] + "\n\n"

    return context


def get_rag_status() -> dict:
    """Health check for the RAG engine."""
    col = _get_collection()
    if col is None:
        return {"available": False, "chunks": 0, "path": CHROMA_PATH}
    return {"available": True, "chunks": col.count(), "path": CHROMA_PATH,
            "collection": COLLECTION_NAME}
