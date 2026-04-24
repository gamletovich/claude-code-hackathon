# Cutover Runbook — OrderValidator Production Deployment

**Version:** 1.0
**Scenario:** Strangler-fig step 1 — routing order validation through the new service
**Audience:** On-call engineer performing the cutover (3am-safe)
**Rehearsal status:** Dry-run required before first production execution

---

## Prerequisites (verify before starting)

- [ ] `main` branch CI is green (18 tests pass, scorecard ≥ 95)
- [ ] `OrderValidator` package deployed to staging and smoke-tested
- [ ] Rollback artifact (previous package version) pinned and accessible
- [ ] Database connection strings available via environment (not hardcoded)
- [ ] On-call secondary notified and available on Slack
- [ ] Incident channel `#northwind-cutover` open

---

## Step 1 — Deploy the new service (T+0)

```bash
# Deploy OrderValidator alongside the monolith (do NOT retire legacy yet)
./deploy.sh --service order-validator --env production --version $(cat VERSION)

# Verify the service is up
curl -s http://order-validator.northwind.internal/health | python -m json.tool
# Expected: {"status": "ok", "version": "..."}
```

**Rollback trigger:** If the health check fails after 2 minutes → go to Step 5.

---

## Step 2 — Enable shadow mode (T+5 min)

Route a copy of all incoming orders to `OrderValidator` for comparison,
without affecting the monolith's response to customers.

```bash
# Enable shadow traffic — 100% of orders go to both paths
./feature-flag set order_validator_shadow=true --env production

# Watch disagreement rate in logs (should be 0% for known order patterns)
./logs tail --service order-validator --filter "shadow_disagree" --minutes 5
```

**Decision point:**
| Disagreement rate | Action |
|---|---|
| 0% | Proceed to Step 3 |
| < 1% | Investigate specific mismatches before proceeding (see Appendix A) |
| ≥ 1% | Stop. Disable shadow. Escalate to engineering lead. |

**Rollback trigger:** Disagreement rate ≥ 1% → go to Step 5.

---

## Step 3 — Canary cutover: 10% of traffic (T+15 min)

```bash
# Route 10% of order validation calls to the new service
./feature-flag set order_validator_percentage=10 --env production

# Monitor for 10 minutes
./metrics watch --dashboard northwind-orders --duration 10m
```

**Pass criteria (all must hold for the full 10 minutes):**
- [ ] Error rate on `/api/orders` ≤ baseline + 0.1%
- [ ] p99 latency on `/api/orders` ≤ baseline + 50ms
- [ ] Zero `CREDIT_EXCEEDED` false positives (check Finance alert channel)
- [ ] Zero inventory desync events (check `#northwind-inventory-alerts`)

**Rollback trigger:** Any criterion fails → go to Step 5.

---

## Step 4 — Full cutover (T+30 min)

```bash
# Ramp to 100%
./feature-flag set order_validator_percentage=100 --env production

# Run smoke test against production
python scripts/smoke_test.py --env production --customer CUST-SMOKE-01

# Monitor for 30 minutes before declaring success
./metrics watch --dashboard northwind-orders --duration 30m
```

**Success declaration:** All Step 3 criteria hold for 30 minutes at 100%.
Notify `#northwind-cutover` and update incident ticket as resolved.

---

## Step 5 — Rollback procedure

Run this if **any** step above hits its rollback trigger.

```bash
# Immediately drop new service traffic to 0%
./feature-flag set order_validator_percentage=0 --env production
./feature-flag set order_validator_shadow=false --env production

# Verify monolith is handling 100% of traffic
./metrics watch --dashboard northwind-orders --duration 2m

# Confirm no orders dropped during the rollback window
./logs query --service orders-api \
  --filter "status=error" \
  --from "$(date -d '-5 minutes' +%s)" \
  --to "$(date +%s)"
```

**After rollback:**
1. Page engineering lead (even at 3am — this is the agreed SLA)
2. Collect disagreement logs from shadow mode for analysis
3. Do NOT retry the cutover until root cause is identified and a new characterization test pins the mismatch

---

## Decision tree

```
Start cutover
    │
    ├─ Health check fails?          ──YES──► Rollback (Step 5) → page lead
    │
    ├─ Shadow disagree rate ≥ 1%?   ──YES──► Rollback (Step 5) → investigate mismatch
    │
    ├─ Canary metrics degrade?      ──YES──► Rollback (Step 5) → page lead
    │
    └─ All good at 100% for 30min?  ──YES──► Declare success ✓
```

---

## Appendix A — Investigating shadow disagreements

A disagreement means the monolith accepted an order the new service would reject,
or vice versa.

**Common causes:**

| Symptom | Likely cause | Resolution |
|---------|-------------|------------|
| New service rejects, monolith accepts | Credit check rounding differs | Compare `available_credit` calculation; check floating-point accumulation |
| New service accepts, monolith rejects | Global state leak in monolith (stale INVENTORY) | Run characterization test suite — a failure here means a pinned behavior changed |
| Disagreement only on multi-item orders | Line-item rounding divergence | See `order_validator.py:_validate_items` — round each line before accumulating |
| Disagreement on inactive customer | CUSTOMERS global mutated mid-request | Race condition in legacy code; new service is correct |

For each disagreement:
1. Capture the raw order payload from the shadow log
2. Replay it against both implementations locally using the characterization test harness
3. If the new service is wrong: add a failing test, fix, re-deploy
4. If the legacy code is wrong (and the new behavior is correct): document in ADR-001 addendum, notify Finance

---

## Rehearsal checklist

Run this dry-run in staging before the production cutover:

- [ ] Deploy to staging and verify health endpoint
- [ ] Enable shadow mode — generate 100 test orders and confirm 0% disagreement
- [ ] Run canary at 10% — verify metrics dashboard updates correctly
- [ ] Simulate a disagreement: inject a test order with a known mismatch, confirm alert fires
- [ ] Execute rollback procedure — confirm traffic drops to 0% within 60 seconds
- [ ] Confirm smoke test runs cleanly at each stage
- [ ] Time the full procedure (target: ≤ 60 minutes including decision points)
