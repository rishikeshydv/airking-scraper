# town/board agenda format reference

Analysis of the 10 fixture PDFs in `ingestion/fixtures/pdfs/{planning,zoning}/` across the 5 towns now in scope: Newark, Bloomfield, Fairfield, Livingston, Montclair. Written before any multi-town parsing code, per the workflow rule to understand existing structure before changing it. This is the reference the next task (multi-town parser design) should start from.

---
## the shared pattern

Every board's *real* agenda item — as opposed to meeting administrivia — reduces to the same case record, already modeled by `AgendaItem`/`BlockLot` in `ingestion/parse_header.py`:

`agenda_section, application_id, applicant, premises, block/lot, [zone], [ward], [attorney], project_text, variances_raw`

Block+lot appears in nearly every real item across all 5 towns, confirming ARCHITECTURE.md's choice of block+lot (not address) as the stable business key. What differs town to town is never the field set — it's the label vocabulary, the item-boundary marker, the section vocabulary, and how much of the field set a given board bothers to print for a given section.

| field | Newark | Bloomfield (zoning, old business) | Fairfield | Livingston (zoning) | Montclair |
|---|---|---|---|---|---|
| application/case id | `Application: CPB-25-111` | none (implicit — one case per meeting) | `App # 2-2025`, `2021-22 (2)` | `Application No. 2026-26-V` | `App. 2959:` |
| applicant | `Applicant:` / `Owner:` (Newark uses both) | `Applicant/Owner:` | bare name after case # | bare name on its own line | name after em-dash |
| premises/address | `Premises:` | `Property location:` | bare address line | bare address line | inline after dash |
| block/lot | `Block(s)/Lot(s) 3042\|1,5` (also seen: `322: 5`, `850.01: 15, 19, and 20`) | `Block 1171, Lot 10` | `Block:2101; Lot:8.03` | `Block 6001; Lot 62` | `(Block 3305, Lot 3.01)` |
| zone | rare, inline in project text | `Zone: B-2` | absent | inline (`R-2 Zone`) | absent |
| ward | `Ward:` — **Newark-only concept**, no other town has wards | absent | absent | absent | absent |
| attorney | `Attorney:` | absent (board has its own attorney roster, not per-item) | absent | absent | absent |
| project narrative | full paragraph | full paragraph | **absent** | short sentence | one clause |
| variances | `'c'`/`'d'` codes in prose | prose (`D1 Use variance, Class C Bulk variances...`) | bare type only (`C Variance`) | itemized: code section + required/proposed/variance amount per line | absent |

Bloomfield *planning* board and Fairfield *memorialization* entries are thinner still — sometimes only an applicant name or address, no block/lot or project text. That's what the source document actually contains for a resolution vote (no need to restate a project already described at a prior meeting), not a parsing gap — extraction should leave those fields empty/null rather than force a value, per CLAUDE.md priority #1 (extraction correctness traceable to source text).

---
## what varies per town — the actual parsing surface

1. **Label vocabulary** for the same field: `Application:` vs `App #` vs `App.` vs `Application No.`; `Block(s)/Lot(s)` vs `Block X, Lot Y` vs `Block: X; Lot: Y`.
2. **Item-boundary marker**: Newark — a line matching `N.` that also contains the word "application"; Bloomfield/Montclair — lettered `A.`/`a.` sub-items nested under a numbered section; Livingston — `N)` numbered sub-items; Fairfield — case-number-prefixed paragraph breaks (no numbering at all).
3. **Section vocabulary**: `New Application` vs `New Business`; `Extension` vs `Continued Matters`; `Memorialization` vs `Memorialization of Resolutions` vs `Old Business – Consideration of Memorializing Resolutions`. The existing `SECTION_KEYWORDS` dict already anticipates this shape (it's a synonym map to a canonical section name) — it just needs more entries.
4. **Field completeness** varies by board and by section, as above.

---
## boilerplate to discard (confirmed present in all 10 PDFs)

Not agenda content — meeting logistics/administrivia that should never reach a parsed `AgendaItem`:
- Meeting title/date/time header, Zoom/dial-in info, venue address, broadcast/streaming plug (Comcast/Verizon channel, YouTube, Facebook Live)
- Open Public Meetings Act notice boilerplate ("adequate notice of the time and date... was posted...")
- Roll Call, Pledge of Allegiance, Call to Order, Statement of Compliance
- Approval of Minutes (board-member motion trackers, "Mr. X ____ Mr. Y ____")
- Committee Reports, Payment/Approval of Bills, invoice numbers
- Board professional roster (attorney/planner/secretary *of the board*, distinct from an item's own `Attorney:` field)
- "Enclosed" report/exhibit lists (engineer/planner/fire dept memos attached to a case, not a case field itself)
- Executive Session litigation references with no project info
- Adjournment, Next Meeting date, "End of Meeting"

---
## per-PDF: agenda-only content actually found

### `planning/newark_planning_board.pdf` (CPB, Aug 10 2026)
Keep: 8 numbered items under `Extensions:` (3) and `New Applications` (5) — CPB-18-57, CPB-23-70, CPB-22-36, CPB-25-111, CPB-26-13, CPB-26-26, CPB-25-115 (uses `Owner:` instead of `Applicant:` — current parser doesn't recognize this label, will misparse), CPB-26-31.
Discard: Zoom/dial-in block, Google Drive link line (belongs in `meetings.google_drive_url`, not an item field), "Open Public Meetings Act" / "Roll Call" bare labels, "Memorialization of Minutes:", "Memorialization of Resolutions:" (empty), "End of Meeting:", "Next Meeting:".

### `zoning/newark_zoning_board.pdf` (ZBA, Aug 6 2026)
Keep: 3 items — ZBA-25-48, ZBA-26-08 (both under implicit "new"/pending), ZBA-25-18 under `Pending Applications:`. None have an `Attorney:` line (already null-safe in current schema).
Discard: same Zoom/dial-in/Drive-link header, "Memorialization of resolutions:"/"Memorialization of Minutes:" (empty), "Resolution to convene into Executive Session", "End of Meeting:".

### `planning/bloomfield_planning_board.pdf`
Keep: Resolutions items 4A (`Bloomfield Broad Associates Urban Renewal, LLC`) and 4B (`91 Beach Street`) — thin, no block/lot/project text available in source.
Discard: Regular-meeting notice paragraph, Board Secretary contact line, `Roll Call:`, `Communications:` (the block/lot mentioned there is for a planning *report*, not an application item), `Minutes: None`, `Old/New Business: None`, `Adjournment:`, "THIS AGENDA IS SUBJECT TO CHANGE".

### `zoning/bloomfield_zoning_board.pdf`
Keep: one Old Business item — Block 1171/Lot 10, 1250-1274 Broad Street, Zone B-2, Applicant/Owner SPG at Bloomfield LLC, D1 Use + Class C Bulk variances, McDonald's drive-thru. (The near-identical "Property location.../Proposal to..." paragraph before Roll Call is a preview of this same case, not a second item — dedupe against the Old Business entry.)
Discard: special-meeting notice paragraph, application-materials link, `Roll Call:`, `Communications: None`, `Minutes: 9/17/26`, `Resolutions: None`, `Applications to consider for Board Planner and/or Traffic Expert: None`, `New Business: None`, `Adjournment:`.

### `planning/fairfield_planning_board.pdf`
Keep: Memorialization item — App # 2-2025, Toll NJ1 LLC, 100 West Greenbrook Road, North Caldwell NJ, Block 2101/Lot 8.03, "Preliminary and Final Major Site Plan / Major Subdivision" (no project narrative in source).
Discard: board roster/roll-call grid, attorney/planner/secretary line, Pledge of Allegiance, notice-posting boilerplate, `APPROVAL OF MINUTES:` block, `APPROVE BILLS:` + invoice numbers.

### `zoning/fairfield_zoning_board.pdf`
Keep: Memorialization item — 2026-3, Michael and Lois Hammer, "C Variance", 7 John Street, Block 4702/Lot 1.01. New Business item — 2021-22 (2), FOH Fairfield Limited LLC, 129/131/137 Fairfield Road, Block 4702/Lot 1.01 (same block/lot as the memorialization item above — coincidence in this fixture, not a parsing signal).
Discard: page headers/footers, board roster/motion grid (both pages), attorney/secretary/planner line, notice-posting boilerplate, `APPROVAL OF MINUTES:`, `MISCELLANEOUS:`/`Approve Bills:` + invoice numbers, the `Enclosed:` report list under New Business (exhibit metadata, not a case field).

### `planning/livingston_planning_agenda.pdf`
Keep: 2 Old Business memorialization items — Spectrum360 LLC / 630 West Mount Pleasant Avenue / App No. 2022-9-PFSP (Amendment); 56 Burnet LLC / 56 Burnet Street / App No. 2026-44-MSUBV. No block/lot in this section's source text.
Discard: dept letterhead/contact info, `Call to Order`, `Statement of Compliance...`, `Roll Call`, `Approval of Minutes`, `Communications`, `New Business:` (empty), `Executive Session – Litigation (If Needed)`, `Adjournment`.

### `zoning/livingston_zoning_agenda.pdf`
Keep: Conference agenda's 8 memorialization line items (address; App No.; applicant name only — no block/lot). Regular agenda's 7 numbered items under `Continued Matters`/`New Business`, each with block/lot, address, App No., applicant + zone, project sentence, and an itemized variance list (code section, required, proposed, variance amount) — richest non-Newark source.
Discard: dept letterhead, "This agenda is for information only...", `Call to Order`, `Statement of Compliance...`, `Roll Call` (×2, once per sub-meeting), `Adjournment` (×2).

### `planning/montclair_planning_board.pdf`
Keep: Old Business item 6a — App. 2959, 116-118 Walnut Street, Grafton Inns LLC, Block 3305/Lot 3.01, "expand seasonal deck and reconfigure parking lot". New Business items 7a–7d are council referrals/discussion items with **no application/case** — not agenda items in the leads sense, exclude.
Discard: dept letterhead, broadcast plug, `Call to Order and Statement of Compliance...`, `Roll Call.`, `Swearing in of Board Professionals`, `Approval of Minutes:`, `Resolutions:` (empty), `Committee Reports.`, `Payment of Bills.`, `Adjournment.`, EEO footer.

### `zoning/montclair_zoning_board.pdf`
Keep: Resolutions item 5a — App. 2953, 105 Upper Mountain Avenue, Yaakoub Hijazi, Block 1503/Lot 19, "In-ground pool and detached garage". New Business item 7a — App. 2976, 95 South Mountain Avenue, Rashmi Sharma, Block 1301/Lot 30 and 31, "Construction of new detached garage on Lot 30".
Discard: dept letterhead, broadcast plug, `Call to Order...`, `Announcements`, `Roll Call`, `Approval of Minutes:`, `Old Business` (empty), `Executive Session – Litigation: App. 2958 - 84 Clinton Avenue` (case reference with zero project data — not usable as an item), `Adjournment.`, EEO footer.

---
## open items for the next task (parser design), not resolved here

- `_parse_block_lot` in `parse_header.py` only splits on `|`; Newark itself already varies (`322: 5`, `850.01: 15, 19, and 20` use `:`) — pre-existing bug, independent of multi-town work.
- `FIELD_LABELS` has no `Owner` synonym for `applicant` — `newark_planning_board.pdf` item 4 uses `Owner:` and would currently parse as empty applicant.
- `meetings.board` is modeled as a Newark-specific `CPB`\|`ZBA` enum (ARCHITECTURE.md). Other towns' boards don't share those names — will need a `town` field distinct from a generalized board type.
- `fixtures/expected/*.json` (`cpb_2026-04-20.json`, `cpb_2026-07-13.json`, `cpb_2026-08-10.json`, `zba_2026-05-11.json`, `zba_2026-06-08.json`) have no matching PDF anymore, and `tests/test_parse_header.py` globs `PDF_DIR.glob("*.pdf")` non-recursively so it currently collects zero fixtures against the new `planning/`/`zoning/` subdirectory layout. Needs a fixture/naming redesign (e.g. `<town>_<board>.json` matching the new PDF stems) before parser work can be verified.
