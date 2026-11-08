# Open Items — deploy-day & credential checklist

Tracks ARCHITECTURE.md §14 open items + IMPLEMENTATION.md phase-dependent credential notes.

## Phase 0 — credentials (user actions)

- [ ] **Groq API key** — created at console.groq.com → API Keys.
      - Model default `openai/gpt-oss-120b`; verify it appears as available for your org at deploy time (`console.groq.com/docs/models`).
      - Free plan limits (verified 2026-11-08): 30 RPM / 1,000 RPD / 8K TPM / 200K TPD.
- [ ] **Pinecone account** — created at app.pinecone.io (serverless free tier).
      - Findings recorded below once signed up:
        - Index name `mf-faq`, host `mf-faq-3cgjwss.svc.aped-4627-b74a.pinecone.io` (created 2026-11-08).
        - Index dim 384, metric cosine, serverless AWS us-east-1.
        - Ingest key: `PINECONE_API_KEY` in `.env.local` (gitignored; key was pasted in chat — rotate after evaluation).
        - Vercel read-only path: same key works server-side (Pinecone REST; no separate read-only key tier needed).

## Phase 1 — naming conventions (note)

- Raw files are named by **URL slug** (e.g. `hdfc-equity-fund-direct-growth.*` = HDFC
  Flexi Cap Fund — Groww serves that scheme under the legacy "equity fund" URL).
  Human-readable names live in `manifest.json` and `data/sources.csv/.md` (D2).
- Scraped data is a **static snapshot**; no live fetching at query time. Staleness
  is handled by FR12 re-ingestion + the "Last updated from sources" stamp (FR10).

## Phase 3 — during cloud switch

- [ ] Confirm Pinecone write path from Python client (explicit embeddings upload, no auto-embed).
- [ ] Confirm Pinecone serverless index ready + 95/95 vector parity (done 2026-11-08).
- [ ] TS client connection test against Pinecone index host (REST, `web/app/api/ask` Phase 5).

## Phase 8 / §14.3 — before public link goes live — deploy-day checklist

- [ ] Re-read Groq data policy: console.groq.com/docs/your-data
- [ ] Re-read Chroma Cloud terms / DPA.
- [ ] Confirm `web/app` logs nothing containing request bodies (PII promise).
- [ ] Verify deployed origin listens with `VECTOR_DB=pinecone` and index host reachable; no Chroma references in deployed code path.
- [ ] Verify Groq model `openai/gpt-oss-120b` still active (or pick current from the Models page — never pin a deprecated name).
