"""Phase 2 orchestrator: scrape(+optional) -> chunk -> embed -> Chroma.

Commands:
  python -m scripts.ingest                # full: scrape then ingest (FR1+FR2)
  python -m scripts.ingest --no-scrape    # FR12: rebuild index from data/raw/

Idempotent: the collection is deleted and recreated each run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.sources import SOURCE_PAGES
from ingestion.chunk import build_chunk_records
from ingestion.embed_store import collection_stats, upsert_chunks


def load_section_files() -> list[dict]:
    manifest = {m["slug"]: m for m in json.loads(
        (Path("data/raw/manifest.json")).read_text(encoding="utf-8"))}
    pages = []
    for p in SOURCE_PAGES:
        m = manifest.get(p.slug)
        sec_path = Path(f"data/raw/{p.slug}.sections.json")
        if not m or m.get("status") != 200 or not sec_path.exists():
            print(f"[ingest] SKIP {p.slug} (no successful scrape)")
            continue
        data = json.loads(sec_path.read_text(encoding="utf-8"))
        pages.append({"slug": p.slug, "url": p.url, "name": p.name,
                      "page_type": p.page_type, "fetched_at": m["fetched_at"],
                      "sections": data["sections"]})
    return pages


def run(scrape_first: bool) -> None:
    if scrape_first:
        from ingestion.scrape import run as scrape_run
        scrape_run()
    pages = load_section_files()
    if not pages:
        print("[ingest] nothing to ingest — run scrape first")
        return
    records = [r for page in pages for r in build_chunk_records(page, page["sections"])]
    n = upsert_chunks(records)
    print(f"[ingest] pages ingested: {len(pages)} | chunks stored: {n}")
    print(f"[ingest] per page: " + ", ".join(f"{p['slug']}={sum(p['slug'] in r['id'] for r in records)}" for p in pages))


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest 5 whitelisted pages into Chroma")
    ap.add_argument("--no-scrape", action="store_true",
                    help="rebuild index from data/raw/ without refetching (FR12)")
    args = ap.parse_args()
    run(scrape_first=not args.no_scrape)
    print(f"[ingest] collection stats: {collection_stats()}")


if __name__ == "__main__":
    main()
