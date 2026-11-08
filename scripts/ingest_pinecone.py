"""Pinecone ingest (FR2 hosted mode) — zero-re-embedding path + exit gate.

Records are rebuilt identically to the local pipeline; VECTORS are read back
from data/chunks/chunks.jsonl (the export contains final 384-dim embeddings),
so Pinecone receives the exact same vectors Chroma holds — no drift possible.
If any chunk lacks its baked vector, we fall back to live fastembed for that chunk.

Run: python -m scripts.ingest_pinecone
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config.sources import SOURCE_PAGES  # noqa: E402
from ingestion.chunk import build_chunk_records  # noqa: E402
from ingestion.embed_store import embed  # noqa: E402
from ingestion.pinecone_store import ensure_index_ready, query_vec, upsert_chunks  # noqa: E402

CHUNKS_JSONL = Path("data/chunks/chunks.jsonl")

SMOKE = [
    ("What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
     "hdfc-large-cap-fund-direct-growth", "expense"),
    ("What is the exit load for HDFC Flexi Cap?",
     "hdfc-equity-fund-direct-growth", "exit load"),
    ("What is the lock-in period of HDFC ELSS Tax Saver Fund?",
     "hdfc-elss-tax-saver-fund-direct-plan-growth", "lock-in"),
]


def load_section_files() -> list[dict]:
    manifest = {m["slug"]: m for m in json.loads(
        (Path("data/raw/manifest.json")).read_text(encoding="utf-8"))}
    pages = []
    for p in SOURCE_PAGES:
        sec_path = Path(f"data/raw/{p.slug}.sections.json")
        m = manifest.get(p.slug)
        if not m or m.get("status") != 200 or not sec_path.exists():
            print(f"[pinecone-ingest] SKIP {p.slug} (no successful scrape)")
            continue
        data = json.loads(sec_path.read_text(encoding="utf-8"))
        pages.append({"slug": p.slug, "url": p.url, "name": p.name,
                      "page_type": p.page_type, "fetched_at": m["fetched_at"],
                      "sections": data["sections"]})
    return pages


def load_baked_vectors() -> dict[str, list[float]]:
    if not CHUNKS_JSONL.exists():
        print(f"[pinecone-ingest] {CHUNKS_JSONL} not found — will embed fresh")
        return {}
    out = {}
    with CHUNKS_JSONL.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            out[rec["id"]] = rec["embedding"]
    print(f"[pinecone-ingest] loaded {len(out)} baked vectors from {CHUNKS_JSONL}")
    return out


def build_vectors(records: list[dict]) -> list[list[float]]:
    baked = load_baked_vectors()
    missing = [r for r in records if r["id"] not in baked]
    vecs = [baked.get(r["id"]) for r in records]
    if missing:
        print(f"[pinecone-ingest] {len(missing)} chunks lack baked vectors — embedding now")
        fresh = embed([r["text"] for r in missing])
        pos = {r["id"]: i for i, r in enumerate(missing)}
        vecs = [baked[r["id"]] if r["id"] in baked else fresh[pos[r["id"]]] for r in records]
    else:
        vecs = [baked[r["id"]] for r in records]  # type: ignore[index]
    assert all(len(v) == 384 for v in vecs), "dimension drift!"
    return vecs


def smoke(host: str) -> None:
    print("\n--- smoke queries against hosted index ---")
    for q, slug, term in SMOKE:
        vec = embed([q])[0]
        hits = query_vec(vec, 4, host=host)
        ok_slug = slug in (hits[0]["url"] if hits else "")
        ok_term = any(term in h["text"].lower() for h in hits)
        mark = "OK " if (ok_slug and ok_term) else "FAIL"
        print(f"[{mark}] {q}")
        for h in hits:
            print(f"    cos={h['cosine']:.4f} {h['section'][:36]:<38} {h['url'].rsplit('/', 1)[-1]}")


def main() -> None:
    host = ensure_index_ready()
    pages = load_section_files()
    if not pages:
        print("[pinecone-ingest] nothing to ingest — run scrape first")
        return
    records = [r for page in pages for r in build_chunk_records(page, page["sections"])]
    vecs = build_vectors(records)
    n = upsert_chunks(records, vecs, host)
    print(f"[pinecone-ingest] per page: " + ", ".join(
        f"{p['slug']}={sum(p['slug'] in r['id'] for r in records)}" for p in pages))
    expected = sum(len(build_chunk_records(page, page["sections"])) for page in pages)
    parity = "OK" if n == expected == len(records) else "FAIL"
    print(f"[pinecone-ingest] parity: {parity} (built {len(records)}, index {n}, expected {expected})")
    smoke(host)


if __name__ == "__main__":
    main()
