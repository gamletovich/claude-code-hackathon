"""
Eval scorecard — static analysis of legacy vs modern code quality.

Scoring dimensions (100 pts total):

  1. Credential safety  (20 pts) — no hardcoded passwords, API keys, or DSNs
  2. Injection safety   (20 pts) — no f-string SQL query construction
  3. State hygiene      (20 pts) — no mutable module-level globals
  4. Structural quality (20 pts) — max nesting depth, type annotations
  5. Baseline quality   (20 pts) — docstrings, consistent return contract

Usage:
  python tests/eval/score.py
"""

import ast
import os
import re
import sys

# Ensure Unicode output works on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LEGACY_FILE = os.path.join(_ROOT, 'legacy', 'src', 'order_processor.py')
MODERN_FILE = os.path.join(_ROOT, 'modern', 'src', 'order_validator.py')

# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

_CRED_PATTERNS = [
    re.compile(r'(?i)password\s*=\s*["\'][^"\']{4,}["\']'),
    re.compile(r'(?i)api_key\s*=\s*["\'][^"\']{4,}["\']'),
    re.compile(r'(?i)connection_string\s*=\s*["\'][^"\']{4,}["\']'),
    re.compile(r'(?i)smtp_password\s*=\s*["\'][^"\']{4,}["\']'),
    re.compile(r'(?i)secret\s*=\s*["\'][^"\']{4,}["\']'),
]

_SQL_INJECT = re.compile(
    r'f["\'].*?(?:SELECT|INSERT|UPDATE|DELETE|WHERE)\b.*?\{[^}]+\}',
    re.IGNORECASE | re.DOTALL,
)


def _count_hardcoded_creds(source: str) -> list:
    found = []
    for pat in _CRED_PATTERNS:
        for m in pat.finditer(source):
            found.append(m.group(0)[:60])
    return found


def _has_sql_injection(source: str) -> bool:
    return bool(_SQL_INJECT.search(source))


def _count_mutable_globals(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    count = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                count += 1
    return count


def _max_nesting_depth(source: str) -> int:
    max_depth = 0
    for line in source.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(line) - len(stripped)
        depth = indent // 4
        max_depth = max(max_depth, depth)
    return max_depth


def _has_type_annotations(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                return True
            if any(a.annotation for a in node.args.args):
                return True
    return False


def _has_module_docstring(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    )


def _has_function_docstrings(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ):
                return True
    return False


def _has_consistent_return(source: str) -> bool:
    return bool(re.search(r'["\']status["\']', source))


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def score_file(path: str) -> tuple:
    """Return (total_score, breakdown_dict, findings_list)."""
    with open(path, encoding='utf-8') as f:
        source = f.read()

    findings = []
    breakdown = {}

    # 1. Credential safety (20 pts)
    creds = _count_hardcoded_creds(source)
    cred_score = max(0, 20 - len(creds) * 7)
    if creds:
        for c in creds:
            findings.append(f"  [CRED]   hardcoded secret: {c!r}")
    breakdown['credential_safety'] = cred_score

    # 2. Injection safety (20 pts)
    if _has_sql_injection(source):
        inject_score = 0
        findings.append("  [INJECT] f-string SQL construction detected")
    else:
        inject_score = 20
    breakdown['injection_safety'] = inject_score

    # 3. State hygiene (20 pts)
    globals_count = _count_mutable_globals(source)
    state_score = max(0, 20 - globals_count * 7)
    if globals_count:
        findings.append(f"  [STATE]  {globals_count} mutable module-level global(s)")
    breakdown['state_hygiene'] = state_score

    # 4. Structural quality (20 pts)
    # Threshold ≤ 4 accounts for class + method + for + if (perfectly reasonable structure)
    depth = _max_nesting_depth(source)
    if depth <= 4:
        depth_score = 15
    elif depth <= 6:
        depth_score = 10
    elif depth <= 8:
        depth_score = 5
    else:
        depth_score = 0
        findings.append(f"  [NEST]   max nesting depth {depth} (threshold: <=4 for full score)")
    if depth > 4:
        findings.append(f"  [NEST]   max nesting depth: {depth}")

    type_score = 5 if _has_type_annotations(source) else 0
    if not _has_type_annotations(source):
        findings.append("  [TYPES]  no type annotations found")

    struct_score = depth_score + type_score
    breakdown['structural_quality'] = struct_score

    # 5. Baseline quality (20 pts)
    doc_module = 5 if _has_module_docstring(source) else 0
    doc_func   = 5 if _has_function_docstrings(source) else 0
    ret_shape  = 5 if _has_consistent_return(source) else 0
    # No bare except (bare except: pass swallows errors silently)
    bare_except = 5 if 'except:' not in source else 0
    baseline_score = doc_module + doc_func + ret_shape + bare_except
    breakdown['baseline_quality'] = baseline_score

    total = cred_score + inject_score + state_score + struct_score + baseline_score
    return total, breakdown, findings


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(label: str, path: str) -> int:
    total, breakdown, findings = score_file(path)

    bar_full  = '█' * (total // 5)
    bar_empty = '░' * ((100 - total) // 5)
    bar = bar_full + bar_empty

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"  {os.path.relpath(path, _ROOT)}")
    print(f"{'=' * 60}")
    print(f"\n  SCORE: {total:3d} / 100   [{bar}]")
    print()
    print(f"  {'Dimension':<25} {'Score':>5}  {'Max':>4}")
    print(f"  {'-'*35}")
    dims = [
        ('credential_safety',  20),
        ('injection_safety',   20),
        ('state_hygiene',      20),
        ('structural_quality', 20),
        ('baseline_quality',   20),
    ]
    for key, max_pts in dims:
        pts = breakdown[key]
        marker = '✓' if pts == max_pts else '✗'
        print(f"  {marker} {key.replace('_', ' ').title():<24} {pts:>5}  /{max_pts:>3}")

    if findings:
        print(f"\n  Issues found:")
        for f in findings:
            print(f)
    else:
        print("\n  No issues found — clean score!")

    return total


def main():
    print("\n" + "=" * 48)
    print("  Northwind Logistics -- Code Quality Eval")
    print("  Scenario 1: Code Modernization")
    print("=" * 48)

    legacy_score = print_report("LEGACY  (before extraction)", LEGACY_FILE)
    modern_score = print_report("MODERN  (after extraction)", MODERN_FILE)

    delta = modern_score - legacy_score
    print(f"\n{'=' * 60}")
    print(f"  Delta: {legacy_score} → {modern_score}  (+{delta} points)")
    verdict = "PASS" if modern_score >= 95 else "FAIL"
    print(f"  Verdict: {verdict} (modern must score ≥ 95)")
    print(f"{'=' * 60}\n")

    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
