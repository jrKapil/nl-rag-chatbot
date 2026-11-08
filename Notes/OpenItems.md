# Open Items — deploy-day & credential checklist

Tracks ARCHITECTURE.md §14 open items + IMPLEMENTATION.md phase-dependent credential notes.

## Phase 0 — credentials (user actions)

- [ ] **Groq API key** — created at console.groq.com → API Keys.
      - Model default `openai/gpt-oss-120b`; verify it appears as available for your org at deploy time (`console.groq.com/docs/models`).
      - Free plan limits (verified 2026-11-08): 30 RPM / 1,000 RPD / 8K TPM / 200K TPD.
- [ ] **Chroma Cloud account** — created at trychroma.com → "Start free on Cloud".
      - Findings recorded below once signed up:
        - Card-on-file required? *TBD*
        - Tenant ID: *TBD*
        - Database ID/name: *TBD*
        - API key created (ingest/write key on dev machine): *TBD*
        - Read-only key created (Vercel function, least privilege — ARCHITECTURE §11): *TBD*

## Phase 1 — naming conventions (note)

- Raw files are named by **URL slug** (e.g. `hdfc-equity-fund-direct-growth.*` = HDFC
  Flexi Cap Fund — Groww serves that scheme under the legacy "equity fund" URL).
  Human-readable names live in `manifest.json` and `data/sources.csv/.md` (D2).
- Scraped data is a **static snapshot**; no live fetching at query time. Staleness
  is handled by FR12 re-ingestion + the "Last updated from sources" stamp (FR10).

## Phase 3 — during cloud switch

- [ ] Confirm Chroma Cloud write path from Python client (explicit embeddings upload, no auto-embed).
- [ ] JS client connection test (chromadb npm) against read-only key.

## Phase 8 / §14.3 — before public link goes live — deploy-day checklist

- [ ] Re-read Groq data policy: console.groq.com/docs/your-data
- [ ] Re-read Chroma Cloud terms / DPA.
- [ ] Confirm `web/app` logs nothing containing request bodies (PII promise).
- [ ] Verify deployed origin listens with `CHROMA_MODE=cloud` and no local-mode fallback misconfiguration.
- [ ] Verify Groq model `openai/gpt-oss-120b` still active (or pick current from the Models page — never pin a deprecated name).
