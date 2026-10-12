# product specification

## overview
"AirKing Data Tracker" scrapes Newark, NJ Central Planning Board and Zoning Board of Adjustment meeting agendas, extracts each land-use application into structured records, and presents them in a searchable web UI. It exists to solve a timing problem for Air King (Totowa, NJ, commercial HVAC contractor): by the time a mechanical permit is pulled the HVAC subcontractor has already been selected, but land-use board agendas surface projects 12–24 months earlier, while the general contractor is still being chosen. Every record links back to the source agenda PDF and the meeting's Google Drive project-files folder so a lead can be verified against the original in one click. Five towns are in scope: Newark, Bloomfield, Fairfield, Livingston, Montclair — of an eventual 22 in Essex County; ingestion is deliberately not built around abstractions for towns beyond this set until a sixth one is added. See `docs/TOWN_FORMATS.md` for the per-town/per-board agenda format reference.

---
# core user flow

## sales lead (browsing)
1. Open the table view, sorted by `hvac_score` descending (best leads first); a toggle switches to meeting date descending (latest first, oldest last)
2. Filter by location (state → county → town, cascading), board, tier, agenda section, date range, or "ground-up only"
3. Text-search across `project_text` and applicant name
4. Expand a row to read the full `project_text` verbatim
5. Follow the source PDF link and Google Drive folder link to verify and find contact info
6. Decide which GC/developer to call, and when

## developer (ingestion & correction)
1. Download agenda PDFs by hand from newarknj.gov/AgendaCenter, or receive them via the board's email distribution list, into a local directory
2. Run the ingestion pipeline against that directory (no network access to newarknj.gov required)
3. Pipeline deterministically parses the structured header fields, then sends the `project` paragraph to Claude for derived-field extraction and scoring
4. Review new/changed records; if a field is misparsed, apply a manual correction in the UI
5. Re-run ingestion later — corrections survive and are never overwritten by a re-parse

---
# non-goals
- Essex County towns beyond the five currently in scope (Newark, Bloomfield, Fairfield, Livingston, Montclair) — 17 remaining — other counties, other states
- Building permits, resolutions, legal notices, council/Legistar items, meeting-video transcription — agendas only
- Email digests, alerts, notifications, or CRM integration
- User accounts, roles, or auth — single-tenant internal tool
- Lead-status tracking or pipeline management — read-only view
- Mobile-specific UI — desktop browser only
