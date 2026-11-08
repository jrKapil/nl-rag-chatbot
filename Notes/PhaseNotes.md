# Phase Notes — per-phase observations (retrieval tuning + report material)

**Migration 2026-11-08 — Chroma → Pinecone (vector DB swap):**
Chroma Cloud stopped accepting new signups, so the hosted store switched to Pinecone serverless
(free tier), index `mf-faq`, dim 384, cosine metric, AWS us-east-1. All 95 chunk vectors were
reused verbatim from `data/chunks/chunks.jsonl` (baked at ingestion — no re-embedding), giving
bit-identical vectors and retrieval results to the local Chroma index. E2E smoke 6/6 PASS against
Pinecone via `scripts/test_answer.py` (VECTOR_DB=pinecone). Local Chroma (`CHROMA_MODE=local`)
kept intact for dev tooling; `scripts/show_index.py` unchanged.

**Source freshness stamp (FR10)** — added 2026-11-08:
Every answer now carries a deterministic `Last updated from sources: YYYY-MM-DD`
line right after the citation URL, derived from the cited chunk's `scraped_at`
metadata (not generation). Refusals carry no URL and no stamp. `build_context()`
in both `retrieve.py` and `pinecone_store.py` exposes `scraped_at` per hit;
`test_answer.py` appends the stamp and `post_checks` verifies it.

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

## Local E2E LLM test (pre-Phase 3, 2026-11-08) — GROQ ONLINE

**Setup:** `.env.local` (gitignored): `GROQ_API_KEY`, `GROQ_MODEL=qwen/qwen3.8-27b`,
`CHROMA_MODE=local`, `RETRIEVAL_K=4`, `SIM_THRESHOLD=0.35`.
Runner: `python -m scripts.test_answer` (mirrors §6.1 exactly; ad-hoc question via argv).

**Groq gotchas (for report + TS port):**
1. Groq sits behind Cloudflare: requests with python's default User-Agent get
   **HTTP 403 / Cloudflare error 1010** regardless of key validity. Must send a
   browser-like UA. The Next.js server-side fetch sends node/undici UA — verify
   it is NOT blocked during Phase 5; if it is, add UA header there too.
2. `qwen/qwen3.8-27b` is live on the free tier alongside gpt-oss-120b/20b,
   llama-prompt-guard, whisper. NO thinking blocks observed at temp 0.1 —
   `reasoning_len 0` across all runs despite qwen3 family. No strip needed but
   the code keeps the defensive <think>...</think> stripper.
3. Free-tier latency: ~0.2–0.45s end-to-end per answer (local). ~40 completion tokens typical.

**Results — 6/6 PASS (4 fact, 1 advice-refusal, 1 unknown-scheme-refusal):**
| Case | Answer | Verdict |
|---|---|---|
| expense ratio Large Cap | "1.01%" + correct URL | all OK |
| exit load Flexi Cap | "1% if redeemed within 1 year" | all OK |
| ELSS lock-in | "3 years" | all OK |
| Min SIP Mid Cap | "₹100" | all OK |
| advice (ELSS vs Mid Cap) | refusal, no URL | all OK |
| NAV of ICICI fund (out of corpus) | refusal, no URL | all OK |

**Prompt contract locked (Phase 5 must replicate):** grounded-only, ≤3 sentences, final
line = exactly one URL taken from the retrieved chunks' metadata, refusal sentence is bare
(no URL), no advice phrasing. Post-checks verify sentence count + citation whitelist +
context-citation + advice-regex + refusal honesty.

**Known tuning item (Phase 7):** retrieval gate passed the "unknown ICICI" query
(0.5332 > 0.35) — the LLM refusal saved it (defense in depth). Threshold likely rises
to ~0.5–0.6 after the full 10-query eval.

## Phase 4 — Next.js App & UI (FR9) — 2026-11-08 — DONE

- `web/app/page.tsx`: SSR welcome line, 3 example question links, "Facts-only. No investment advice." disclaimer, Chat client-component island
- `web/app/api/ask/route.ts`: stub POST returning fixed `AskEnvelope` (ARCHITECTURE §6.1.8 shape)
- `web/lib/prompts.ts`: SYSTEM_RULES + refusal/returns/not-found templates (Phase 5 consumes as-is)
- `web/lib/envelope.ts`: shared `AnswerType` / `AskEnvelope` types
- `web/app/components/Chat.tsx` + `chat.module.css`: input form, answer display with citation + type badge + "Last updated from sources" stamp
- `web/.env.local.example`: env var reference for Phase 5
- Verified: `npm run build` passes; `npm run dev` serves on :3000; `GET /` renders SSR content; `POST /api/ask` returns stub envelope
- Exit gate met: UI renders, example links populate input via `?q=` navigation, submit calls `/api/ask`, stub envelope renders with citation + type badge

## Phase 5 — next: real retrieval + generation in `web/app/api/ask/route.ts` (Pinecone REST + Groq + prompts.ts)
