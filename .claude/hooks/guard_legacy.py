#!/usr/bin/env python3
"""
PreToolUse hook: block any write to legacy/ directory.

Claude Code fires this before Write or Edit tool calls.
Stdin: JSON with tool_name and tool_input.
Stdout: {"decision": "block", "reason": "..."} to block, or nothing to allow.

This is the mechanical half of the fence described in ADR-001.
The CLAUDE.md prompt is the preference; this hook is the hard stop.
"""
import json
import sys


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Cannot parse — allow and let Claude handle it
        sys.exit(0)

    tool_input = payload.get("tool_input", payload)
    file_path = str(tool_input.get("file_path", ""))

    # Normalize separators so both / and \ work on Windows and Linux
    normalized = file_path.replace("\\", "/")

    if "/legacy/" in normalized or normalized.endswith("/legacy"):
        print(json.dumps({
            "decision": "block",
            "reason": (
                "legacy/ is a read-only reference baseline — writes are blocked by the "
                "PreToolUse hook (see .claude/hooks/guard_legacy.py and ADR-001). "
                "The five flaws in order_processor.py must remain intact for the eval "
                "scorecard to have a valid 'before' state. "
                "If you need to document a finding, add it to docs/ or legacy/FLAWS.md "
                "via a non-hook path (it already exists and is writable)."
            ),
        }))

    # All other paths: allow silently
    sys.exit(0)


if __name__ == "__main__":
    main()
