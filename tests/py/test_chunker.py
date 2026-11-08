"""Chunker unit tests — fact snippets stay welded to their section header."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[2].as_posix())
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ingestion.chunk import CHUNK_SIZE, chunk_sections, build_chunk_records  # noqa: E402

SECTIONS = [
    {"title": "Fund Highlights", "text": "Expense ratio: 1.09% which is the scheme's annual charge.\n" * 30},
    {"title": "Fund house", "text": "The HDFC Mutual Fund house manages this scheme with a long track record."},
    {"title": "Investment Objective",
     "text": ("The scheme seeks to provide long-term capital appreciation by "
              "investing predominantly in Large-Cap companies with strong fundamentals. ") * 6},
]


def test_long_section_produces_multiple_chunks_all_carrying_header():
    chunks = chunk_sections(SECTIONS)
    highlights = [c for c in chunks if c["section"] == "Fund Highlights"]
    assert len(highlights) >= 2, "long fact section should split"
    for c in highlights:
        assert c["text"].startswith("Expense ratio:"), "fact table text must survive splitting"


def test_chunks_respect_size_limit():
    chunks = chunk_sections(SECTIONS)
    for c in chunks:
        assert len(c["text"]) <= CHUNK_SIZE + 20, f"chunk too long: {len(c['text'])}"


def test_chunk_records_carry_full_metadata():
    page = {"slug": "hdfc-large-cap-fund-direct-growth",
            "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            "name": "HDFC Large Cap Fund Direct Growth",
            "page_type": "scheme", "fetched_at": "2026-11-08T10:00:00+00:00"}
    records = build_chunk_records(page, SECTIONS)
    assert records
    for r in records:
        md = r["metadata"]
        assert md["url"] == page["url"] and md["page_type"] == "scheme"
        assert md["scheme_name"] == "HDFC Large Cap Fund Direct Growth"
        assert md["scraped_at"] == page["fetched_at"]
        assert md["section"] in {s["title"] for s in SECTIONS}
        assert r["id"].startswith("hdfc-large-cap-fund-direct-growth::")


def test_single_small_chunk_not_duplicated():
    chunks = chunk_sections([SECTIONS[1]])
    assert len(chunks) == 1
    assert chunks[0]["text"] == SECTIONS[1]["text"]
