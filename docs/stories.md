# User Stories — Northwind Logistics Order Processing

Scenario 1: Code Modernization
Status: Characterization complete, first extraction delivered

---

## Epic: Safe Monolith Extraction

**Context:** Northwind's `process_order` handles order intake, stock reservation,
credit checks, and notifications in a single 80-line function. The board approved
"modernization." Engineering needs a path that doesn't require a big-bang rewrite
and doesn't break the warehouse ops team's daily order flows mid-extraction.

---

### Story 1.1 — Warehouse Operator: Place an Order

**As a** warehouse operator processing an inbound order form,
**I want** the system to accept or reject an order instantly with a clear reason,
**so that** I can tell the customer what's happening without calling IT.

**Acceptance criteria:**
- AC1: A valid order (known customer, items in stock, within credit) returns `status: accepted` and an order reference number within 500ms.
- AC2: A rejected order returns `status: rejected` and a human-readable `reason` that names the exact problem (e.g., "Insufficient stock for SKU-003", not "Order failed").
- AC3: Rejection does not partially commit state (inventory not decremented if credit check fails).
- AC4: A missing or blank `shipping_address` is rejected before any inventory check runs.

**Stakeholder disagreement captured:** Ops wants rejection messages in plain English for customers. Finance wants rejection codes for their ERP integration. Current delivery: plain English reason strings. Codes to follow in Story 1.4.

---

### Story 1.2 — Finance: Credit Limit Enforcement

**As a** finance controller,
**I want** orders to be blocked when they would push a customer past their credit limit,
**so that** we don't ship goods we won't get paid for.

**Acceptance criteria:**
- AC1: `available_credit = credit_limit - balance`; orders where `total > available_credit` are rejected with `"Credit limit exceeded"`.
- AC2: Partially in-stock orders do not reserve any inventory before hitting the credit check.
- AC3: The credit check result is auditable — the order record includes the total and the customer's balance at time of evaluation.

**Note:** Story 1.3 (fraud detection) is a prerequisite for AC3 being meaningful in production.

---

### Story 1.3 — Risk: Fraud Detection Hook

**As a** risk analyst,
**I want** the order validation pipeline to have a designated hook for fraud-check results,
**so that** I can wire in an external fraud service without modifying the validation rules.

**Acceptance criteria:**
- AC1: `OrderValidator.validate()` returns a `ValidationResult` that the caller can pass to a separate `FraudChecker.check(result)` before committing.
- AC2: The fraud check is not called inside `validate()` — it is the caller's responsibility to compose them.
- AC3: A test exists that exercises the full pipeline: validate → fraud-check stub → commit.

**Status:** AC1 and AC2 delivered. AC3 pending (Story 1.5).

---

### Story 1.4 — ERP Integration: Machine-Readable Rejection Codes

**As a** systems integrator connecting Northwind's order system to an ERP,
**I want** rejections to carry a structured error code alongside the human message,
**so that** the ERP can route without parsing free-text strings.

**Acceptance criteria:**
- AC1: `ValidationResult` includes a `code` field (e.g., `CUSTOMER_NOT_FOUND`, `INSUFFICIENT_STOCK`, `CREDIT_EXCEEDED`).
- AC2: The human-readable `reason` field is unchanged.
- AC3: Characterization tests updated to assert codes alongside reasons.

**Status:** Not started. Blocked on stakeholder agreement on code vocabulary.

---

### Story 1.5 — QA: Full Pipeline Smoke Test

**As a** QA engineer running regression after each deployment,
**I want** a single test command that exercises every rejection path end-to-end,
**so that** I don't need to manually step through 7 scenarios after each release.

**Acceptance criteria:**
- AC1: `python -m pytest tests/characterization/ -v` runs all 18 behavioral tests (9 scenarios × 2 implementations) and reports pass/fail within 5 seconds.
- AC2: `python tests/eval/score.py` exits 0 when modern code scores ≥ 95/100.
- AC3: Both commands run without a database, SMTP server, or network access.

**Status:** AC1 and AC2 delivered. AC3 delivered (in-memory repos, no network calls).

---

## Backlog (not started)

| Story | Title | Priority |
|-------|-------|----------|
| 1.6 | Inventory Service extraction (strangler fig step 2) | High |
| 1.7 | Customer Service extraction (strangler fig step 3) | High |
| 1.8 | Rollback on partial failure (saga pattern) | Medium |
| 1.9 | Async order confirmation (replace inline SMTP) | Medium |
| 1.10 | Audit log for every validation outcome | Low |
