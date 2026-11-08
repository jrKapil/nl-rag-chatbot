# Mutual Fund FAQ RAG Chatbot

A facts-only mutual-fund FAQ chatbot built on a classic two-stage RAG pipeline
(**Data Ingestion** + **Data Retrieval**) over exactly **5 official public Groww
pages** covering the HDFC Mutual Fund overview and 4 HDFC schemes (Large Cap,
Flexi Cap, ELSS Tax Saver, Mid Cap).

> **Positioning: No investment advice.** A factual lookup assistant, not a recommender.

**Live prototype:** _Vercel URL to be added after deploy — see Phase 8._

## Scope

- **1 AMC overview** + **4 HDFC schemes** (Large Cap, Flexi Cap, ELSS Tax Saver, Mid Cap).
- Exactly 5 whitelisted source pages (see [`data/sources.md`](./data/sources.md)).
- No crawling of internal links; no third-party blogs as sources.

## Architecture summary

Fully serverless: **Next.js on Vercel** (UI + `/api/ask` route handler) →
**Pinecone serverless** (vector store, index `mf-faq`, dim 384, cosine) →
**Groq API** (`qwen/qwen3.8-27b` default, OpenAI-compatible) for generation.
Query embeddings run in-function via the ONNX export of the mandated model
`sentence-transformers/all-MiniLM-L6-v2` (`@huggingface/transformers`); ingestion
embeds via the same model through `fastembed` (Python) — same vector space.

Pipeline: `scrape → clean → chunk (recursive, ~900 chars/120 overlap) → embed → store →
retrieve top-k → ground → generate (≤3 sentences, one whitelisted citation) → guardrails`.

## Setup (fresh environment)

### Prerequisites
- Python 3.11+
- Node.js 20 LTS (for the web app)

### 1. Python environment
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Secrets
```bash
cp .env.local.example .env.local
# Fill in: GROQ_API_KEY, PINECONE_API_KEY, PINECONE_HOST, VECTOR_DB=pinecone
cp .env.local.example web/.env.local
# Same values for the Next.js app
```

### 3. Ingest (build the vector index)
```bash
python -m scripts.ingest                 # scrape + ingest
python -m scripts.ingest --no-scrape     # FR12: rebuild index from data/raw/ without refetching
python -m scripts.ingest_pinecone        # hosted Pinecone index (95 vectors)
```

### 4. Run the web app
```bash
cd web
npm install
npm run dev                              # http://localhost:3000
```

### 5. Run tests
```bash
# Python (scraper/chunker)
python -m pytest tests/py -q
# TypeScript (guardrails)
cd web && npx vitest run
# Interactive RAG tester
python -m scripts.ask
# Full eval (10 queries, paces 3s apart)
python -m scripts.eval_qa
```

## Deliverables (D1–D5)

| # | Deliverable | Location |
|---|-------------|----------|
| D1 | Working prototype (web app link / local run) | Vercel URL (Phase 8) / `cd web && npm run dev` |
| D2 | Source list (CSV/MD) of the 5 URLs used | [`data/sources.csv`](./data/sources.csv), [`data/sources.md`](./data/sources.md) |
| D3 | README | this file |
| D4 | Sample Q&A file | [`data/qa_samples.json`](./data/qa_samples.json) (10 queries + envelopes + pass/fail) |
| D5 | Disclaimer snippet used in UI | see below |

### D5 — Disclaimer snippet (verbatim)
> **"Facts-only. No investment advice."**

**Location in code:** `web/app/page.tsx` (header disclaimer block) and
`web/app/components/Chat.tsx` (rendered in answer meta). Used verbatim in the UI
per PRD §9/D5. Also appears in `data/sources.md`.

## Commands reference

| Command | Purpose |
|---|---|
| `python -m ingestion.scrape` | Full scrape pass (fetch + clean + persist + D2) |
| `python -m scripts.retext` | Rebuild `.txt`/sections from stored HTML (no network) |
| `python -m scripts.ingest --no-scrape` | FR12: rebuild index from raw |
| `python -m scripts.ingest_pinecone` | Hosted Pinecone ingest + smoke gate |
| `python -m scripts.smoke_query` | Local Chroma retrieval smoke (3 known-answer queries) |
| `python -m scripts.show_index` | Inspect local ChromaDB (`--page/--id/--query/--k/--full/--vector`) |
| `python -m scripts.test_answer` | E2E LLM test (6 cases, all checks) |
| `python -m scripts.ask` | Interactive RAG tester (type questions, `quit` to exit) |
| `python -m scripts.eval_qa` | Phase 7 eval gate (10 queries, paces 3s) |
| `python -m scripts.eval_qa --url https://...` | Run eval against deployed URL |

## Known limitations

- Knowledge is frozen at scrape time; data can become stale (mitigated by the
  re-ingestion command `python -m scripts.ingest --no-scrape` and the
  "Last updated from sources" stamp on every answer).
- Scope limited to one AMC (HDFC) and 4 schemes; out-of-scope questions are
  answered only if their facts exist on these pages, else refused.
- Groww pages may change structure, breaking the scraper (mitigated by storing
  raw scrapes in `data/raw/`).
- Chunking/retrieval quality bounded by facts being embedded from
  section-based pages.
- Embedding model is fixed (`all-MiniLM-L6-v2`); changing it is out of scope.
- Groq free-tier limits: 30 RPM / 1,000 RPD / 8K TPM / 200K TPD — refusals
  and returns paths make zero LLM calls to protect budget.

## Architecture

See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) (v1.3) for the full design,
[`docs/PRD.md`](./docs/PRD.md) for requirements, and
[`docs/IMPLEMENTATION.md`](./docs/IMPLEMENTATION.md) for the phase-wise build guide.

## Environment variables

See [`.env.local.example`](./.env.local.example) for the full reference. Key vars:

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq LLM API key |
| `GROQ_MODEL` | No | default `qwen/qwen3.8-27b` |
| `PINECONE_API_KEY` | Yes (prod) | Pinecone vector store |
| `PINECONE_HOST` | Yes (prod) | Pinecone index host (e.g. `mf-faq-3cgjwss.svc.aped-4627-b74a.pinecone.io`) |
| `PINECONE_INDEX` | No | default `mf-faq` |
| `VECTOR_DB` | Yes (prod) | `pinecone` (or `chroma` for local dev) |
| `RETRIEVAL_K` | No | default 4 |
| `SIM_THRESHOLD` | No | default 0.35 |
| `CHROMA_MODE` | No | `local` for dev tooling (default) |

## Notes

- Secrets are never committed. `.env.local` is gitignored.
- The vector store is Pinecone serverless (free tier); local Chroma (`CHROMA_MODE=local`)
  is kept for dev tooling.
- Rotate API keys after evaluation (both were pasted in chat during development).
