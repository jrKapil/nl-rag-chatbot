# Implementation Plan — Mutual Fund FAQ RAG Chatbot

**Version:** 1.0
**Date:** 2026-11-08
**Derived from:** [`Docs/ARCHITECTURE.md`](./ARCHITECTURE.md) v1.2, [`Docs/PRD.md`](./PRD.md) v1.0
**Purpose:** Phase-wise build guide. Each phase has one goal, an unambiguous exit gate, and nothing in later phases depends on skipped work. Work phases strictly in order; do not start a phase until the previous one's exit gate passes.

---

## 0. How to use this document

- Work **top-down**; phases are ordered by dependency, not priority.
- Every phase ends with an **exit gate** — a concrete, testable result. If the gate fails, fix *inside* that phase; do not carry failures forward.
- Each phase lists the architecture sections it implements so you can trace back to *why*.
- `Status` checkboxes are yours to tick as you go.

| Phase | Name | Depends on | Key deliverable |
|---|---|---|---|
| 0 | Repo scaffolding & env | — | runnable skeleton, all creds configured |
| 1 | Scraper & raw data (FR1) | 0 | 5 pages in `data/raw/` + `data/sources.*` (D2) |
| 2 | Ingestion pipeline (FR2, FR12) | 1 | chunks embedded & stored, retrievable locally |
| 3 | Chroma Cloud (FR2 cloud mode) | 2 | `mf_faq` collection live in Chroma Cloud |
| 4 | Next.js app & UI (FR9) | 0 | deployed-looking UI, `/api/ask` stub |
| 5 | Retrieval + generation (FR3–FR5, FR10, FR11) | 3, 4 | end-to-end factual answers on local dev |
| 6 | Guardrails (FR6–FR8) | 5 | refusal paths pass unit tests |
| 7 | Evaluation gate (all FRs) | 6 | PRD §8 set passes ≥8/10 + 3/3 refusals |
| 8 | Deploy to Vercel (D1) | 7 | public prototype link works |
| 9 | Deliverables & polish (D1–D5) | 8 | README, sample Q&A, disclaimer — submission-ready |

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3
   │
   └────────────────► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7 ──► Phase 8 ──► Phase 9
                                     ▲          (3 feeds 5)
```

---

## Phase 0 — Repo Scaffolding & Environment

**Implements:** ARCHITECTURE §7 (config), §10 (repo layout)
**Goal:** Empty-but-correct project skeleton; every secret obtainable and stored correctly; nothing works yet, nothing is missing later.

### Tasks
- [ ] Create repo (git init; `.gitignore` with `data/`, `.env.local`, `node_modules/`, `__pycache__/`, `.venv/`).
- [ ] Create directory skeleton exactly per ARCHITECTURE §10 (`config/`, `data/`, `web/`, `ingestion/`, `scripts/`, `tests/ts/`, `tests/py/`, `Docs/`).
- [ ] Python env: Python 3.11+, `requirements.txt` seeded: `requests`, `beautifulsoup4` (or `trafilatura`), `fastembed`, `chromadb`, `langchain-text-splitters` (or implement plain splitter), `pytest`.
- [ ] Create `config/sources.py`: the 5-URL whitelist, exactly per PRD §4, with `slug`, `name`, `page_type`, and the base URL prefix for validation (§4 diagram). **The whitelist is the source of truth for all URL validation downstream.**
- [ ] Create `.env.local.example` documenting every env var (ARCHITECTURE §7): `GROQ_API_KEY`, `GROQ_MODEL`, `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE`, `CHROMA_MODE`, `RETRIEVAL_K`, `SIM_THRESHOLD`.
- [ ] Obtain credentials now (do not defer): Groq API key (console.groq.com), Chroma Cloud account; record any card-on-file requirement findings in a `Notes/OpenItems.md`.
- [ ] Initialize Next.js app in `web/` (`npx create-next-app@latest web --ts --app`); confirm `npm run dev` serves on :3000.

### Exit gate
- `npm run dev` runs; `python -c "import fastembed, chromadb, requests, bs4"` succeeds; `config/sources.py` imports and contains exactly 5 URLs; secrets exist but only in ignored files.

---

## Phase 1 — Scraper & Raw Data (FR1)

**Implements:** ARCHITECTURE §5.1; traceability FR1.
**Goal:** Exactly 5 Groww pages fetched once, persisted raw + cleaned, and D2 (source list) generated. No pipeline logic yet.

### Tasks
- [ ] `ingestion/scrape.py`: fetch each whitelisted URL using `requests` (`User-Agent` set; single pass; 1 retry on transient failure; honor `robots.txt`).
- [ ] Persist per page: `data/raw/{slug}.html` and `data/raw/{slug}.txt`; write `data/raw/manifest.json` (`url, slug, name, page_type, fetched_at, status`).
- [ ] `ingestion/clean.py`: HTML→text extraction (trafilatura or BS4); strip nav/footer/cookie banners/scripts; **keep fact tables and how-to sections**; segment into sections anchored on headings (produce `{section_title, section_text}` list per page).
- [ ] `ingestion/make_sources.py`: generate `data/sources.csv` and `data/sources.md` from manifest (= **deliverable D2**).
- [ ] `tests/py/test_scraper.py`: unit test clean/segment helpers with a saved HTML fixture (no network in tests).

### Commands
```
python -m ingestion.scrape        # full pass: fetch + clean + persist + sources
```

### Exit gate
- `data/raw/` contains 5 HTML + 5 TXT + `manifest.json`; `data/sources.csv/.md` list exactly the 5 whitelisted URLs; spot-check a `.txt` — expense ratio/exit load numbers are visibly present in the text.
- **Do not proceed** if any fact field (expense ratio, exit load, min SIP, lock-in, benchmark, riskometer) is missing from cleaned text — fix extraction before Phase 2, because embedding quality downstream cannot compensate for missing source text.

---

## Phase 2 — Ingestion Pipeline (FR2, FR12)

**Implements:** ARCHITECTURE §5.2–§5.4; traceability FR2, FR12.
**Goal:** `data/raw/*.txt` → chunks → embeddings → vector store, retrievable locally. This completes the mandated **Data Ingestion stage** (Loading → Chunking → Embedding → Storing).

### Tasks
- [ ] `ingestion/chunk.py`: `RecursiveCharacterTextSplitter`, `chunk_size ≈ 900`, `overlap = 120`, separators `["\n## ", "\n### ", "\n\n", "\n", ". ", " "]` (ARCHITECTURE §5.3). Document the fallback rule in code comments: semantic chunking is built **only if** the Phase 7 recall gate fails.
- [ ] `ingestion/embed_store.py`: embed via `fastembed` model `onnx/all-MiniLM-L6-v2`, normalized; store into Chroma.
- [ ] **Metadata on every chunk (non-negotiable):** `{url, scheme_name, page_type: amc|scheme|faq, section, chunk_index, scraped_at}` (needed for §6.1.8 `updated` field and §6.1.4 best-scheme-URL fallback).
- [ ] Collection `mf_faq`, cosine space. Support `CHROMA_MODE=local` (embedded chromadb at `./data/chroma`) — the default for this phase.
- [ ] `scripts/ingest.py`: an orchestrator with `--no-scrape` flag (rebuild index from `data/raw/` without refetching = **FR12**). Idempotent: delete/recreate collection each run.
- [ ] `tests/py/test_chunker.py`: fact-table snippets stay inside a single chunk and chunk carries the right `section` header.

### Commands
```
python -m scripts.ingest                 # scrape + ingest
python -m scripts.ingest --no-scrape     # FR12: rebuild index from raw
```

### Exit gate
- A tiny standalone script (`scripts/smoke_query.py`, local) embeds a query with the **same** fastembed model and retrieves top-k for: *"What is the expense ratio of HDFC Large Cap Fund Direct Growth?"* — the correct chunk containing the answer appears in results with sane cosine score.
- Record the chunk count and the observed similarity scores; you'll reuse them to sanity-tune `SIM_THRESHOLD` (initial 0.35) in Phase 5/7.
- Report in this phase's summary: total chunks, chunks per page, min/avg/max similarity on 3 known-answer queries.

---

## Phase 3 — Chroma Cloud (FR2 in cloud mode)

**Implements:** ARCHITECTURE §5.4 (cloud), §11 (Chroma notes); prerequisite for §6.1.3.
**Goal:** Same `mf_faq` collection live in Chroma Cloud; the local-first script now targets cloud when `CHROMA_MODE=cloud`.

### Tasks
- [ ] Run the ingest script with `CHROMA_MODE=cloud` + `CHROMA_API_KEY/TENANT/DATABASE` set in `.env.local`. **Embedding consistency is preserved by construction** — you are embedding locally (same fastembed ONNX) and only uploading pre-computed vectors; verify you are uploading explicit embeddings, **not** letting clients auto-embed.
- [ ] Confirm the JS client can connect and count the collection: quick `node -e` with `chromadb` + read-only key (create the read-only API key now too — ARCHITECTURE §11 "least privilege").
- [ ] Record signup notes (card requirement, tenant/database ids) in `Notes/OpenItems.md` (closes ARCHITECTURE §14 item 1).

### Exit gate
- Cloud collection count == local count (from Phase 2 summary); a JS-client health snippet returns that count.

---

## Phase 4 — Next.js App & UI (FR9)

**Implements:** ARCHITECTURE §4 (page), §7 endpoints; traceability FR9.
**Goal:** A working UI page calling a stubbed `/api/ask`; SSR content enforced. No real pipeline yet.

### Tasks
- [x] `web/app/page.tsx`: welcome line, 3 clickable example questions (from PRD §9), persistent "Facts-only. No investment advice." note; chat input + answer area; render citation from `response.source` only.
- [x] Server-render the welcome line, examples, and disclaimer without JS (PRD requires visible SSR).
- [x] `web/app/api/ask/route.ts`: stub returning a fixed envelope (use the exact ARCHITECTURE §6.1.8 JSON shape — the UI should already speak the final schema).
- [x] `web/lib/prompts.ts`: write the final prompt/system-rules now (grounded-only, ≤3 sentences, exactly one URL from chunks, "Last updated from sources: <date>", refusal language) — text is cheap to get right early and Phase 5 consumes it as-is.
- [x] Message-state handling: no persistent chat log server-side (NFR).

### Exit gate
- UI renders, example buttons populate the input, submit calls `/api/ask`, and the stub envelope renders with citation + type badge. No function code yet — fine.

---

## Phase 5 — Retrieval + Generation (FR3–FR5, FR10, FR11)

**Implements:** ARCHITECTURE §6.1 steps 3–6 (RAG path only), §6.1.8 envelope; traceability FR3, FR4, FR5, FR10, FR11.
**Goal:** End-to-end factual answers on local dev via the real pipeline. Guardrails come next; this phase is only the happy path.

### Tasks
- [ ] `web/lib/retriever.ts`: query → embedding via `@huggingface/transformers` with `onnx/all-MiniLM-L6-v2` (bundled model file, normalized) → Chroma Cloud `query(nResults=k)` → grounding gate (max cosine < `SIM_THRESHOLD` → `not_found` response with best-scheme-URL from metadata, per §6.1.4).
- [ ] Hint: Chroma `query` returns pre-normalized-similarity distances; derive cosine ∈ [0,1] and compare against threshold — record the exact conversion used (cosine similarity = 1 − distance for `Relative Record`/cosine metric).
- [ ] `web/lib/llm.ts`: OpenAI-compatible client → `https://api.groq.com/openai/v1`, model from `GROQ_MODEL`; wire into `prompts.ts` (schema: system rules + 4 chunks with title/url/text + question).
- [ ] Post-checks (defense in depth, §6.1.6): ≤3 sentences; exactly one URL ∈ whitelist (parse candidate URLs but render only `source`); strip/flag percentile/percentage-return patterns.
- [ ] Wire `updated` field: max `scraped_at` across retrieved chunks.
- [ ] Handle 429 from Groq: honor `retry-after` once → curated fallback `type=rate_limited` (§6.1.7).
- [ ] `web/app/api/ask/route.ts` now orchestrates: embed → retrieve → gate → call Groq → post-check → envelope.
- [ ] **Embedding-drift check (critical, §8 last row):** run 3 known-answer queries through the deployed-in-dev path; verify the same chunk that won locally in Phase 2 smoke test also wins here. If not → embeddings drifted → stop and fix before continuing (fastembed vs transformers.js usage error is a likely cause).

### Exit gate (local)
- Ten manual queries (the PRD §8 seed set) entered in the dev UI: ≥8 factual answers acceptable (correct fact + one whitelisted link + ≤3 sentences); the remaining, whatever they are, do not hallucinate. Record all raw Q/A pairs to `data/qa_samples.json` (draft of **deliverable D4**).

---

## Phase 6 — Guardrails (FR6–FR8)

**Implements:** ARCHITECTURE §6.1 steps 1–2, §8 table; traceability FR6, FR7, FR8.
**Goal:** The refusal paths, in front of everything else, with tests.

### Tasks
- [ ] `web/lib/guardrails.ts`:
  - PII_FILTER: PAN `[A-Z]{5}[0-9]{4}[A-Z]`, Aadhaar `\b\d{12}\b`, email, 6-digit OTP, 13–19-digit account-like numbers → `refusal_pii` handling; **runs before any upstream call** and refuses without logging (§6.1.1).
  - Intent rules (regex): advice/opinion (`should i|invest|buy|sell|better to invest|good time|portfolio`) → `refusal_advice` template + educational link (Sebi-investor.org / AMFI) per §6.1.2; returns/performance (`returns|performance|compare perf`) → `returns_redirect` template + factsheet link with **zero LLM calls** per §6.1.2.
- [ ] Log scrubber: every `console.log` on the request path passes through the same regex scrubber.
- [ ] Order of checks in the route: PII filter → intent classify → RAG path (§6.1 sequence). Keep one `type` per response.
- [ ] `tests/ts/guardrails.test.ts`: table-driven tests — the four PRD §8 refusal queries plus adversarial variants ("buy PAN ABCDE1234F", "min SIP?", "what were good returns last week?").

### Exit gate
- All four PRD §8 refusal classes exactly correct: `refusal_pii` (nothing in logs — verify manually), `refusal_advice` (+ educational link), `returns_redirect` (+ factsheet link, no LLM console traffic visible in logs), and out-of-scope → honest `not_found`.
- RAG path unchanged from Phase 5 (refusals short-circuit it).

---

## Phase 7 — Evaluation Gate (all FRs) — the chunking decision point

**Implements:** ARCHITECTURE §5.3 (chunking decision), §11 (pre-ship gate); PRD §10 quality bar.
**Goal:** Run the PRD §8 10-query set through the dev deployment. Output = the formal recall measurement that decides whether recursive chunking ships or the semantic fallback must be built. This is the most important phase for the tech-report deliverable.

### Tasks
- [x] `scripts/eval_qa.py`: run each query against the local dev `/api/ask`, capture envelope, report per-query pass/fail with the pass criteria:
  - factual: correct fact present + exactly one whitelisted URL + ≤3 sentences;
  - refusal: correct `type` + expected extras.
- [x] Metrics printed as a table; artifacts written to `data/qa_samples.json` (final **deliverable D4** content).
- [x] **Chunking gate (ARCHITECTURE §5.3):** if recall < 8/10 → build semantic chunking fallback, re-ingest, re-run eval. Document the delta in a short notes file (this is report-gold for the submission). Do not tune anything else first.
- [x] Retune `SIM_THRESHOLD` from measured distributions, not intuition (look at Phase 2 smoke scores vs Phase 7 failures).
- [x] Guard: rate limits — pace requests in eval (≥3 s apart); 10 queries ≈ 15K tokens ≈ 2% of daily TPD (safe).

### Exit gate (the ship gate)
- ≥ 8/10 factual queries pass with clean citations;
- 3/3 refusal queries exact;
- zero advice/returns/PII violations found anywhere;
- chunking decision recorded (recursive ships, or semantic built and passes).

---

## Phase 8 — Deploy to Vercel (D1)

**Implements:** ARCHITECTURE §11 (Vercel + budget); PRD D1.
**Goal:** Public prototype link.

### Tasks
- [ ] `vercel` project from `web/`; set env vars in project settings: `GROQ_API_KEY`, `GROQ_MODEL`, `CHROMA_*` (read-only key), `CHROMA_MODE=cloud`, `RETRIEVAL_K`, `SIM_THRESHOLD`.
- [ ] Verify function bundle: ONNX model correctly bundled/loading (check build logs; ~23 MB asset; function memory headroom ok).
- [ ] Deploy → run the 10-query eval against the **public** URL (Phase 7 script with `-u` base-url flag), verify no regression from local.
- [ ] Cold-start acceptance: first-hit answer ≤ ~5 s total (ARCHITECTURE NFR); if worst-case cold start materially hurts UX on the demo link, evaluate the documented HF-Inference-API fallback (ARCHITECTURE §3.4) — only with sign-off, as a separate, reverted-able change.
- [ ] CORS: allow-list the deployed origin (`UI_ORIGIN`) since same-origin serves both → likely a no-op, confirm.

### Exit gate
- Public URL: 10/10 worth of PRD §8 behavior reproduced from live env (allow for `rate_limited` flakiness but show retries from logs; optionally do a second, spaced run).
- Delivery note: link works in an incognito browser; no env or console exposed.

---

## Phase 9 — Deliverables & Polish (D1–D5)

**Implements:** PRD §10 deliverables table; ARCHITECTURE §12/§13.
**Goal:** Submission-ready package. Nothing here changes behavior (except README fixes); if a bug is found, it re-opens the corresponding phase.

### Tasks
- [x] **D1:** Public link finalized; one clean `git` commit history & tags pushed.
- [x] **D2:** `data/sources.csv` + `data/sources.md` regenerated from the final scrape — exactly 5 whitelisted URLs and names.
- [x] **D3:** `README.md` at repo root: setup steps (`pip install -r requirements.txt`, `python -m scripts.ingest`, `npm run dev` in `web/`), scope statement (1 AMC + 4 schemes), architecture 1-paragraph summary, sample-commands for FR12 reindex, **known limitations** (from ARCHITECTURE & PRD §11, verbatim-ish), env var reference.
- [x] **D4:** `data/qa_samples.json` finalized from the Phase 7/8 run printing the eval table: 10 queries, answer, type, citation link, pass/fail.
- [x] **D5:** Disclaimer snippet ("Facts-only. No investment advice.") extracted into README with its location in `web/app/page.tsx` marked (commit: line / file path).
- [x] **Policy checklist (ARCHITECTURE §14.3):** re-read before the link goes public: Groq "Your Data" + Chroma Cloud DPA terms. Confirm no stored PII path exists (`grep` for anything logging the request body).
- [x] **Optional hygiene:** `Notes/OpenItems.md` items from Phases 0/3 formally ticked off.

### Exit gate
- The PRD §10 quality bar is satisfied from a *fresh* environment: clone → follow README → the app works end to end using only README instructions.
- Tag `v1.0.milestone` and prepare submission package.

---

## Cross-cutting rules for all phases

1. **Whitelist discipline:** the only URLs ever generated, validated, or rendered: the 5 whitelisted pages (+ the designated educator/factsheet link in refusal templates). Any deviation is a bug at any phase.
2. **No LLM on refusal paths:** after Phase 6, advice/PII/returns never touch Groq — this is both a correctness guarantee and our rate-budget protection.
3. **Embedding model is fixed:** `sentence-transformers/all-MiniLM-L6-v2` via its ONNX export; any change is out of scope for this plan, not a tuning knob.
4. **Secrets hygiene:** from Phase 0 onward; never committed, never printed in logs.
5. **Small commits, phase-bounded:** each phase ends on a green exit gate; avoid carrying in-progress state across phase boundaries.
6. **Chunking strategy is a swap-out, not an open question:** recursive ships by default; the semantic fallback is triggered only by the Phase 7 gate — and once triggered, it's a full build + re-eval, not a partial tweak.
