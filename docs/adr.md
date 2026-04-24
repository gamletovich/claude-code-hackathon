# ADR-001: Extract OrderValidator as the First Service Boundary

**Date:** 2026-04-24
**Status:** Accepted
**Deciders:** Engineering lead, QA lead, Finance stakeholder

---

## Context

Northwind Logistics runs order intake through a single Python function,
`process_order()`, in `legacy/src/order_processor.py`. The function mixes
five distinct concerns, contains hardcoded production credentials, and has
accumulated 8 levels of nesting over five years of patch-on-patch maintenance.

The board has approved "modernization" without specifying scope. Two approaches
were on the table:

1. **Big-bang rewrite** — freeze features, rewrite everything in 6 months.
2. **Strangler-fig extraction** — carve out one service at a time, running
   old and new in parallel, retiring legacy pieces as confidence grows.

A third option — **leave it alone and document it** — was raised by ops
and rejected by finance after the Q1 security audit flagged the hardcoded credentials.

---

## Decision

We will use the **strangler-fig pattern**, extracting `OrderValidator` as the
first seam. This service:

- Accepts a raw order dict at its boundary
- Validates business rules (stock, credit, customer status, address)
- Returns a typed `ValidationResult` — accepted or rejected with a reason
- Does **not** commit state, send emails, or make HTTP calls

The monolith continues to run unchanged. The new service is wired in alongside
it; the monolith's validation logic is progressively replaced call-site by call-site.

---

## Why this seam first

We ranked extraction candidates by three factors:

| Candidate | Coupling | Test coverage before | Business criticality |
|-----------|----------|----------------------|----------------------|
| Order validation | Low (returns a value, no DB writes of its own) | None | High |
| Inventory writes | High (touches 3 globals, no rollback) | None | High |
| Email notification | Medium (depends on validation result) | None | Medium |
| Fraud API call | Low (external, commented out) | None | Low |

Order validation scored lowest on coupling and highest on testability — it is
a pure function trapped inside a stateful context. Extracting it first gives us:
1. A safe extraction (no DB migrations, no network changes)
2. An immediate win on the credential and injection security flaws
3. A behavioral contract (characterization tests) that pins all downstream work

---

## What we chose NOT to do

**Not containerizing yet.** The scenario allows it, but packaging a module we just
extracted into a container before the seam is proven adds risk without evidence.
Container extraction is the natural next step once the service runs in production
for one sprint.

**Not using an event bus.** An event-driven architecture would be the right long-term
shape, but it requires the whole team to adopt a new mental model while we're still
learning the legacy domain. We will route synchronous calls through `OrderValidator`
first and revisit async in ADR-002.

**Not extracting inventory writes in the same PR.** The inventory write is the riskiest
part of the legacy code (global dict, no rollback, concurrency issues). We need the
characterization test suite to be green and trusted before we touch it.

**Prompt AND hook for boundary enforcement, not just one.** The `legacy/CLAUDE.md`
prompt is the probabilistic preference ("do not modify"). The `.claude/hooks/guard_legacy.py`
`PreToolUse` hook is the deterministic hard stop — it blocks `Write`, `Edit`, and
`MultiEdit` calls targeting `legacy/` regardless of what the prompt says. Both are wired
in `.claude/settings.json`. The distinction: prompts guide judgment, hooks enforce rules
that must never be overridden. This repo needs the hook because the eval baseline must stay
intact; the prompt alone is insufficient when the cost of a mistake is a corrupted scorecard.

---

## Consequences

**Positive:**
- Characterization tests provide a regression net from day one.
- `OrderValidator` can be unit-tested with no network or DB, in milliseconds.
- The eval scorecard moves from 20/100 to 100/100 on the extracted service.
- Security flaws (credentials, SQL injection) are fully eliminated from the new boundary.

**Negative / risks:**
- The monolith and the new service will diverge if the monolith is patched without
  updating the characterization tests. Mitigation: CI runs both test suites on every commit.
- `ValidationResult` does not yet carry machine-readable error codes (Story 1.4).
  Callers parsing the `reason` string will need an update when codes land.
- Global state in the legacy module is not eliminated — only bypassed. Until the
  inventory write is extracted, concurrent requests against the legacy path can still
  corrupt `INVENTORY`.

---

## References

- `legacy/FLAWS.md` — detailed analysis of the five baseline defects
- `docs/stories.md` — user stories that drove the extraction scope
- `tests/characterization/test_order_logic.py` — behavioral contract
- `tests/eval/score.py` — quality scorecard
