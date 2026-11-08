# PRD — Mutual Fund FAQ RAG Chatbot

**Version:** 1.0 (Draft for review)
**Date:** 2026-11-08
**Source:** `Docs/ProblemStatement.txt`
**Status:** Draft — awaiting approval

---

## 1. Overview

### 1.1 Problem
Retail users comparing mutual fund schemes ask the same small set of factual questions over and over — expense ratio, exit load, minimum SIP, lock-in period, riskometer, benchmark, how to download a capital-gains statement. Support and content teams at broker platforms answer these manually, and generic search results mix official scheme pages with third-party blogs and unsolicited "advice."

### 1.2 Solution
A small, **facts-only FAQ chatbot** built with a classic two-stage RAG pipeline (data ingestion + retrieval) over **exactly 5 official public Groww pages** covering the HDFC Mutual Fund overview and 4 HDFC schemes. Every answer carries **one cited source link**, answers are **≤3 sentences**, and opinionated/portfolio questions are politely refused with an educational link.

> **Positioning:** No investment advice. A factual lookup assistant, not a recommender.

---

## 2. Goals & Non-Goals

### Goals
| # | Goal |
|---|------|
| G1 | Answer factual scheme questions (expense ratio, exit load, min SIP, ELSS lock-in, riskometer, benchmark, statement download how-to) |
| G2 | Cite exactly one source link in every answer |
| G3 | Refuse opinionated/portfolio questions ("Should I buy/sell X?") with a polite, facts-only message + relevant educational link |
| G4 | Demonstrate a complete, correct RAG pipeline: Loading → Chunking → Embedding → Vector store → Retrieval → Generation |
| G5 | Tiny, usable web UI with welcome line, 3 example questions, and a mandatory disclaimer |

### Non-Goals
| # | Non-Goal |
|---|----------|
| N1 | **No investment advice** — no buy/sell recommendations, no portfolio construction |
| N2 | **No performance claims** — never compute, compare, or rank returns; link to the official factsheet if asked |
| N3 | **No PII** — never accept/store PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers |
| N4 | No crawling beyond the 5 whitelisted pages (no internal links, no third-party blogs) |
| N5 | No multi-AMC coverage, real-time NAV, transaction execution, or user accounts |

---

## 3. Users

| Persona | Description | Primary need |
|---------|-------------|--------------|
| Retail investor | Comparing HDFC schemes (Large Cap vs Flexi Cap vs ELSS vs Mid Cap) | Quick factual answers with a trustworthy source link |
| Support / content team | Handling repetitive MF queries | Deflect repetitive tickets with consistent, cited answers |

Both are treated as one user for the prototype: a single anonymous chat user. No login, no personalization.

---

## 4. Data Scope

Exactly **5 pages**, scraped once and stored. No follow-through of internal links.

| # | Type | Name | URL |
|---|------|------|-----|
| 1 | AMC overview | HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Large Cap | HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Flexi Cap | HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | ELSS (tax saver) | HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Mid Cap | HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

Scraped raw data (HTML/text) is persisted locally to support re-ingestion without re-scraping, and to produce the required **source list (CSV/MD)** deliverable.

---

## 5. Architecture & Pipeline

### 5.1 Stage flow (per problem statement)

```
[Scrape 5 URLs] → [Load & clean text]
        ↓
[Chunking: Recursive or Semantic — decided on the data]
        ↓
[Embedding: sentence-transformers/all-MiniLM-L6-v2]
        ↓
[Storing: ChromaDB (persistent, local)]
        ↓
[Retrieve top-k chunks per query] → [LLM answers with citation]
        ↓
[Chat UI with disclaimer + example questions]
```

Two distinct stages, as required: **Data Ingestion** (scrape → load → chunk → embed → store) and **Data Retrieval** (embed query → vector search → answer + citation).

### 5.2 Component requirements

**a) Scraper**
- Fetch the 5 whitelisted URLs; respect robots/ETag basics; single polite fetch pass (no crawling of internal links).
- Persist raw HTML and cleaned text per URL, tagged with scheme name + URL (metadata for Chroma).

**b) Chunking**
- Strategy is a build decision: **RecursiveCharacterTextSplitter** is the default; **Semantic chunking** is the fallback candidate if recursive chunks fragment the section-based data (scheme fact tables, FAQ blocks) and hurt retrieval.
- Decision criterion: retrieval hit-rate on the sample Q&A set (Section 8) — pick the strategy with better recall before tuning anything else.
- Preserve section headers (e.g., "Expense Ratio", "Exit Load", "Lock-in") inside chunks as much as possible; attach `{url, scheme_name, section, scraped_at}` metadata to every chunk.

**c) Embedding**
- Model: `sentence-transformers/all-MiniLM-L6-v2` (fixed by the problem statement).
- Applied identically to documents and user queries (same model, same normalization).

**d) Vector store**
- ChromaDB, persistent local directory, one collection `mf_faq` containing all chunks from the 5 pages.

**e) Retrieval + generation**
- Top-k retrieval (default k=4, tunable) → feed retrieved chunks + user question to the LLM.
- Answer must be grounded in retrieved content, **≤3 sentences**, and include exactly one source link (the URL of the best-matching chunk).
- Include a "Last updated from sources: <scrape date>" line where a scrape date is available.
- If retrieval is not confident / no relevant chunk found: say so honestly and point to the source page rather than hallucinating.

**f) Guardrails (must-have)**
- **Advice refusal:** classify intent; on opinionated/portfolio questions ("should I buy/sell", "which is better to invest", "is this a good time"), respond with a polite facts-only message + a relevant educational link, then optionally answer the nearest *factual* sub-question if one is clearly identifiable.
- **PII refusal:** detect PAN, Aadhaar, account numbers, OTPs, emails, phone numbers in user input; refuse and warn without storing it.
- **Performance-question handling:** if asked about returns/performance, do not compute or compare; link the official factsheet/source page.
- Disclaimer always visible in the UI: **"Facts-only. No investment advice."**

---

## 6. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | Scrape and store exactly the 5 whitelisted pages | P0 |
| FR2 | Ingestion pipeline: load → chunk → embed (MiniLM) → store in ChromaDB | P0 |
| FR3 | Retrieval: embed query → top-k vector search over `mf_faq` | P0 |
| FR4 | Answer generation grounded in retrieved chunks, ≤3 sentences | P0 |
| FR5 | Exactly one source link present in every answer | P0 |
| FR6 | Refuse opinionated/portfolio questions politely + educational link | P0 |
| FR7 | Refuse/handle PII input without storing it | P0 |
| FR8 | No computed/compared returns; link factsheet for performance questions | P0 |
| FR9 | UI: welcome line + 3 example questions + "Facts-only. No investment advice." note | P0 |
| FR10 | "Last updated from sources: <date>" shown with scraped date | P1 |
| FR11 | Honest "no relevant info found" path instead of hallucination | P1 |
| FR12 | Re-ingestion command to refresh the vector store (delete & rebuild) | P1 |

---

## 7. Non-Functional Requirements

- **Stack:** Python; free/local components preferred (sentence-transformers runs on CPU; ChromaDB is local) to keep the prototype zero-cost and reproducible.
- **Simplicity:** single small codebase; scraper + ingestion + app separated in modules; no databases beyond ChromaDB.
- **Privacy:** no PII storage anywhere (no chat logs persisted by default; if logs exist, they must be scrubbed of PII).
- **Public sources only:** citations resolve only to the 5 whitelisted pages; never screenshots of the back-end, never third-party blogs as sources.
- **Reproducibility:** a fresh environment can rebuild the index from stored raw text via documented commands in the README.
- **Latency (target):** answer in < ~5 s on a normal machine including embedding the query and LLM call.

---

## 8. Sample Q&A (evaluation set)

A file of **5–10 sample queries with the assistant's answers + links** is both a deliverable and the acceptance test set. Seed list:

1. "What is the expense ratio of HDFC Large Cap Fund Direct Growth?" → answer + source link
2. "What is the exit load for HDFC Flexi Cap?" → answer + source link
3. "What is the minimum SIP amount for HDFC ELSS Tax Saver?" → answer + source link
4. "What is the lock-in period of HDFC ELSS Tax Saver Fund?" → answer + source link
5. "What is the benchmark and riskometer of HDFC Mid Cap Fund?" → answer + source link
6. "How do I download my capital-gains statement?" → answer + source link
7. "Should I buy HDFC ELSS Tax Saver Fund now?" → **refusal** + educational link
8. "My PAN is ABCDE1234F, tell me my fund value?" → **PII refusal**, nothing stored
9. "What were the returns of HDFC Large Cap last year?" → no computed returns; link to factsheet/source page
10. "What funds does Zerodha offer?" / something out-of-scope → honest not-found / scope-limit answer

---

## 9. UI Requirements

Single-page chat:
- Welcome line (e.g., "Ask factual questions about HDFC Mutual Fund schemes.")
- 3 clickable example questions
- Persistent note: **"Facts-only. No investment advice."**
- Each answer rendered with its single citation link; refusal messages rendered politely, no citation invented for refusals.

---

## 10. Deliverables & Acceptance Criteria

| # | Deliverable | Acceptance criteria |
|---|-------------|---------------------|
| D1 | Working prototype (web app link / local run) | Runs from README instructions; answers the 10 sample queries acceptably |
| D2 | Source list (CSV/MD) of the 5 URLs used | Exactly the 5 whitelisted URLs, with scheme names |
| D3 | README | Setup steps, scope (AMC + 4 schemes), known limitations |
| D4 | Sample Q&A file | 5–10 queries with assistant answers + links, including refusal cases |
| D5 | Disclaimer snippet used in UI | Verbatim "Facts-only. No investment advice." text used in the app |

**Quality bar:**
- Every factual answer ≤3 sentences + exactly one correct source link.
- Zero advice/returns/PII violations across the sample Q&A set.
- Pipeline visibly implements load → chunk → embed → store (ChromaDB) → retrieve, with MiniLM as the embedding model.

---

## 11. Known Limits (for README)

- Knowledge is frozen at scrape time; data can become stale (mitigated by re-ingestion command and "Last updated" note).
- Scope limited to one AMC and 4 schemes; out-of-scope questions are answered only if their facts exist on these pages, else refused.
- Groww pages may change structure, breaking the scraper (mitigated by storing raw scrapes).
- Chunking/retrieval quality bounded by facts being embedded from section-based pages.

---

## 12. Decisions Resolved 2026-11-08

1. **Generation LLM:** ✅ **Groq API, free tier** — OpenAI-compatible, free, fast (~500 t/s); default model `openai/gpt-oss-120b` (current lineup; older llama-3.x names deprecated). See `Docs/ARCHITECTURE.md` §3, §11 for free-tier budget. Ollama dropped from MVP.
2. **UI framework:** ✅ **Next.js (React)** — required by the Vercel deployment decision; Streamlit and Ollama were rejected for the serverless runtime model (ARCHITECTURE.md §3).
3. **Deployment target:** ✅ **All-serverless** — Vercel for the entire app (Next.js UI + `/api/ask` route handler running query embeddings via the ONNX export of `all-MiniLM-L6-v2`), Chroma Cloud as the serverless ChromaDB, Groq for generation. No container host (Render/HF Space) is needed. See `Docs/ARCHITECTURE.md` v1.2 for the final shape and deploy-day checklist.
