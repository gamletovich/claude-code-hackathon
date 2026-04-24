# CLAUDE.md — modern/

## What this directory is

The extraction target. Every file here should be production-ready:
clean, tested, dependency-injected, and scoreable at 100/100 by the eval harness.

## Conventions

- **No globals.** All state lives in injected repositories.
- **No hardcoded values.** Configuration comes from caller or environment.
- **Early returns.** Max nesting depth 3; no pyramid-of-doom control flow.
- **Typed results.** Public methods return typed classes, not bare dicts.
- **Side-effect-free validation.** `validate()` reads, never writes.

## What belongs here

| Path | Purpose |
|------|---------|
| `src/order_validator.py` | Extracted `OrderValidator` service |
| `src/<future_service>.py` | Next extraction candidates (inventory, customer, fraud) |

## What does NOT belong here

- Any `import` from `legacy/` (the anti-corruption layer is the test contract)
- Any hardcoded DB strings, passwords, or API keys
- Functions longer than 40 lines
- Nesting deeper than 3 levels

## Extension pattern

When adding a new service:
1. Define a `Protocol` for each external dependency
2. Implement an `InMemory*` test double alongside the real implementation
3. Write characterization tests that pass against the legacy equivalent first
4. Ensure `tests/eval/score.py` awards 100/100 before merging
