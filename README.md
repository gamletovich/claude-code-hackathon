# Team Gamletovich

## Participants
- Armen Boiadzhian (PM · Architect · Dev · Tester)

## Scenario
Scenario 1: Code Modernization — "The Monolith"

---

## What We Built

A complete strangler-fig extraction of the order-validation seam from the
Northwind Logistics Python monolith. Everything here was built from scratch
during the hackathon session.

**What runs:**
- `legacy/src/order_processor.py` — the original monolith, preserved with all five
  documented flaws intact (hardcoded credentials, SQL injection, global mutable state,
  8-level nesting, mixed concerns). This file is intentionally broken; the eval harness
  measures it as the "before" state.
- `modern/src/order_validator.py` — the extracted `OrderValidator` service: dependency-
  injected repos, typed `ValidationResult`, pure validation with no side effects,
  max nesting depth 3.
- `tests/characterization/test_order_logic.py` — 14 behavioral tests (7 scenarios × 2
  implementations). The same contract runs against both the legacy and modern code,
  proving behavioral equivalence.
- `tests/eval/score.py` — static analysis scorecard. Legacy scores 20/100; modern scores
  100/100. Exits non-zero in CI if the modern score drops below 95.
- `presentation/index.html` — 10-slide HTML deck with keyboard navigation.

**What's scaffolding / faked:**
- The legacy code's HTTP fraud-check and SMTP calls are commented out with `# In production…`
  comments — they would execute against real endpoints in production. The test harness
  uses the in-memory dict path instead.
- The `InMemoryInventoryRepo` and `InMemoryCustomerRepo` are test doubles. A production
  deployment would swap in SQLAlchemy or PostgreSQL implementations behind the same Protocol.

---

## Challenges Attempted

| # | Challenge | Status | Notes |
|---|-----------|--------|-------|
| 1 | The Stories | Done | 5 stories with acceptance criteria in `docs/stories.md` |
| 2 | The Patient | Done | Legacy monolith generated with 5 documented flaws |
| 3 | The Map | Done | ADR in `docs/adr.md` — seams ranked by coupling and risk |
| 4 | The Pin | Done | 9 characterization scenarios, 18 tests total (legacy + modern) |
| 5 | The Cut | Done | `OrderValidator` extracted, all 18 tests green |
| 6 | The Fence | Done | `PreToolUse` hook blocks `legacy/` writes + CLAUDE.md prompt |
| 7 | The Scorecard | Done | `tests/eval/score.py` — static analysis, legacy 20 → modern 100 |
| 8 | The Weekend | Done | `docs/runbook.md` — cutover runbook with rollback decision tree |
| 9 | The Scouts | Done | `scripts/scouts.py` — 5 parallel subagents, ranked extraction plan |

---

## Key Decisions

**Strangler fig over big-bang rewrite.** The board said "modernize" without a scope.
A 6-month freeze and full rewrite carries enormous risk in a domain with undocumented
behavior. Extract one seam at a time, run old and new in parallel, retire legacy code
incrementally. See `docs/adr.md`.

**Order validation as the first seam.** Ranked against inventory writes and email
notification by coupling, testability, and business risk. Validation was the clear winner:
no DB writes, returns a value, trivially injectable. See `docs/adr.md` for the full ranking.

**Characterization tests before code changes.** We wrote 14 tests against the legacy
monolith before extracting the service. This gave us a regression net with teeth — a
future commit that silently changes validation behavior fails loudly with a precise message.

**Both prompt AND hook for boundary enforcement.** `legacy/CLAUDE.md` says "do not modify"
(probabilistic preference). `.claude/hooks/guard_legacy.py` blocks `Write` and `Edit` calls
targeting `legacy/` mechanically (deterministic guardrail). ADR-001 explains why each
mechanism was chosen and when to use one vs. the other.

---

## How to Run It

No Docker required. Needs Python 3.10+ only.

```bash
# Clone
git clone https://github.com/gamletovich/claude-code-hackathon.git
cd claude-code-hackathon

# Run characterization tests (18 tests: 9 scenarios × 2 implementations)
python -m unittest discover tests/characterization/ -v

# Run eval scorecard
python tests/eval/score.py

# Open the presentation
open presentation/index.html   # macOS
start presentation/index.html  # Windows

# Run the scouts (Challenge 9 — requires Anthropic API key)
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python scripts/scouts.py
```

Expected output from the scorecard:
```
LEGACY   order_processor.py    20 / 100
MODERN   order_validator.py   100 / 100
Delta: 20 → 100  (+80 points)
Verdict: PASS
```

---

## If We Had More Time

1. **Extract InventoryService** — the riskiest seam (global dict mutations, no rollback).
   Needs a saga pattern or two-phase commit before it touches production.
2. **Concrete repos** — swap `InMemoryInventoryRepo` for a PostgreSQL implementation
   behind the same `InventoryRepo` Protocol. The validator doesn't change.
3. **Error codes** — `ValidationResult` currently carries a human-readable reason string.
   Finance's ERP integration needs machine-readable codes (Story 1.4).
4. **PreToolUse hook** — mechanically enforce the `legacy/` boundary so no Claude session
   can accidentally "fix" the monolith and corrupt the eval baseline.
5. **Task subagents (The Scouts)** — fan out one subagent per seam candidate, each scoring
   extraction risk independently, then aggregate into a ranked plan.
6. **Cutover runbook** — the 3am ops guide. What triggers a rollback, who approves, what
   the decision tree looks like. Currently just implied by the ADR.

---

## How We Used Claude Code

**What worked exceptionally well:**
- Three-level `CLAUDE.md` (root → legacy → modern) kept the context scoped per directory.
  Claude never tried to "fix" the intentionally broken legacy code.
- Parallel file writes — the entire deliverable set (monolith, service, tests, eval, ADR,
  stories, deck) was produced in a single session without losing coherence across files.
- The mixin test contract (`OrderProcessorContract`) was suggested by the interaction
  pattern: "write tests that prove equivalence without duplicating them." The multiple
  inheritance approach (`TestLegacyProcessor(OrderProcessorContract, unittest.TestCase)`)
  came out clean on the first try.
- The eval harness as a CI guardrail: framing it as "a script that exits non-zero on
  failure" gave Claude the right shape immediately — no hand-holding needed.

**What surprised us:**
- The `Protocol` typing for repository interfaces was proposed without prompting.
  It's the right pattern (structural subtyping means the test doubles need no explicit
  inheritance), and it made the code cleaner than what we would have written manually.
- The presentation HTML took one pass and needed zero iteration. Dark theme, 10 slides,
  keyboard navigation, score bar animations — all on the first write.

**Where it saved the most time:**
- Archaeology: translating "find 5 realistic security/quality flaws in a 2017 Python
  order-processing script" into specific line-level citations with risk ratings — 5 minutes
  vs. the 30+ it would take to research manually.
- The characterization test structure: designing a pattern that proves behavioral
  equivalence across two implementations without test duplication is a non-trivial
  architecture choice. It was right on the first attempt.
