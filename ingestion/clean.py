"""HTML -> clean text, segmented into heading-anchored sections.

Phase 1 (FR1). Used by scrape.py to produce data/raw/{slug}.txt plus a
sections JSON that Phase 2's chunker consumes, and reused by the fact
presence gate.

Implementation notes (from the structural probe):
- Groww pages are server-rendered; the facts live in the visible DOM
  (e.g. `<span>Fund benchmark</span><span>NIFTY 100 Total Return Index</span>`
  inside `investmentObjective_benchmarkRow`).
- Boilerplate we drop: script/style/svg/noscript, nav/footer/header/aside/form.
- Sections are anchored on h1-h6 headings, in document order.
"""

from __future__ import annotations

import html as _html
import re

from bs4 import BeautifulSoup, NavigableString, Tag

DROP_TAGS = (
    "script", "style", "noscript", "svg", "img", "iframe",
    "nav", "footer", "header", "aside", "form",
    "button", "input", "select", "textarea", "template",
)
# Groww doesn't always use semantic <footer>/<header>; huge site chrome is in
# <div class="footerTopSection...">, cookie banners, etc. Drop by class token.
BOILER_CLASS_RE = re.compile(r"^(footer|cookie|breadcrumb|banner|drawer|modal|advert)", re.I)
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

_WS = re.compile(r"[ \t\xa0]+")
_NEWLINES = re.compile(r"\n{3,}")

# Facts that Groww renders only in its embedded page JSON (the visible DOM
# labels hidden CSS/JS chrome). We extract them from the SAME whitelisted
# page's own structured payload — provenance is identical; see PRD §4 note.
_LOCKIN_RE = re.compile(r'"lock_in":\s*\{\s*"years":\s*(\d+)')
_LOCKIN_YRS_RE = re.compile(r'"lock_in_yrs":\s*(\d+)')


def structured_extras(html_doc: str) -> dict[str, str]:
    """Facts from the page's embedded structured data that visible text omits."""
    extras: dict[str, str] = {}
    if not html_doc:
        return extras
    m = _LOCKIN_RE.search(html_doc) or _LOCKIN_YRS_RE.search(html_doc)
    if m:
        years = m.group(1)
        extras["Lock-in (from embedded page data)"] = (
            f"Lock-in period of this fund is {years} year(s) "
            f"(source: official page data on the same Groww page)."
        )
    return extras



def _norm(text: str) -> str:
    """Collapse runs of whitespace (incl. nbsp) and limit blank lines."""
    text = _html.unescape(text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = _WS.sub(" ", text)
    return _NEWLINES.sub("\n\n", text).strip()


def _strip_boilerplate(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    doomed = [
        tag
        for tag in soup.find_all(True)
        if tag.attrs and any(BOILER_CLASS_RE.match(str(c)) for c in (tag.get("class") or []))
    ]
    for tag in doomed:
        tag.decompose()


def extract_sections(html_doc: str) -> tuple[str, list[dict[str, str]]]:
    """Extract page title and heading-anchored sections from raw HTML.

    Returns:
        (title, sections) where sections is an ordered list of
        {"title": <section title>, "text": <section body>}.
    """
    soup = BeautifulSoup(html_doc or "", "lxml")
    # comments are NavigableString subclasses; drop them first
    from bs4 import Comment
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    _strip_boilerplate(soup)

    title = ""
    if soup.h1:
        title = _norm(soup.h1.get_text(" ", strip=True))
    if not title and soup.title:
        title = _norm(soup.title.get_text(" ", strip=True))

    sections: list[dict[str, str]] = []
    if title:
        sections.append({"title": "Page Overview", "text": title})

    body = soup.body if soup.body else soup

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                txt = _norm(str(child))
                if txt:
                    if not sections:
                        sections.append({"title": "Overview", "text": txt})
                    else:
                        sections[-1]["text"] = (sections[-1]["text"] + "\n" + txt).strip()
            elif isinstance(child, Tag):
                if child.name in HEADING_TAGS and child.get_text(strip=True):
                    sections.append(
                        {"title": _norm(child.get_text(" ", strip=True)), "text": ""}
                    )
                else:
                    walk(child)

    walk(body)

    # drop empty / duplicate-title sections, collapse whitespace
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in sections:
        s["text"] = _norm(s.get("text", ""))
        if not s["title"] or not s["text"] or s["title"] in seen:
            continue
        seen.add(s["title"])
        cleaned.append(s)
    return title, cleaned


def sections_to_text(sections: list[dict[str, str]]) -> str:
    """Flatten sections into the single clean-text file we persist."""
    parts = [f"{s['title']}\n{s['text']}" for s in sections]
    return ("\n\n".join(parts).strip()) + "\n"


def build_document(html_doc: str) -> tuple[str, str, list[dict[str, str]]]:
    """Convenience: (title, flat_text, sections)."""
    title, sections = extract_sections(html_doc)

    # enrich with facts present only in the page's embedded JSON
    flat_low = "".join(s["text"].lower() for s in sections)
    for sec_title, sec_text in structured_extras(html_doc).items():
        if sec_title.lower() not in flat_low:
            sections.append({"title": sec_title, "text": sec_text})

    return title, sections_to_text(sections), sections
