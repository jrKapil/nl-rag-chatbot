# Phase Notes — per-phase observations (retrieval tuning + report material)

## Phase 2 — Ingestion pipeline (2026-11-08)

**Commands that work:**
- `python -m ingestion.scrape` — full safe pass (fetch + clean + persist + D2)
- `python -m scripts.retext` — rebuild .txt/sections from stored HTML, then re-index
- `python -m scripts.ingest --no-scrape` — FR12 reindex from raw
- `python -m scripts.smoke_query.py` — local retrieval smoke (3 known-answer queries)

**Chunk/embedding exports (updated in same run as ingest):**
- `data/chunks/chunks.txt` — human-readable dump: id, url, scheme, section, metadata + full text
- `data/chunks/chunks.jsonl` — one JSON line per chunk WITH the 384-dim embedding
  (self-contained: full index reproducible from this file alone)

**Inspecting ChromaDB locally:**
- `python -m scripts.show_index` — collection stats + per-page chunk counts + previews
- `python -m scripts.show_index --page large-cap` — filter by slug/scheme substring
- `python -m scripts.show_index --id <slug>::<n> [--vector]` — one chunk, optional embedding
- `python -m scripts.show_index --query "..." --k 5` — embed query + top-k hits w/ cosines
- `--full` prints complete text; add `--cloud` reads CHROMA_* env vars instead of local store


**Index stats (final after tuning):**
- 95 chunks @384 dims; per page: AMC=12, Large Cap=19, Flexi/Equity=22, ELSS=20, Mid Cap=22
- Collection `mf_faq`, cosine space, local mode at `data/chroma/`

**Smoke results (all PASS):**
| Query | #1 chunk | cosine |
|---|---|---|
| expense ratio of HDFC Large Cap | Key facts (Expense ratio 1.01%) | 0.804 |
| exit load for HDFC Flexi Cap | Exit Load (1% within 1 year) | 0.629 |
| lock-in of HDFC ELSS | Lock-in from embedded data (3 years) | 0.888 |
Similarity spread: min 0.593 / avg 0.727 / max 0.888 → initial `SIM_THRESHOLD=0.35` looks safely low; may raise to ~0.5 after Phase 7 full eval.

**Extraction/tuning lessons (report-gold):**
1. Groww serves SSR but site chrome lives in class-named divs (`footer*`, `dropdownUI_*`)
   — semantic `<footer>/<header>` dropping missed ~half the junk. Dropped by class
   token prefix now.
2. The expense/NAV/SIP metric strip (`fundDetails_*`) was drowning inside the
   "Page Overview" section → carved into a dedicated "Key facts" section.
3. AMC page per-fund cards contain ONLY returns → dropped (`Fund Performance` cards,
   PRD no-returns). Tooltip glosses (fee/returns definitions) → dropped.
4. ELSS lock-in + riskometer facts exist only in the page's embedded JSON;
   `structured_extras()` pulls `lock_in.years` from it (visible-DOM fallback absent).
   Visible risk level ("rated Very High risk") instead of literal "Riskometer" word.
5. Every chunk text now carries `scheme_name — Section: body` anchors — that single
   change moved fact chunks from rank 6–10+ to rank 1 (query mentions fund name).

**Where values live on scheme pages (for Phase 5 prompt design):**
- Key facts chunk: NAV, AUM, Expense ratio (current), Min SIP, Rating
- "About …" chunk: launch date, AUM, NAV, risk level, Min SIP, Min Lumpsum, Exit load
- "Exit Load"/"Minimum investments" chunks: dated exit-load history, SIP/Lumpsum mins
