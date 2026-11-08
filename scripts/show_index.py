"""Local ChromaDB inspector — view what's stored in mf_faq.

Usage (set CHROMA_MODE, default local; add --cloud to use cloud creds):
  python -m scripts.show_index                      # stats + per-page counts
  python -m scripts.show_index --page large-cap     # chunks matching slug/url substring
  python -m scripts.show_index --id hdfc-large-cap-fund-direct-growth::000
  python -m scripts.show_index --query "expense ratio of HDFC Large Cap" --k 5
  python -m scripts.show_index --text               # press-through full text
  python -m scripts.show_index --vector             # show embedding vector (first dims)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ingestion.embed_store import COLLECTION_NAME, embed, get_chroma_client  # noqa: E402


def fmt_chunk(chunk_id, meta, doc, dist=None, vec=None, full=False) -> str:
    parts = [f"[{chunk_id}] cos={1 - dist:.4f}" if dist is not None else f"[{chunk_id}]"]
    if meta:
        parts.append(f"{meta.get('scheme_name')} | section={meta.get('section')} "
                     f"| chunk {meta.get('chunk_index')} | scraped {meta.get('scraped_at')}")
    parts.append(doc if full else doc[:160].replace("\n", " / "))
    if vec is not None:
        v = vec if not hasattr(vec, "tolist") else vec.tolist()
        parts.append(f"emb[{len(v)}d] first5={v[:5]}")
    out = "\n".join("  " + p for p in parts if p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", help="substring filter on chunk ID (slug) or url")
    ap.add_argument("--id", help="exact chunk ID")
    ap.add_argument("--query", help="embed this text and show top-k")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--full", action="store_true", help="print full text")
    ap.add_argument("--vector", action="store_true", help="print embedding vectors")
    args = ap.parse_args()

    client = get_chroma_client()
    coll = client.get_collection(COLLECTION_NAME)
    n = coll.count()
    print(f"collection: {COLLECTION_NAME!r} | mode={__import__('os').environ.get('CHROMA_MODE', 'local')} | count={n}")

    # per-page counts
    per = {}
    res = coll.get(include=["metadatas"])
    for m in res["metadatas"]:
        per[m["url"]] = per.get(m["url"], 0) + 1
    for url, c in sorted(per.items()):
        print(f"  {c:^4} chunks | {url}")
    print()

    if args.id:
        r = coll.get(ids=[args.id], include=["metadatas", "documents", "embeddings"])
        if not r["ids"]:
            print(f"no chunk with id {args.id}")
            return
        vec = r["embeddings"][0] if args.vector else None
        print(fmt_chunk(r["ids"][0], r["metadatas"][0], r["documents"][0], vec=vec, full=True))
        return

    if args.page:
        fin = {"$or": [{"url": {"$contains": args.page}}, {"scheme_name": {"$contains": args.page}}]}
        matched = [cid for cid, m in zip(res["ids"], res["metadatas"])
                   if args.page.lower() in cid.lower() or args.page.lower() in m["url"].lower()]
        if not matched:
            print(f"no chunks match page filter: {args.page}")
            return
        sel = {"ids": matched}
        for chunk_id in matched if args.full else matched[:8]:
            rr = coll.get(ids=[chunk_id], include=["metadatas", "documents"], limit=1)
            vec = rr["embeddings"][0] if args.vector else None
            print(fmt_chunk(rr["ids"][0], rr["metadatas"][0], rr["documents"][0],
                            vec=vec, full=args.full))
        if not args.full:
            print(f"  (… {len(matched) - 8} more; --full prints all with complete text)")
        return

    if args.query:
        vec = embed([args.query])[0]
        r = coll.query(query_embeddings=[vec], n_results=args.k,
                       include=["documents", "metadatas", "distances", "embeddings" if args.vector else "documents"])
        for i in range(len(r["ids"][0])):
            v = r["embeddings"][0][i] if args.vector and "embeddings" in r else None
            print(fmt_chunk(r["ids"][0][i], r["metadatas"][0][i], r["documents"][0][i],
                            dist=r["distances"][0][i], vec=v, full=args.full))
        return

    # default: show first few chunks
    for i in range(min(5, n)):
        rr = coll.get(ids=[res["ids"][i]], include=["metadatas", "documents"])
        print(fmt_chunk(rr["ids"][0], rr["metadatas"][0], rr["documents"][0]))
    print("  (… use --page/--id/--query for targeted views)")


if __name__ == "__main__":
    main()
