"""Phase 1: fetch exactly the 5 whitelisted Groww pages, persist raw + clean text.

Implements FR1 / ARCHITECTURE §5.1. Single polite pass per URL, one retry on
transient failure, robots.txt honored. No link-following — the whitelist in
config/sources.py is the entire crawl frontier.

End-to-end pass also:
  - cleans each page into sections (ingestion/clean.py) -> {slug}.txt + {slug}.sections.json
  - writes data/raw/manifest.json
  - regenerates data/sources.csv + data/sources.md (deliverable D2)

Run: python -m ingestion.scrape
"""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.robotparser
from pathlib import Path

import requests

from config.sources import SOURCE_PAGES, SourcePage
from ingestion.clean import build_document
from ingestion.make_sources import generate_source_lists

DATA_RAW = Path("data/raw")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT_S = 30


def allowed_by_robots(url: str) -> bool:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url("https://groww.in/robots.txt")
    try:
        rp.read()
    except Exception as exc:  # pragma: no cover - network edge
        print(f"[robots] could not read robots.txt ({exc}); assuming NOT allowed")
        return False
    return rp.can_fetch(UA, url)


def fetch(url: str) -> tuple[str, int]:
    """Fetch once; retry once on transient failures. Returns (html, status)."""
    last_err = ""
    for attempt in (1, 2):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT_S)
            if r.status_code == 200:
                return r.text, 200
            last_err = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last_err = str(exc)
        if attempt == 1:
            time.sleep(2)
    return "", 0 if not last_err.startswith("HTTP") else -1


FACT_MARKERS: dict[str, list[str]] = {
    # substring, case-insensitive, that must appear in the cleaned text
    # (Phase 1 exit gate: facts visibly present in extracted text)
    # Note: the literal word "Riskometer" only exists in Groww's embedded JSON;
    # the visible page states the risk level (e.g. "rated Very High risk"),
    # which satisfies the riskometer fact. Gate uses "high risk".
    "amc-hdfc-mutual-funds": ["fund", "amc", "hdfc"],
    "hdfc-large-cap-fund-direct-growth": [
        "expense ratio", "exit load", "minimum sip", "benchmark", "high risk",
    ],
    "hdfc-equity-fund-direct-growth": [
        "expense ratio", "exit load", "minimum sip", "benchmark", "high risk",
    ],
    "hdfc-elss-tax-saver-fund-direct-plan-growth": [
        "expense ratio", "exit load", "minimum sip", "benchmark", "high risk", "lock-in",
    ],
    "hdfc-mid-cap-fund-direct-growth": [
        "expense ratio", "exit load", "minimum sip", "benchmark", "high risk",
    ],
}


def fact_check(slug: str, text: str) -> dict[str, bool]:
    low = text.lower()
    return {kw: kw in low for kw in FACT_MARKERS.get(slug, [])}


def scrape_page(page: SourcePage) -> dict:
    html, status = "", 0
    if not allowed_by_robots(page.url):
        status = -100  # robots disallowed
    else:
        html, status = fetch(page.url)

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    entry: dict = {
        "url": page.url,
        "slug": page.slug,
        "name": page.name,
        "page_type": page.page_type,
        "fetched_at": fetched_at,
        "status": status,
    }
    if status != 200:
        entry["error"] = f"fetch failed (status={status})"
        print(f"[FAIL] {page.slug}: {entry['error']}")
        return entry

    title, flat_text, sections = build_document(html)
    (DATA_RAW / f"{page.slug}.html").write_text(html, encoding="utf-8")
    (DATA_RAW / f"{page.slug}.txt").write_text(flat_text, encoding="utf-8")
    (DATA_RAW / f"{page.slug}.sections.json").write_text(
        json.dumps({"title": title, "sections": sections}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    entry.update(
        bytes=len(html.encode("utf-8")),
        chars=len(flat_text),
        title=title,
        sections=len(sections),
    )
    checks = fact_check(page.slug, flat_text)
    entry["fact_check"] = checks
    missing = [k for k, ok in checks.items() if not ok]
    entry["facts_ok"] = not missing
    mark = "OK  " if not missing else f"MISSING {missing}"
    print(f"[{mark}] {page.slug}: {len(sections)} sections, {len(flat_text)} chars")
    return entry


def run() -> None:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for i, page in enumerate(SOURCE_PAGES):
        print(f"[{i + 1}/{len(SOURCE_PAGES)}] {page.url}")
        manifest.append(scrape_page(page))
        if i < len(SOURCE_PAGES) - 1:
            time.sleep(2)  # polite spacing

    (DATA_RAW / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok = sum(1 for e in manifest if e.get("facts_ok"))
    facts_missing = [e["slug"] for e in manifest if e.get("status") == 200 and not e.get("facts_ok")]
    print(f"\nDone: {ok}/{len(SOURCE_PAGES)} pages with all fact markers present.")
    if facts_missing:
        print(f"FACT GATE FAILURE — fix extraction before Phase 2 for: {facts_missing}")


if __name__ == "__main__":
    generate_source_lists  # keep import referenced; D2 regenerated below
    run()
    generate_source_lists()
