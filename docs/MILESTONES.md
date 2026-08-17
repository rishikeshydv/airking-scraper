# newark agenda tracker: development milestones

## Milestone 1 — Project Scaffolding & Environment Setup

**Goal:** Repo skeleton for both ingestion (Python) and frontend (Next.js) exists, with Postgres running locally and envs configured.

**Deliverables:**
- Python project (venv/uv, `pyproject.toml`) with `pdfplumber`, `httpx`, `anthropic`, FastAPI, SQLAlchemy, Alembic
- Next.js app (App Router, TypeScript, Tailwind)
- Local Postgres (docker-compose or native), empty schema
- Folder structure per ARCHITECTURE.md, including empty `ingestion/fixtures/`
- `.env.example` + `.env.development` with placeholder keys

**Acceptance:** `uvicorn api.main:app` serves, `npm run dev` loads a blank page, `psql` connects to the local DB.

---

## Milestone 2 — Header Parsing Against Fixtures

**Goal:** The deterministic label parser correctly extracts every structured header field from real agenda PDFs — the core risk in this project, resolved before any UI work begins.

**Deliverables:**
- `ingestion/parse_header.py`: application_id, premises, block, lots[] (pipe-delimited), ward, applicant, attorney, agenda_section, item_number
- 5–10 committed sample PDFs in `fixtures/pdfs/` (including the Walnut Street CPB-20-13 example) with hand-verified expected JSON in `fixtures/expected/`
- Test runner diffing parser output against fixtures

**Acceptance:** parser output matches fixtures exactly for every committed sample.

---

## Milestone 3 — Manual Ingestion Pipeline & Compliant Fetcher

**Goal:** An end-to-end manual ingestion path from a local PDF directory into Postgres, plus a `robots.txt`-aware fetcher for the (default-off) authorized crawl mode.

**Deliverables:**
- `ingestion/fetch.py`: robots.txt check, ≤1 req/2s rate limit, `NEWARK_CRAWL_AUTHORIZED` gate
- `ingestion/ingest.py` CLI (`ingest --dir <path>`)
- Alembic migration for `meetings` + `agenda_items` (header fields only, no derived fields yet)

**Acceptance:** `ingest --dir fixtures/pdfs` populates `meetings`/`agenda_items` correctly; running against newarknj.gov without the authorization flag refuses with a clear error.

---

## Milestone 4 — Claude Field Extraction & Scoring

**Goal:** `project_text` is parsed into typed derived fields via Claude, and `hvac_tier`/`hvac_score` are computed deterministically from those fields.

**Deliverables:**
- `ingestion/extract_fields.py`: Claude call, JSON schema validation, confidence + model version stored per field
- `projects` table + block/lot linking across meetings
- `scoring.py` implementing the tier table and `hvac_score` formula

**Acceptance:** re-running ingestion on fixtures produces derived fields with confidence scores; a project scores as a strong lead despite carrying many `c` variances — verified against `newark_planning_board.pdf`'s CPB-25-111 (760-766 Clinton Avenue, ground-up mixed-use, 11 `c` variances, scores 352 — a top-tier B lead), since the original "Walnut Street CPB-20-13" fixture referenced here no longer exists post the Milestone 2 five-town fixture refresh (see docs/TOWN_FORMATS.md).

---

## Milestone 5 — Read API

**Goal:** FastAPI exposes the joined `agenda_items`/`meetings`/`projects` data with the filters the UI needs.

**Deliverables:**
- `GET /agenda-items` — filter by board, tier, section, date range, ground-up, text search; default sort `hvac_score` desc
- `GET /meetings/{id}`

**Acceptance:** API returns correctly filtered/sorted JSON against the ingested fixture data.

---

## Milestone 6 — Table UI

**Goal:** The sales-lead-facing table view is live and usable end-to-end.

**Deliverables:**
- Next.js table page, `FilterBar`, expandable `RowDetail` (full `project_text`)
- Links on every row to the source PDF and the meeting's Google Drive folder
- Repeat block/lot appearances grouped into one row with history
- Light/dark mode

**Acceptance:** the app shows real ingested data, sorted by score, filterable, with working outbound links.

---

## Milestone 7 — Manual Correction

**Goal:** A misparsed field can be corrected by the user and survives re-ingestion.

**Deliverables:**
- `<field>_override` + `corrected_by`/`corrected_at` columns
- `POST /agenda-items/{id}/corrections`
- Inline edit UI on `RowDetail`
- Ingestion logic updated to never overwrite an override

**Acceptance:** correct a field in the UI, re-run ingestion on the same source PDF, confirm the correction still shows (not overwritten).
