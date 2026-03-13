#!/usr/bin/env python3
"""Verify there are no dependency cycles among sub-issues of a parent issue."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge.linear import fetch_sub_issues


def main():
    if len(sys.argv) < 2:
        print("Usage: check_cycle.py <parent_issue_id>", file=sys.stderr)
        sys.exit(1)

    result = fetch_sub_issues(sys.argv[1])
    cycle = result.get("cycle")

    if cycle:
        print(f"CYCLE DETECTED: {' -> '.join(cycle)}")
        sys.exit(1)
    else:
        print("OK")


if __name__ == "__main__":
    main()
