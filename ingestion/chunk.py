"""Chunking for ingestion (ARCHITECTURE §5.3).

Shipped strategy: RecursiveCharacterTextSplitter at ~900 chars with 120 overlap,
separators tuned so Groww's section headers stay welded to their facts.

Fallback rule (do not remove): semantic chunking is built ONLY if the Phase 7
recall gate fails (<8/10). Chunking is not otherwise tuned.

Chunks are built per-section (no cross-section chunks) and each chunk's text is
prefixed with its section title so fact context survives into the embedding.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", ". ", " "]


def make_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
        keep_separator=True,
        add_start_index=False,
        strip_whitespace=True,
    )


def chunk_sections(
    sections: list[dict[str, str]],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict[str, str]]:
    """Turn [{title, text}] into per-section chunks.

    Returns [{text, section}] where text begins with the section title so the
    embedding carries fact context (e.g. "Expense ratio" inside the vector).
    """
    splitter = make_splitter() if (chunk_size, chunk_overlap) == (CHUNK_SIZE, CHUNK_OVERLAP) \
        else RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                            separators=SEPARATORS, keep_separator=True,
                                            strip_whitespace=True)
    out: list[dict[str, str]] = []
    for sec in sections:
        title = (sec.get("title") or "Overview").strip()
        body = (sec.get("text") or "").strip()
        if not body:
            continue
        pieces = splitter.split_text(body)
        if not pieces:
            continue
        # single-piece sections: keep as-is (no duplication of the header)
        for i, piece in enumerate(pieces):
            out.append({"text": piece, "section": title, "chunk_index": i})
    return out


def chunk_prefix(page_meta: dict) -> str:
    """Scheme name prefix so fund queries align with the fund's own fact chunks."""
    if page_meta["page_type"] == "scheme":
        return f"{page_meta['name']} — "
    return "HDFC Mutual Fund — "


def build_chunk_records(page_meta: dict, sections: list[dict[str, str]]) -> list[dict]:
    """Full chroma-ready records for one page.

    Metadata per chunk (non-negotiable, ARCHITECTURE §5.4):
    url, scheme_name, page_type, section, chunk_index, scraped_at.
    """
    records: list[dict] = []
    prefix = chunk_prefix(page_meta)
    running_index = 0  # per-page cumulative — Chroma IDs must be unique
    for c in chunk_sections(sections):
        body = c["text"]
        section = c["section"]
        # always carry the section anchor in the text; add scheme name unless
        # the section title already has it
        if section.lower() not in body.lower():
            body = f"{section}: {body}" if not body.lower().startswith(section.lower()) else body
        head = chunk_prefix(page_meta).strip()
        fund_name = f"{head}".rstrip("— ").strip()
        if fund_name.lower() not in section.lower() and fund_name.lower() not in body.lower():
            body = f"{head} {body}"
        records.append(
            {
                "id": f"{page_meta['slug']}::{running_index:03d}",
                "text": body,
                "metadata": {
                    "url": page_meta["url"],
                    "scheme_name": page_meta["name"],
                    "page_type": page_meta["page_type"],
                    "section": c["section"],
                    "chunk_index": running_index,
                    "scraped_at": page_meta["fetched_at"],
                },
            }
        )
        running_index += 1
    return records
