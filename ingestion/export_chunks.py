"""Human-readable + machine-readable export of chunks & embeddings.

Produced on every ingest run:
  data/chunks/chunks.txt     — readable dump (one block per chunk)
  data/chunks/chunks.jsonl   — one JSON line per chunk: id, metadata, text,
                               embedding (384 floats) — fully self-contained.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path("data/chunks")


def write_chunks_txt(records: list[dict], path: Path = OUT_DIR / "chunks.txt") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for r in records:
        m = r["metadata"]
        head = (
            f"== ID      : {r['id']}\n"
            f"== URL     : {m['url']}\n"
            f"== SCHEME  : {m['scheme_name']}\n"
            f"== SECTION : {m['section']} (chunk {m['chunk_index']})\n"
            f"== SCRAPED : {m['scraped_at']}\n"
        )
        blocks.append(head + "\n" + r["text"])
    path.write_text("\n\n" + "=" * 78 + "\n\n".join(blocks), encoding="utf-8")


def write_chunks_jsonl(
    records: list[dict], vectors: list[list[float]],
    path: Path = OUT_DIR / "chunks.jsonl",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r, v in zip(records, vectors):
            f.write(json.dumps({
                "id": r["id"],
                "metadata": r["metadata"],
                "text": r["text"],
                "embedding": v,
            }, ensure_ascii=False) + "\n")


def export_all(records: list[dict], vectors: list[list[float]]) -> None:
    write_chunks_txt(records)
    write_chunks_jsonl(records, vectors)
    print(f"[export] wrote {len(records)} chunks -> {OUT_DIR / 'chunks.txt'} and {OUT_DIR / 'chunks.jsonl'}")
