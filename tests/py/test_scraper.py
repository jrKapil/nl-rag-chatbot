"""Phase 1 unit tests for clean.py — run against a captured Groww HTML fixture.

No network in tests (fixture copy of data/_probe_largecap.html).
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingestion.clean import build_document, extract_sections  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures_groww_scheme.html"


def _doc(title, text, sections):
    return title, text, sections


def test_title_extracted():
    html = FIXTURE.read_text(encoding="utf-8")
    title, flat, sections = build_document(html)
    assert "HDFC Large Cap Fund" in title
    assert len(sections) >= 3
    # Page Overview section carries the title
    assert sections[0]["title"] == "Page Overview"
    assert "HDFC Large Cap Fund" in sections[0]["text"]


def test_heading_anchored_sections():
    html = FIXTURE.read_text(encoding="utf-8")
    _, _, sections = build_document(html)
    titles = [s["title"].lower() for s in sections]
    # from the structural probe, these headings exist in the DOM
    assert any("fund house" in t for t in titles)
    assert any("investment objective" in t for t in titles)


def test_facts_present_in_flat_text():
    html = FIXTURE.read_text(encoding="utf-8")
    _, flat, _ = build_document(html)
    low = flat.lower()
    for marker in ["expense ratio", "exit load", "minimum sip", "high risk", "benchmark"]:
        assert marker in low, f"missing fact marker: {marker}"


def test_no_script_style_noise():
    html = FIXTURE.read_text(encoding="utf-8")
    _, flat, _ = build_document(html)
    # raw JS must not leak into clean text
    assert "function(" not in flat
    assert "var groundContent" not in flat
    # huge boilerplate markers absent
    assert "__NEXT_DATA__" not in flat
    assert "<div" not in flat


def test_structured_extras_lockin_from_embedded_json():
    """ELSS lock-in renders only in Groww's embedded JSON — enrichment must find it."""
    mini = (
        "<html><head><title>X</title></head><body>"
        "<h3>Fund house</h3><p>HDFC</p>"
        "<script>window.__NUST__={\"scheme\":{\"lock_in\":{\"years\":3,\"months\":0}}}</script>"
        "</body></html>"
    )
    title, flat, sections = build_document(mini)
    assert "lock-in" in flat.lower()
    assert any("lock-in" in s["title"].lower() for s in sections)
    # guard: no lock_in -> no invented section
    title2, flat2, _ = build_document("<html><body><p>no facts</p></body></html>")
    assert "lock-in" not in flat2.lower()


def test_section_text_persistence_roundtrip():
    from ingestion.clean import sections_to_text
    _, _, sections = build_document(FIXTURE.read_text(encoding="utf-8"))
    flat = sections_to_text(sections)
    for s in sections:
        assert s["text"] and s["text"] in flat
