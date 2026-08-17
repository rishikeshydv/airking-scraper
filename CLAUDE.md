This repository is built incrementally with a strong emphasis on maintainability, correctness, and production-quality engineering practice. It is an internal tool for Air King (Totowa, NJ), not a demo — extraction correctness matters more than polish or scale, and every derived field must be verifiable against the original PDF.
---
# engineering philosophy
Prioritize:
1. Extraction correctness, traceable back to source text
2. Readability
3. Maintainability
4. Performance
---
Avoid:
1. premature optimization
2. speculative abstractions — five towns are in scope (Newark, Bloomfield, Fairfield, Livingston, Montclair); do not build abstractions anticipating towns beyond this set until a sixth one exists
3. unnecessary indirection
---
# workflow rules
Implement features incrementally.
For every task:
1. Understand existing architecture before changing it
2. Explain intended changes briefly
3. Implement the minimal complete solution
4. Verify correctness — fixture match for parsing, manual check for UI — before moving on
Do not:
1. refactor unrelated code
2. build future-facing abstractions for hypothetical needs (e.g. a second town, auth, alerts)
3. modify files outside the current task's scope
---
# ui principles
1. Light/dark mode support
2. Dense table over decorative UI — desktop browser only, no mobile layout
3. Every row links to its source PDF and its meeting's Google Drive folder
---
# code style
Python:
1. type-hint all function signatures
2. no bare `except:` — catch specific exceptions
3. keep parsing/scoring logic pure; keep I/O (fetch, DB, Claude calls) at the edges

TypeScript:
1. avoid `any`
2. use explicit typing

React:
1. functional components only
2. avoid unnecessary hooks
3. avoid premature memoization
---
# ingestion & api architecture
1. All Claude API calls happen in `ingestion/extract_fields.py` — never from the frontend
2. Manual/local ingestion is the default mode; authorized crawling requires that town's `<TOWN>_CRAWL_AUTHORIZED=true` (Newark, Bloomfield, Fairfield, Livingston) and is documented as requiring written permission from the town, in addition to a clean `robots.txt` check (verified per-site, not assumed — see `docs/ARCHITECTURE.md`). Montclair has no crawler: its agenda platform (ecode360.com) disallows automated access to its own site in `robots.txt`.
3. Environment variables via `.env.development` / `.env.production`; never commit real values
4. Re-ingestion must never overwrite a stored manual correction
---
# modification rules
1. Before adding a new file, verify an appropriate file does not already exist.
2. Before creating an abstraction, confirm a duplicate does not already exist.
3. Before introducing a dependency, justify why a native API or existing dependency is not sufficient.
---
# important
Do not generate large amounts of speculative code. Do not build abstractions anticipating towns beyond the five currently in scope. Build step-by-step with production-quality decisions, and prove the parser against fixtures before starting any UI work.
