"""Backend-agnostic top-k retrieval (CHROMA local or Pinecone hosted).

Switch: env VECTOR_DB = chroma (default) | pinecone.
Same hit shape for both: {"id", "cosine", "text", "url", "scheme", "section"}.
"""

from __future__ import annotations

import os


def query_top_k(query: str, k: int) -> list[dict]:
    backend = os.environ.get("VECTOR_DB", "chroma").lower()
    if backend == "pinecone":
        from ingestion.pinecone_store import query_top_k as pinecone_top_k
        return pinecone_top_k(query, k)
    if backend == "chroma":
        from ingestion.embed_store import embed, get_chroma_client
        coll = get_chroma_client().get_collection("mf_faq")
        vec = embed([query])[0]
        res = coll.query(query_embeddings=[vec], n_results=k,
                         include=["documents", "metadatas", "distances"])
        hits = []
        for i in range(len(res["ids"][0])):
            md = res["metadatas"][0][i]
            hits.append({
                "id": res["ids"][0][i],
                "cosine": 1.0 - res["distances"][0][i],
                "text": res["documents"][0][i],
                "url": md["url"],
                "scheme": md["scheme_name"],
                "section": md["section"],
            })
        return hits
    raise ValueError(f"Unknown VECTOR_DB backend: {backend}")
