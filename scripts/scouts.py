"""
Challenge 9 — The Scouts: Fan-out extraction risk analysis.

Uses Claude as a coordinator with one subagent call per candidate seam,
each independently scoring extraction risk across four dimensions:
  - Coupling (how many other modules depend on this seam)
  - Test coverage (how much behavior is already pinned)
  - Data-model tangle (does this seam own shared tables or globals)
  - Business criticality (impact of a mis-extraction on ops)

Each agent returns a structured verdict. The coordinator aggregates into a
ranked extraction plan and compares against the human ranking in ADR-001.

Usage:
  export ANTHROPIC_API_KEY=sk-...
  python scripts/scouts.py

Requires: pip install anthropic
"""

from __future__ import annotations

import json
import os
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import anthropic
except ImportError:
    raise SystemExit(
        "anthropic package not found. Install it with: pip install anthropic"
    )

# ---------------------------------------------------------------------------
# Seam definitions — candidate services to extract from the monolith
# ---------------------------------------------------------------------------

SEAMS = [
    {
        "name": "OrderValidator",
        "description": (
            "The validation logic in process_order(): customer lookup, credit check, "
            "stock check, address validation. Pure computation — returns accept/reject. "
            "Currently interleaved with inventory mutation and email sending."
        ),
        "location": "legacy/src/order_processor.py — process_order(), get_customer_raw()",
        "current_state": "No tests. Mutates INVENTORY and CUSTOMERS as a side-effect of validation.",
    },
    {
        "name": "InventoryService",
        "description": (
            "Stock reservation and deduction: INVENTORY global dict, qty decrement on "
            "accepted orders. No rollback if a downstream step fails. "
            "Accessed by process_order() mid-loop during item validation."
        ),
        "location": "legacy/src/order_processor.py — INVENTORY global, lines 91-93",
        "current_state": "No tests. Race condition under concurrent load. No rollback path.",
    },
    {
        "name": "CustomerCreditService",
        "description": (
            "Customer lookup and credit-limit enforcement: CUSTOMERS global dict, "
            "balance increment after order acceptance. "
            "get_customer_raw() has SQL injection. Balance is mutated before email send."
        ),
        "location": "legacy/src/order_processor.py — CUSTOMERS global, get_customer_raw()",
        "current_state": "SQL injection in get_customer_raw(). Balance mutation is non-atomic.",
    },
    {
        "name": "FraudDetectionGateway",
        "description": (
            "HTTP call to external fraud API: commented out in current code but wired "
            "to execute in production. API_KEY hardcoded at module level. "
            "A fraud-service outage would reject all valid orders."
        ),
        "location": "legacy/src/order_processor.py — commented block, lines 106-110",
        "current_state": "Currently commented out. Hardcoded API_KEY. No circuit breaker.",
    },
    {
        "name": "NotificationService",
        "description": (
            "SMTP confirmation email: smtplib call commented out but wired for production. "
            "SMTP_PASSWORD hardcoded. Fires after state is committed — failure leaves "
            "order accepted but customer unnotified."
        ),
        "location": "legacy/src/order_processor.py — commented SMTP block, lines 113-118",
        "current_state": "Hardcoded SMTP_PASSWORD. No retry. Inline with business logic.",
    },
]

# ---------------------------------------------------------------------------
# Prompt template for each scout subagent
# ---------------------------------------------------------------------------

SCOUT_PROMPT = """You are an extraction-risk analyst reviewing a legacy Python monolith.
Your job is to score ONE candidate seam for extraction risk, then return a structured JSON verdict.

## The seam you are scoring

Name: {name}
Description: {description}
Location in codebase: {location}
Current state: {current_state}

## Scoring rubric (lower score = easier to extract safely)

Score each dimension 1-5:
- **coupling** (1=isolated, 5=deeply tangled with other modules)
- **test_coverage** (1=well-pinned, 5=zero behavioral tests)
- **data_model_tangle** (1=owns clean data, 5=shared globals or shared tables)
- **business_criticality** (1=low impact if wrong, 5=breaks all orders if mis-extracted)

Compute **total_risk = coupling + test_coverage + data_model_tangle + business_criticality** (range 4-20).

## Output format

Return ONLY valid JSON with this exact shape:
{{
  "seam": "{name}",
  "scores": {{
    "coupling": <int 1-5>,
    "test_coverage": <int 1-5>,
    "data_model_tangle": <int 1-5>,
    "business_criticality": <int 1-5>
  }},
  "total_risk": <int 4-20>,
  "verdict": "<one sentence: extract early / extract with caution / extract last>",
  "key_blocker": "<the single biggest thing that must be resolved before extraction>",
  "safe_to_extract_before": ["<seam name>", ...]
}}

Return only the JSON object — no markdown, no explanation.
"""

# ---------------------------------------------------------------------------
# Scout runner
# ---------------------------------------------------------------------------

def run_scout(client: "anthropic.Anthropic", seam: dict) -> dict:
    """Call Claude once to score a single seam. Returns the parsed verdict."""
    prompt = SCOUT_PROMPT.format(**seam)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",  # fast + cheap for fan-out scouts
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    print("\n=== The Scouts — Fan-out Extraction Risk Analysis ===")
    print(f"Scoring {len(SEAMS)} candidate seams in parallel...\n")

    verdicts: list[dict] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=len(SEAMS)) as pool:
        futures = {pool.submit(run_scout, client, seam): seam["name"] for seam in SEAMS}
        for future in as_completed(futures):
            name = futures[future]
            try:
                verdict = future.result()
                verdicts.append(verdict)
                print(f"  [{verdict['total_risk']:>2}/20 risk]  {name}: {verdict['verdict']}")
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                print(f"  [ERROR]        {name}: {exc}")

    if errors:
        print(f"\n{len(errors)} scout(s) failed. Results may be incomplete.")

    # Sort by total_risk ascending (lowest risk = extract first)
    verdicts.sort(key=lambda v: v["total_risk"])

    print("\n=== Ranked extraction order (lowest risk first) ===\n")
    for rank, v in enumerate(verdicts, 1):
        s = v["scores"]
        print(f"  {rank}. {v['seam']:<28} risk={v['total_risk']:>2}/20")
        print(f"     coupling={s['coupling']} coverage={s['test_coverage']} "
              f"data={s['data_model_tangle']} criticality={s['business_criticality']}")
        print(f"     Blocker : {v['key_blocker']}")
        print()

    print("=== Compare to human ranking (ADR-001) ===\n")
    human_order = [
        "OrderValidator",
        "FraudDetectionGateway",
        "NotificationService",
        "CustomerCreditService",
        "InventoryService",
    ]
    agent_order = [v["seam"] for v in verdicts]

    agreements = sum(1 for i, s in enumerate(agent_order) if i < len(human_order) and s == human_order[i])
    print(f"  Human order  : {' → '.join(human_order)}")
    print(f"  Agent order  : {' → '.join(agent_order)}")
    print(f"  Agreement    : {agreements}/{len(human_order)} positions match\n")

    if agreements < len(human_order):
        print("  Divergences worth reviewing:")
        for i, (h, a) in enumerate(zip(human_order, agent_order)):
            if h != a:
                matching_v = next((v for v in verdicts if v["seam"] == a), None)
                blocker = matching_v["key_blocker"] if matching_v else "unknown"
                print(f"    Position {i+1}: human chose {h!r}, agent chose {a!r}")
                print(f"    Agent reasoning: {blocker}")
        print()

    print("Full verdict JSON written to: scripts/scouts_output.json")
    with open("scripts/scouts_output.json", "w") as f:
        json.dump(verdicts, f, indent=2)


if __name__ == "__main__":
    main()
