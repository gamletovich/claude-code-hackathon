# Five Documented Flaws — Legacy Order Processor

These are the baseline defects the modernization engagement was hired to fix.
Each flaw is traceable to a specific line range in `src/order_processor.py`.

---

## Flaw 1 — Hardcoded Credentials (lines 18–21)

```python
DB_CONNECTION_STRING = "postgresql://admin:Passw0rd!@prod-db.northwind.internal/orders"
API_KEY = "sk-live-nwl-8f2a91c3d4b5e6f7a8b9c0d1e2f3"
SMTP_PASSWORD = "smtp_NW_2019!"
```

**Risk:** CRITICAL. Any developer with read access to the repo has production credentials.
Rotating them requires a code change, a review, and a deploy. Secret scanners
will flag every commit that touches this file.

**Fix applied in modern code:** All credentials removed. Callers inject configuration;
the validator has no knowledge of connection strings or API keys.

---

## Flaw 2 — SQL Injection (lines 38–42, `get_customer_raw`)

```python
query = f"SELECT * FROM customers WHERE id = '{customer_id}'"
```

`customer_id` comes from untrusted input. An attacker can pass:

```
CUST-001' OR '1'='1
```

and receive every row in the customers table.

**Risk:** HIGH. Full table read for unauthenticated input; with a writable endpoint,
this escalates to data destruction.

**Fix applied in modern code:** No SQL. The `CustomerRepo` protocol accepts a
`customer_id` and returns a typed dict; the implementation uses parameterized
queries or an ORM that prevents injection by construction.

---

## Flaw 3 — Global Mutable State (lines 27–36)

```python
INVENTORY = { ... }   # mutated on every accepted order
CUSTOMERS = { ... }   # balance incremented during "validation"
ORDERS    = []        # appended to on every success
```

Three module-level dicts are shared across all callers with no locking.
Under concurrent load:
- Two threads can both see `qty=1`, both pass the stock check, and both
  decrement to `-1`.
- A failed email send leaves INVENTORY and CUSTOMERS mutated with no rollback.

**Risk:** HIGH. Race conditions under any load; silent data corruption.

**Fix applied in modern code:** `OrderValidator` holds no state. Repos are injected
per-request. The test doubles (`InMemoryInventoryRepo`, `InMemoryCustomerRepo`)
are constructed fresh per test, making state isolation trivial.

---

## Flaw 4 — Deep Nesting (lines 48–95, `process_order`)

The main function reaches **8 levels of indentation**:

```
if order_data:
  if customer_id:
    if customer:
      if customer.get('active'):
        if items:
          for item in items:
            if sku in INVENTORY:
              if stock['qty'] >= qty_requested:  ← level 8
```

Each branch exit requires reading 8 lines of context to understand which
guard failed. Adding a new validation rule means choosing an insertion
point inside the pyramid.

**Risk:** LOW (correctness), HIGH (maintainability). Every engineer who
touches this function extends a bug or misplaces a return.

**Fix applied in modern code:** Early returns flatten the structure to ≤ 3 levels.
Each guard fails fast; the happy path is the last line.

---

## Flaw 5 — Mixed Concerns (throughout `process_order`)

A single function performs four distinct jobs:
1. **Business-rule validation** — credit check, stock check, address presence
2. **State mutation** — `INVENTORY[sku]['qty'] -= qty`, `CUSTOMERS[...]['balance'] +=`
3. **HTTP I/O** — fraud API call (commented out but wired to run in prod)
4. **SMTP I/O** — confirmation email (commented out but wired to run in prod)

This means:
- Validation cannot be tested without triggering side effects.
- The fraud service being down rejects valid orders.
- Adding a new notification channel means editing the validation function.

**Risk:** MEDIUM (correctness), HIGH (maintainability, testability).

**Fix applied in modern code:** `OrderValidator.validate()` does only rule 1.
It returns a `ValidationResult`. The caller decides whether to commit state,
call the fraud service, or send email — and can test each path independently.
