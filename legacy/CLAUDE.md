# CLAUDE.md — legacy/

## What this directory is

The pre-extraction monolith. It exists as a read-only reference baseline.

**Do not modify any file in this directory.**

The five documented flaws are intentional. They must stay broken so:
- The eval scorecard can measure the "before" state
- Characterization tests have a fixed target to pin against
- The modernization story has a clear starting point

## The five flaws (see FLAWS.md for details)

| # | Flaw | Location |
|---|------|----------|
| 1 | Hardcoded credentials | Module top — `DB_CONNECTION_STRING`, `API_KEY`, `SMTP_PASSWORD` |
| 2 | SQL injection | `get_customer_raw()` — f-string query construction |
| 3 | Global mutable state | `INVENTORY`, `CUSTOMERS`, `ORDERS` module globals |
| 4 | Deep nesting | `process_order()` — 8 levels of indentation |
| 5 | Mixed concerns | HTTP + DB + email + validation all in `process_order()` |

## Permitted actions

- Read files to understand behavior
- Reference code in characterization tests
- Cite specific lines in ADRs and docs

## Prohibited actions

- Editing `src/order_processor.py` to fix anything
- Adding files that import from and re-export legacy code as "improved"
- Silencing the eval scorecard warnings for this directory
