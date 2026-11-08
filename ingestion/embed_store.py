"""Embeddings + Chroma storage (ARCHITECTURE §5.4).

Embedding model (fixed by the problem statement, cross-cutting rule #3):
  sentence-transformers/all-MiniLM-L6-v2 via the official ONNX export,
  loaded through fastembed (no torch). The TS side uses the same export via
  @huggingface/transformers at query time.

Chroma collection: mf_faq, cosine space.
CHROMA_MODE=local  -> embedded PersistentClient at ./data/chroma (dev default)
CHROMA_MODE=cloud  -> Chroma Cloud (tenant/database/api key via env)
"""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
from fastembed import TextEmbedding

COLLECTION_NAME = "mf_faq"
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # fastembed's name for onnx/all-MiniLM-L6-v2

_EMB_MODEL_SINGLETON: TextEmbedding | None = None


def get_embedder() -> TextEmbedding:
    """Shared instance — identical model & normalization for docs and queries."""
    global _EMB_MODEL_SINGLETON
    if _EMB_MODEL_SINGLETON is None:
        _EMB_MODEL_SINGLETON = TextEmbedding(model_name=EMB_MODEL)
    return _EMB_MODEL_SINGLETON


def embed(texts: list[str]) -> list[list[float]]:
    """fastembed returns cosine-normalized vectors by default."""
    emb = get_embedder()
    return [v.tolist() for v in emb.embed(texts)]


def get_chroma_client() -> chromadb.ClientAPI:
    mode = os.environ.get("CHROMA_MODE", "local").lower()
    if mode == "local":
        return chromadb.PersistentClient(path=str(Path("data/chroma")))
    if mode == "cloud":
        api_key = os.environ["CHROMA_API_KEY"]
        tenant = os.environ["CHROMA_TENANT"]
        database = os.environ["CHROMA_DATABASE"]
        try:
            return chromadb.CloudClient(token=api_key, tenant=tenant, database=database)
        except AttributeError:  # older chromadb without CloudClient
            return chromadb.HttpClient(
                host="api.trychroma.com",
                port=443,
                ssl=True,
                headers={"Authorization": f"Bearer {api_key}",
                         "X-Chroma-Tenant": tenant, "X-Chroma-Database": database},
                tenant=tenant, database=database,
            )
    raise ValueError(f"Unknown CHROMA_MODE: {mode}")


def new_collection(client: chromadb.ClientAPI):
    """Idempotent rebuild path: delete + recreate with cosine space."""
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # first run / already absent
    return client.create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(records: list[dict]) -> int:
    """Embed + add chunk records into a freshly created mf_faq collection."""
    if not records:
        return 0
    client = get_chroma_client()
    coll = new_collection(client)
    ids = [r["id"] for r in records]
    docs = [r["text"] for r in records]
    metas = [r["metadata"] for r in records]
    vecs = embed(docs)

    # chroma caps batch sizes; add in slices of 500
    B = 500
    for i in range(0, len(ids), B):
        coll.add(ids=ids[i:i + B], embeddings=vecs[i:i + B],
                 documents=docs[i:i + B], metadatas=metas[i:i + B])
    print(f"[embed_store] added {len(ids)} chunks to collection {COLLECTION_NAME!r}")
    return len(ids)


def collection_stats() -> dict:
    client = get_chroma_client()
    coll = client.get_collection(COLLECTION_NAME)
    peek_size = coll.count()
    return {"collection": COLLECTION_NAME, "count": peek_size}
