# CLAUDE.md — Code Modernization Hackathon

## Project
Scenario 1: "The Monolith" — extracting a clean OrderValidator service from a legacy
Python order-processing monolith. Domain: e-commerce order management.

## What we built
- `legacy/src/order_processor.py` — the mess: 5 documented flaws, deep nesting, global state
- `modern/src/order_validator.py` — extracted service: pure class, injected dependencies, no globals
- `tests/characterization/` — lock legacy behavior before extraction
- `tests/eval/score.py` — automated scorecard: before 20/100, after 100/100

## Team conventions
- Never modify `legacy/` to "fix" it — it must stay broken as the baseline
- Characterization tests must pass against BOTH legacy and modern code
- Every new file in `modern/` needs a corresponding test
- No hardcoded secrets — use os.getenv()
- Commit messages: feat: / fix: / test: / docs: / chore:

## What Claude should always do
- Use dependency injection over global state
- Prefer early returns over deep nesting
- Validate inputs at system boundaries
- Return typed, consistent results

## What Claude should never do
- Hardcode credentials, API keys, or passwords
- Mutate global state as a side effect of validation
- Mix HTTP handling, DB access, and business logic in one function
- Use bare except or swallow errors silently

## Directory ownership
- `legacy/` — reference only, do not modify
- `modern/` — the target: clean, tested, production-ready
- `tests/` — all tests must be green before merge
- `docs/` — ADR and user stories
- `presentation/` — HTML deck for judges
