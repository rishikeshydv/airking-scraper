# newark agenda tracker architecture
## technology stack
ingestion (Python 3.11+):
1. httpx — HTTP client for the gated authorized-crawl mode
2. pdfplumber — PDF text extraction (text-based PDFs, no OCR needed)
3. anthropic — Claude API for `project_text` field extraction

backend:
1. FastAPI
2. PostgreSQL (SQLAlchemy + Alembic migrations)

frontend:
1. Next.js (App Router)
2. TypeScript
3. Tailwind CSS

hosting: TBD — decide during MILESTONES Step 1

note: an all-TypeScript stack (Next.js API routes instead of FastAPI, `pdf-parse` instead of `pdfplumber`) is a viable alternative if a single language is preferred. Proceeding with the Python/FastAPI split above per intake.

---
# architectural goals
backend responsibilities:
1. Own the robots.txt compliance check and rate limiting — the frontend never talks to newarknj.gov directly
2. Own the deterministic header parser and the Claude extraction call; store raw source text alongside every derived field
3. Never let re-ingestion overwrite a stored manual correction
4. Expose a read-mostly REST API — the only write path is corrections

frontend responsibilities:
1. Dense, filterable table UI — no client-side scraping or PDF handling
2. Every row links to the source PDF and the meeting's Google Drive folder
3. Light/dark mode support

---
# security model
1. `ANTHROPIC_API_KEY` and `DATABASE_URL` are read only from `.env` files — `.env.development` locally, `.env.production` on deploy
2. `.env*` files are gitignored; only a committed `.env.example` with placeholder values
3. `NEWARK_CRAWL_AUTHORIZED` defaults to `false`; automated fetches against newarknj.gov are refused unless explicitly enabled

---
# ingestion modes (robots.txt compliance)
Checked against the live files (2026-08-16): `newarknj.gov` and the other CivicPlus-hosted town sites (Bloomfield, Fairfield, Livingston) disallow specific paths for generic user-agents (`/admin`, `/search`, `/currentevents`, `/map`, …) but not `/AgendaCenter` — so automated fetching of agenda listings and PDFs on those four is `robots.txt`-compliant. Montclair is the opposite case: its agendas are hosted on `ecode360.com`, a third-party platform (General Code) whose own `robots.txt` explicitly disallows `/documents` — the path Montclair's agendas live under. Permission from Montclair Township doesn't override the platform operator's own policy, so Montclair stays manual-ingestion-only until that's resolved directly with General Code. This robots.txt check — per site, checked live, not assumed — is a hard architectural constraint, not a footnote.

1. **Manual mode (default, v1)** — point the parser at a local directory of PDFs downloaded by hand or received via the board's email list. Zero network access required.
2. **Authorized crawl mode (gated)** — runs only when that town's `<TOWN>_CRAWL_AUTHORIZED=true` (e.g. `NEWARK_CRAWL_AUTHORIZED`), which is documented as requiring written permission from the town, in addition to (not instead of) the robots.txt check. Checks `robots.txt` before every fetch, rate-limits to ≤1 request/2s, sends a descriptive User-Agent with a contact email. Supported towns: Newark, Bloomfield, Fairfield, Livingston — see `ingestion/scrape.py`.
3. Do not design around circumventing `robots.txt` — this is why Montclair has no crawler. Manual mode covers MVP volume (~2 meetings/month/board) and remains the only path for Montclair.

---
# state management
No global client store for v1. The table view derives from one API response (`GET /agenda-items`) held in a query cache (e.g. TanStack Query). Filters (board, tier, section, date range, ground-up, search text) are local component state, mirrored to the URL query string so views are shareable.

Core data shape returned by the API mirrors `agenda_items` joined to `meetings` and `projects` — see Data Model.

---
# data model
Three tables. `block` + `lot` is the stable business key — not address (written inconsistently) or applicant (a new LLC per project). Confirmed to hold across all five towns now in scope — see `docs/TOWN_FORMATS.md`.

- **meetings** — town, board (`planning`|`zoning`, generalized across all 5 towns rather than Newark's own `CPB`/`ZBA` naming — matches `ingestion/parse_header.py`'s `(town, board)` dispatch key), meeting_date, meeting_type, document_center_id, source_url, google_drive_url, raw_text, ingested_at
- **agenda_items** — meeting_id FK, agenda_section, item_number, application_id, premises, block, lots[], ward, applicant, attorney, project_text, variances_raw, plus derived fields and override fields below
- **projects** — one row per real-world project keyed on block+lot, linking the `agenda_items` where it reappears across meetings

Derived fields on `agenda_items` (extracted from `project_text` by Claude; stored with a confidence score and model version): `building_type`, `stories`, `unit_count`, `square_footage`, `is_ground_up`, `involves_demolition`, `zone`, `variance_types[]`, `hvac_tier`, `hvac_score`.

Correction fields: a nullable `<field>_override` plus `corrected_by`/`corrected_at` per derived field. Display and scoring always prefer the override when present; re-ingestion writes only the raw extraction, never the override.

---
# scoring model
`hvac_tier` from `building_type`: **A** — medical/lab, restaurant/commercial kitchen, cannabis cultivation, data center, cold storage, hotel, school, house of worship. **B** — office, retail, mixed-use, multifamily 4+ stories, fitness, climate-controlled self-storage. **C** — bulk warehouse/distribution, industrial shell, parking structure. **D** — 1–3 family residential, fences/decks/sheds/signs, parking-only variances, subdivision with no building proposed.

`hvac_score` combines tier, ground-up vs. alteration, square footage (filtered second, never first), and variance type into one sortable number. `d` variances (change of use, `d1` strongest) are a strong positive signal; `c` variances (dimensional) carry almost no signal alone.

---
# suggested folder structure
```
newark-agenda-tracker/
├── ingestion/
│   ├── fetch.py             # robots.txt-aware fetcher, manual + authorized modes
│   ├── parse_header.py      # deterministic label parsing (application, block/lot, ward…)
│   ├── extract_fields.py    # Claude call: project_text → derived fields + score
│   ├── ingest.py            # CLI entrypoint: directory or crawl → DB
│   └── fixtures/
│       ├── pdfs/            # committed sample agenda PDFs
│       └── expected/        # expected parsed output per fixture
├── api/
│   ├── main.py               # FastAPI app
│   ├── models.py              # SQLAlchemy models
│   ├── routes/
│   │   ├── agenda_items.py    # GET list/filter
│   │   └── corrections.py     # POST correction
│   └── db.py
├── migrations/                # Alembic
├── frontend/
│   ├── app/page.tsx           # table view
│   ├── components/
│   │   ├── AgendaTable.tsx
│   │   ├── FilterBar.tsx
│   │   └── RowDetail.tsx
│   └── lib/api.ts
├── .env.example
├── .env.development
└── .env.production
```
