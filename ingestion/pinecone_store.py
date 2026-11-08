"""Pinecone storage backend (ARCHITECTURE §5.4 — Pinecone variant).

Backend switch (2026-11-08): Chroma Cloud stopped accepting new signups, so the
hosted store is now Pinecone serverless. Reason recorded in ARCHITECTURE v1.3
and Notes/PhaseNotes.md. Local Chroma (CHROMA_MODE=local) is kept fully working
for dev tooling; this module never imports chromadb.

Index: PINECONE_INDEX (default mf-faq), serverless AWS us-east-1,
dimension 384, metric cosine — matches fastembed's normalized output exactly.

REST-only (no SDK): the corporate network here blocks pypi.org TLS, and the
TS side will use the same REST paths either way. API version: 2025-04.

Hits mirror the Chroma-side shape so retrieval code is backend-agnostic:
  {"id", "cosine", "text", "url", "scheme", "section"}
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1].as_posix()))

from ingestion.envload import load_env  # noqa: E402  (shared .env.local loader)
from ingestion.embed_store import embed  # noqa: E402  (shared fastembed)

API_BASE = "https://api.pinecone.io"
API_VERSION = "2025-04"
NAMESPACE = ""
DIM = 384
METRIC = "cosine"
_PINECONE_INDEX_SINGLETON: dict = {}  # name -> host cache


def _headers() -> dict:
    load_env()
    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        raise RuntimeError("PINECONE_API_KEY missing (set it in .env.local)")
    return {"Api-Key": key,
            "X-Pinecone-API-Version": API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def index_name() -> str:
    return os.environ.get("PINECONE_INDEX", "mf-faq")


def _describe(name: str) -> dict | None:
    r = requests.get(f"{API_BASE}/indexes/{name}", headers=_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    raise RuntimeError(f"Pinecone describe_index {r.status_code}: {r.text[:300]}")


def ensure_index_ready() -> str:
    """Create the serverless index if absent; return its host when ready."""
    name = index_name()
    info = _describe(name)
    if info is None:
        spec = {
            "name": name,
            "dimension": DIM,
            "metric": METRIC,
            "spec": {
                "serverless": {
                    "region": os.environ.get("PINECONE_REGION", "us-east-1"),
                    "cloud": os.environ.get("PINECONE_CLOUD", "aws"),
                }
            },
        }
        r = requests.post(f"{API_BASE}/indexes", headers=_headers(), json=spec, timeout=60)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Pinecone create_index {r.status_code}: {r.text[:400]}")
        print(f"[pinecone] creating index {name!r} (serverless, dim={DIM}, {METRIC})…")
        info = _describe(name)

    host = info.get("host")
    # wait until ready
    for _ in range(60):
        info = _describe(name) or {}
        if (info.get("status") or {}).get("ready"):
            break
        time.sleep(2)
    print(f"[pinecone] index ready: {name!r} @ {host}")
    _PINECONE_INDEX_SINGLETON[name] = host
    return host


def _data_req(host: str, path: str, payload: dict | None = None) -> dict:
    url = f"https://{host}/{path}"
    r = requests.post(url, headers=_headers(), json=payload or {}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Pinecone {path} {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def delete_all(host: str) -> None:
    try:
        _data_req(host, "vectors/delete", {"deleteAll": True, "namespace": NAMESPACE})
    except RuntimeError as e:
        if "Namespace not found" in str(e):
            return  # empty/fresh namespace — nothing to delete
        raise


def upsert_chunks(records: list[dict], vectors: list[list[float]], host: str) -> int:
    """Wipe + re-add all chunk vectors. Metadata carries text for retrieval."""
    if len(records) != len(vectors):
        raise ValueError("records/vectors length mismatch")
    delete_all(host)
    vectors_data = []
    for r, v in zip(records, vectors):
        meta = dict(r["metadata"])
        meta["text"] = r["text"]
        vectors_data.append({"id": r["id"], "values": v, "metadata": meta})
    B = 100
    for i in range(0, len(vectors_data), B):
        _data_req(host, "vectors/upsert", {"vectors": vectors_data[i:i + B], "namespace": NAMESPACE})
    # verify count — describe_index_stats lags on serverless, so verify by
    # a real query match count instead (authoritative)
    time.sleep(3)
    probe = _data_req(host, "query", {"vector": [0.0] * DIM, "topK": 2000,
                                      "includeMetadata": False, "namespace": NAMESPACE})
    n = len((probe.get("result") or probe).get("matches") or [])
    print(f"[pinecone] upserted {len(records)} vectors -> {index_name()!r}; index matches={n}")
    return n


def count(host: str) -> int:
    return int(_data_req(host, "describe_index_stats").get("total_vector_count", 0))


def _norm_hits(res: dict) -> list[dict]:
    matches = (res.get("result") or res).get("matches") or []
    hits = []
    for m in matches:
        md = dict(m.get("metadata") or {})
        hits.append({
            "id": m.get("id"),
            "cosine": float(m.get("score", 0.0)),
            "text": md.pop("text", ""),
            "url": md.get("url", ""),
            "scheme": md.get("scheme_name", ""),
            "section": md.get("section", ""),
        })
    return hits


def query_vec(vector: list[float], k: int, host: str | None = None) -> list[dict]:
    """Vector query -> hits sorted by cosine similarity (same shape as Chroma path)."""
    host = host or ensure_index_ready()
    body = {"vector": vector, "topK": k, "includeMetadata": True, "namespace": NAMESPACE}
    try:
        res = _data_req(host, "query", body)
        return _norm_hits(res)
    except RuntimeError as e:
        if "not found" in str(e) or "404" in str(e):
            # newer API versions route vector queries through /query/single
            res = _data_req(host, "query/single",
                            {"vector": vector, "topK": k, "includeMetadata": True,
                             "namespace": NAMESPACE})
            return _norm_hits(res)
        raise


def query_top_k(query: str, k: int) -> list[dict]:
    """Embed the query with the fixed ingestion model and fetch top-k."""
    vec = embed([query])[0]
    return query_vec(vec, k)
