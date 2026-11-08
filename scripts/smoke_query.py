"""Phase 5-ready smoke query — local retrieval check (Phase 2 exit gate).

Embeds a query with the SAME fastembed model used for ingestion, then queries
the local mf_faq collection. Verifies the correct chunk (known answer) wins.

Run: python -m scripts.smoke_query [query]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("CHROMA_MODE", "local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ingestion.embed_store import embed, get_chroma_client  # noqa: E402

KNOWN_ANSWERS = [
    "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
    "What is the exit load for HDFC Flexi Cap?",
    "What is the lock-in period of HDFC ELSS Tax Saver Fund?",
]
EXPECT_SLUG = ["hdfc-large-cap-fund-direct-growth",
               "hdfc-equity-fund-direct-growth",
               "hdfc-elss-tax-saver-fund-direct-plan-growth"]
EXPECT_TERM = ["expense", "exit load", "lock-in"]


def top_k(query: str, k: int = 4) -> dict:
    client = get_chroma_client()
    coll = client.get_collection("mf_faq")
    vec = embed([query])[0]
    res = coll.query(query_embeddings=[vec], n_results=k,
                     include=["documents", "metadatas", "distances"])
    hits = []
    for i in range(len(res["ids"][0])):
        d = res["distances"][0][i]
        hits.append({
            "id": res["ids"][0][i],
            "cosine": round(1.0 - d, 4),
            "url": res["metadatas"][0][i]["url"],
            "section": res["metadatas"][0][i]["section"],
            "text": res["documents"][0][i][:160],
        })
    return {"query": query, "hits": hits}


def main() -> None:
    queries = [sys.argv[1]] if len(sys.argv) > 1 else KNOWN_ANSWERS
    scores = []
    for q, slug, term in zip(queries, EXPECT_SLUG, EXPECT_TERM):
        r = top_k(q)
        print(f"\nQ: {q}")
        for h in r["hits"]:
            print(f"  cos={h['cosine']:<7} {h['section'][:38]:<40} {h['url'].rsplit('/', 1)[-1]}")
            print(f"        {h['text'][:110]}")
        scores.append([h["cosine"] for h in r["hits"]])
        if len(queries) == len(EXPECT_SLUG):
            ok_slug = slug in r["hits"][0]["url"]
            ok_term = any(term in h["text"].lower() for h in r["hits"])
            print(f"  -> expected page hit: {'OK' if ok_slug else 'MISS'} | term '{term}': {'OK' if ok_term else 'MISS'}")
    flat = [s for row in scores for s in row]
    print(f"\nsimilarity stats (top{k if False else 4}): min={min(flat)} avg={sum(flat)/len(flat):.4f} max={max(flat)}")


if __name__ == "__main__":
    main()
