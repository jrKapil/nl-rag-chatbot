# Architecture — Mutual Fund FAQ RAG Chatbot

**Version:** 1.2
**Date:** 2026-11-08
**Derived from:** [`Docs/PRD.md`](./PRD.md) v1.0
**Status:** Approved basis for implementation
**Changelog:** v1.2 — locked **all-serverless**: Vercel + Chroma Cloud + Groq; no container host. FastAPI backend replaced by a Next.js route handler; query embeddings run in-function via the ONNX export of the mandated model.
**Changelog (v1.1):** Vercel + Groq adopted; Ollama/Streamlit dropped.

---

## 1. Summary

A facts-only mutual-fund FAQ chatbot implementing a classic two-stage RAG pipeline — **Data Ingestion** (scrape → chunk → embed → store) and **Data Retrieval** (retrieve → ground → generate with citation) — fully serverless:

| Layer | Choice |
|---|---|
| App (UI + `/api/ask` functions) | **Next.js on Vercel** (one repo, one deploy) |
| LLM | **Groq API** (free tier), default `openai/gpt-oss-120b`, OpenAI-compatible endpoint |
| Embeddings | **`sentence-transformers/all-MiniLM-L6-v2` (mandated)** via its official ONNX export: `fastembed` in Python for ingestion, `@huggingface/transformers` in the Vercel function for query embedding |
| Vector DB | **Chroma Cloud** (serverless Chroma; GA Aug 2025, free start; same Chroma API). Ingestion writes from Python client; query reads from JS client |
| Ingestion | Local/offline Python scripts (no server needed anywhere) |

**No containers, no Render, no HF Space, no always-on process.** Local development is the identical code path (Next.js dev server; ingestion scripts unchanged).

---

## 2. Fixed Constraints (traceable to problem statement)

- Data scope: exactly 5 Groww pages (AMC overview + 4 HDFC schemes). No crawling internal links.
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` — same model for documents and queries.
- Vector DB: ChromaDB (Chroma Cloud is ChromaDB as a managed service — satisfies the constraint; see §3).
- Chunking: Recursive (default), Semantic (documented fallback).
- Every answer: ≤3 sentences, exactly one source link, grounded in retrieved chunks.
- Guardrails: no advice, no computed returns, no PII accepted or stored.
- Public sources only; citations resolve only to the 5 whitelisted URLs.

---

## 3. Deployment Decisions (resolving PRD §12 — final)

1. **App: Next.js on Vercel.** Streamlit rejected (long-running server; incompatible with serverless). The API layer lives in the same Next.js app as a route handler — one deploy, one URL.
2. **LLM: Groq, everywhere.** OpenAI-compatible (`https://api.groq.com/openai/v1`), fast (~500 t/s). `GROQ_MODEL` env-resolved (llama-3.x names deprecated by Groq; keep to gpt-oss family). Ollama dropped from MVP.
3. **Vector store: Chroma Cloud.** Chroma's managed serverless offering — GA, free to start ($5 credits; negligible ongoing spend for our few-hundred-vector index), same Chroma API via the standard clients. Ingestion (Python `chromadb` client) and query (JS `chromadb` client) hit the same collection `mf_faq`.
4. **Query embeddings: in-function ONNX.** The model mandated by the problem statement cannot ship as torch (~GBs); its **official ONNX export** (`onnx/all-MiniLM-L6-v2`, ~23 MB quantized / ~90 MB fp32) runs in a Vercel Node function via `@huggingface/transformers`. Ingestion uses the same ONNX export via `fastembed` in Python. Same weights, same tokenizer → same vector space; the eval gate (§11) is the drift detector.
   - *Considered and rejected for MVP:* **HF Inference API** for query embeddings (once proposed under the container-based design). Verified 2026-11-08: HF is now pay-as-you-go Inference Providers (free tiers reduced to small starter credits), it serves fp32 weights (raising drift risk vs our int8-ONNX ingestion), and adds an external hop + token dependency. **Kept as documented fallback** if function cold-start or bundle size becomes a real problem — in that case, switch *both* ingest and query to HF Inference to preserve consistency.

---

## 4. System Components

```
┌────────────────── Vercel (the only server we touch) ─────────────────┐
│                                                                       │
│  app/page.tsx                app/api/ask/route.ts                     │
│  ┌────────────────┐   POST   ┌─────────────────────────────────┐      │
│  │ Next.js UI     │ ───────► │ 1. PII filter (regex)           │      │
│  │ welcome line   │          │ 2. Intent classify (rules)      │      │
│  │ 3 example Qs   │ ◄─────── │ 3. Embed query (ONNX MiniLM) ───┼──┐   │
│  │ disclaimer     │  JSON    │ 4. Chroma Cloud top-k ──────────┼──┼─┼─► Chroma Cloud
│  └────────────────┘          │ 5. Grounding gate               │  │ │   (collection mf_faq)
│   renders citation from      │ 6. ── Groq call ─────────────────┼──┼─┼─► Groq API
│   response.source only       │ 7. Post-checks                   │  │ │
│                              └─────────────────────────────────┘  │ │
└──────────────────────────────────────────────────────────────────────┘ │
                                                                          │
┌── Offline, on the dev machine (no hosting) ──────────────────────────┐ │
│ scripts/scrape.py → data/raw/ (HTML, text, manifest.json)            │ │
│ scripts/ingest.py → clean → chunk → fastembed (ONNX MiniLM) ─────────┼─┘
│                      → upsert Chroma Cloud (mf_faq)                  │
│                      → data/sources.csv/.md (deliverable D2)         │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 5. Data Ingestion Pipeline

Stage 1 of the required two-stage RAG. Offline Python, idempotent, re-runnable. **Ingestion is the only stateful job in the system — and it runs on a laptop, not a server.**

```
scrape → persist raw → load & clean → chunk → embed (fastembed/ONNX) → upsert Chroma Cloud → source list
```

### 5.1 Scraper
- `scripts/scrape.py` fetches **exactly** the 5 whitelisted URLs from `config/sources.py`. No link-following.
- One polite fetch pass per URL (retry once on transient failure; custom `User-Agent`; honors `robots.txt`).
- Persists per page: raw HTML, extracted clean text, scrape timestamp → `data/raw/{slug}.html|.txt` + `data/raw/manifest.json` (url, slug, name, fetched_at, status).
- Regenerates `data/sources.csv` / `data/sources.md` (deliverable D2).

### 5.2 Loading & cleaning
- HTML → text extraction (trafilatura or BS4) strips nav/footer/cookie banners; keeps scheme fact tables, "About", and how-to sections.
- Sections anchored on headings; section title becomes chunk metadata.

### 5.3 Chunking (decision recorded)
- **Shipped:** `RecursiveCharacterTextSplitter`, `chunk_size ≈ 800–1000 chars`, `overlap = 100–150`, separators `["\n## ", "\n### ", "\n\n", "\n", ". ", " "]` — section headers stay welded to their facts.
- **Fallback (documented, built only if needed):** semantic chunking via embedding-boundary detection.
- **Gate:** run the PRD §8 set through the deployed `/api/ask`; if exact-fact recall < 8/10, build semantic and re-evaluate before any other tuning.
- Budget note: 4 chunks × ~250 tokens ≈ ~1.5K prompt tokens/request — comfortably inside Groq free-tier TPM (§11).

### 5.4 Embedding & storage
- Ingest embeddings: `fastembed` (`onnx/all-MiniLM-L6-v2`, cosine-normalized). Query embeddings: `@huggingface/transformers` loading the same ONNX export. Both fp-normalized; any drift is caught by the eval gate.
- Chroma Cloud: API key + tenant/database via env vars (`CHROMA_*`); collection **`mf_faq`**, cosine space.
- Chunk metadata: `{url, scheme_name, page_type: amc|scheme|faq, section, chunk_index, scraped_at}`.
- Local/dev parity: the same scripts run against *local embedded chromadb* when `CHROMA_MODE=local` — a config switch, identical chunk/embed code.
- Re-ingestion (FR12) = run script; it deletes/rebuilds the collection from `data/raw/` (`--no-scrape` skips fetching).

---

## 6. Retrieval & Generation Pipeline

Stage 2 of the required two-stage RAG. Runs per question inside the Vercel function.

```
question → PII filter → intent classify → [refusal path | RAG path]
RAG path: embed query (ONNX MiniLM, in-function) → Chroma Cloud top-k (k=4) →
          grounding gate → prompt (rules + chunks) → Groq gpt-oss-120b →
          post-checks (≤3 sentences, single whitelisted URL) → response
```

### 6.1 Sequence (`POST /api/ask`)

1. **PII filter** (regex set: PAN `[A-Z]{5}[0-9]{4}[A-Z]`, Aadhaar `\b\d{12}\b`, email, 6-digit OTP, 13–19-digit account-like numbers). Hit → refusal response; **nothing logged or sent to Chroma/Groq** (FR7). All log writes pass the same scrubber.
2. **Intent classification** (regex/keyword rules — *"should i", "invest", "buy", "sell", "better to invest", "good time", "portfolio", "returns", "compare perf"*; LLM fallback only if ambiguous).
   - **Advice/opinion** → refusal template + educational link (Sebi-investor.org / AMFI) (FR6).
   - **Performance/returns** → deterministic template linking the official factsheet/source page; **Groq is never called** (FR8) — also conserves RPD allowance.
3. **RAG retrieval:** query → `@huggingface/transformers` ONNX MiniLM embedding (normalized) → Chroma Cloud `query(nResults=4)` on `mf_faq`.
4. **Grounding gate:** max cosine < threshold (initial ~0.35) → honest "not in my indexed sources; check the official page: <best-scheme-url>" (FR11). Never invents facts.
5. **Generation:** system rules (grounded-only, ≤3 sentences, exactly one URL from provided chunks, "Last updated from sources: <max(scraped_at)>", refusal language on advice asks) + chunks (title+url+text) + question → Groq `chat.completions`.
6. **Post-checks (defense in depth):** ≤3 sentences; exactly one URL ∈ whitelist (educator link only for refusals); strip/flag computed return figures. Violations → deterministic repair or curated response.
7. **429 handling:** Groq rate-limit → honor `retry-after` once → curated fallback (`type=rate_limited`) rather than 5xx.
8. **Response envelope:**

```json
{
  "answer": "The expense ratio of HDFC Large Cap Fund Direct Growth is 1.09%.",
  "source": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "updated": "2026-11-08",
  "type": "factual" | "refusal_advice" | "refusal_pii" | "returns_redirect" | "not_found" | "rate_limited",
  "chunks_used": 3
}
```
UI renders `source` as the single citation; never parses URLs from LLM text.

---

## 7. API & Configuration

| Endpoint | Purpose |
|---|---|
| `POST /api/ask` | `{ "question": "string", "k": 4? }` → envelope above (Vercel function) |
| `GET /` | the chat UI (SSR: welcome line, examples, disclaimer) |
| `scripts/ingest.py` | reindex (FR12) — offline-only now, replaces the old `/admin/reindex` endpoint |

- Env vars only: `GROQ_API_KEY`, `GROQ_MODEL` (default `openai/gpt-oss-120b`), `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE`, `CHROMA_MODE` (`cloud|local`), `RETRIEVAL_K` (4), `SIM_THRESHOLD` (0.35). **Secrets never committed** (Vercel env config; `.env.local` gitignored for dev).
- No auth (public demo, no user data).

---

## 8. Guardrail Design (PRD FR6–FR8)

| Threat | Control | Layer |
|---|---|---|
| User sends PII | Regex pre-filter; refusal; never logged, never sent upstream | §6.1.1 (first thing that runs) |
| Model gives advice | Intent rules + prompt rules + post-check | §6.1.2, §6.1.5–6.1.6 |
| Model computes returns | Intent class `returns` short-circuits LLM entirely | §6.1.2 |
| Hallucination | Grounding gate + "answer only from chunks" + post-check URL whitelist | §6.1.4–6.1.6 |
| Multiple/invalid citations | Post-check enforces exactly 1 URL ∈ whitelist; UI renders server-verified `source` only | §6.1.6–6.1.7 |
| Long answers | Prompt rule + sentence-count post-check | §6.1.5–6.1.6 |
| Rate-limit outage | `retry-after` once → curated fallback | §6.1.7 |
| Embedding drift between ingest & query | Same ONNX export both sides + recall gate | §5.4, §11 |

Every answer path lands in exactly one of six `type`s; all tested against PRD §8.

---

## 9. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| App runtime | Next.js (React + Node route handlers) | one deploy on Vercel |
| Embedding (query) | `@huggingface/transformers` + `onnx/all-MiniLM-L6-v2` | ~23 MB quantized model, in-function |
| Embedding (ingest) | `fastembed` (Python) same ONNX export | CPU; no torch dependency |
| Vector DB | `chromadb` clients (JS query / Python ingest) → Chroma Cloud | collection `mf_faq`; `CHROMA_MODE=local` for dev parity |
| LLM | Groq — `openai/gpt-oss-120b` default, `gpt-oss-20b` fallback | OpenAI-compatible; `GROQ_MODEL` env |
| Ingestion/eval | Python 3.11+ (`requests`, `trafilatura`/BS4, fastembed, chromadb) | ran offline only |
| Chunking | LangChain `textsplitter` or plain impl | recursive |
| UI | Next.js (SSR page + route handler) | serverless-friendly |

---

## 10. Repository Layout (planned)

```
RAGChatbot/
├── Docs/                     # PRD.md, ARCHITECTURE.md, ProblemStatement.txt
├── config/
│   └── sources.py            # the 5-URL whitelist + slugs + scheme names
├── data/                     # gitignored artifacts; produced, not committed
│   ├── raw/                  # scraped HTML/text + manifest.json
│   ├── sources.csv / .md     # deliverable D2
│   └── qa_samples.json       # eval set (PRD §8) + outputs for D4
├── web/                      # Next.js app (deployed to Vercel)
│   ├── app/
│   │   ├── page.tsx          # chat page: welcome line, examples, disclaimer
│   │   └── api/ask/route.ts  # POST /api/ask — the retrieval+generation function
│   ├── lib/
│   │   ├── guardrails.ts     # PII filter + intent rules (mirrors Postman-testable rules)
│   │   ├── retriever.ts      # ONNX embed + Chroma Cloud query + grounding gate
│   │   ├── llm.ts            # Groq client (OpenAI-compatible) + 429 handling
│   │   └── prompts.ts        # system rules incl. facts-only disclaimer wording
│   └── package.json
├── ingestion/
│   ├── scrape.py  clean.py  chunk.py  embed_store.py   # fastembed + chromadb (cloud or local)
│   └── make_sources.py       # D2 generation
├── scripts/
│   ├── ingest.py             # full (scrape+ingest) or `--no-scrape`
│   └── eval_qa.py            # runs PRD §8 set against /api/ask, computes recall → D4
├── tests/
│   ├── ts/                   # guardrails/post-check unit tests (vitest)
│   └── py/                   # scraper/cleaner/chunker unit tests (pytest)
├── requirements.txt
└── README.md
```

---

## 11. Deployment & Budget Notes

### Vercel
- `web/` deployed via Vercel; env vars set in project settings.
- SSR renders the welcome line, 3 example questions, and disclaimer without JS.
- Function cold start: ONNX model (~23 MB) loads in ~1–3 s — acceptable; Vercel keeps warm on active demo traffic.

### Chroma Cloud
- Free start (worth $5 credits) — for a few hundred vectors this is effectively free for the life of the deliverable; re-check whether card-on-file is required at signup (deploy-day checklist item).
- Sizing sanity: our index ≈ 500–1,500 vectors @384 dims → well under any paid threshold; query p50 ~20 ms warm, ~650 ms cold.
- Writes happen only at ingestion on the dev machine — the Vercel function gets **read-only** credentials to the cloud DB (least privilege).

### Groq free-tier budget (verified 2026-11-08)
| Limit | Value (free plan, text models) | Fit assessment |
|---|---|---|
| RPM | 30 | ✅ far above demo traffic |
| RPD | 1,000/day | ✅ demo day fine; don't loop big eval sweeps |
| TPM | 8K/min | ✅ each request ≈ 1–2K tokens (prompt + 4 chunks) |
| TPD | 200K/day | ✅ several hundred full answers/day |

- Answers capped at ≤3 sentences + k=4 retrieval keep requests ~1.5K tokens; TPM is never binding.
- Refusal and returns paths make **zero** LLM calls — protects RPD.

### Privacy
- Only PII-filtered question text + whitelisted-page chunks leave the request path (→ Groq). No user identifiers; no persistent chat logs. Re-read Groq "Your Data" and Chroma Cloud DPA terms at deploy time (§14).

### Pre-ship evaluation gate
PRD §8 set (10 queries, 3 refusals) must pass: factual answers ≤3 sentences with whitelisted citation ≥8/10; zero advice/returns/PII violations; refusal classes exact 3/3. Results land in `data/qa_samples.json` (D4). This gate also catches ONNX-embedding drift (§8).

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ONNX ingest/query embedding drift | silent recall loss | same official ONNX export both sides; eval gate is the tripwire |
| Vercel function cold start | slow first answer | ~1–3 s ONNX load; warm on active use; acceptable & documented; **fallback** = flip both embed paths to HF Inference API (§3.4) |
| Chroma Cloud signup/card friction | deploy-day blocker | free-tier card requirement checked before demo week; `CHROMA_MODE=local` keeps dev unblocked regardless |
| Chroma Cloud free credits run out | query outage | negligible actual usage; monitor; index snapshot kept in `data/raw/` for instant re-seed |
| Groww page structure change | scraper breaks | raw scrape persisted; whitelist versioned in `config/sources.py` |
| Groq model deprecation | client breaks | `GROQ_MODEL` env fix only; defaults kept on current gpt-oss family |
| Groq 429s | degraded UX | `retry-after` once → curated fallback |
| Vercel function cold start | slow first answer | ~1–3 s ONNX load; warm on active use; acceptable & documented |
| Recursive chunking splits fact tables | low recall | §5.3 gate triggers documented semantic fallback |
| PII leaks upstream or to logs | violates NFR | PII filter runs first; scrubber on all log writes |

---

## 13. Traceability

| PRD requirement | Where implemented |
|---|---|
| FR1 scrape 5 pages | `ingestion/scrape.py` + `config/sources.py` |
| FR2 ingestion pipeline | `ingestion/{clean,chunk,embed_store}.py` (fastembed → Chroma) |
| FR3 retrieval | `web/lib/retriever.ts` |
| FR4 grounded ≤3 sentences | `web/lib/prompts.ts` + post-checks (§6.1.6) |
| FR5 single citation | envelope `source` (§6.1.8) + §6.1.6 |
| FR6 advice refusal | `web/lib/guardrails.ts` |
| FR7 PII refusal | `web/lib/guardrails.ts` |
| FR8 returns→factsheet | §6.1.2 deterministic template (no LLM call) |
| FR9 UI copy | `web/app/page.tsx` |
| FR10 last-updated | `scraped_at` metadata → `updated` field (§6.1.8) |
| FR11 not-found path | §6.1.4 grounding gate |
| FR12 reindex | `scripts/ingest.py --no-scrape` (offline) |
| D1–D5 | §11 evaluation gate + `data/` artifacts |

---

## 14. Remaining Open Items

1. **Chroma Cloud signup details** — confirm free-tier card requirement + project/tenant IDs at deploy time; record in README.
2. **`SIM_THRESHOLD`** — initial 0.35; confirm/retune after first real scrape + eval run.
3. **Deploy-day policy read** — Groq "Your Data" + Chroma Cloud terms before the public link goes live.
