#!/usr/bin/env python3
"""Build docs ↔ Postman crosslink index."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import docs_kb  # noqa: E402


def main() -> int:
    result = docs_kb.build_crosslinks(save=True)
    stats = result["stats"]
    print(
        f"✓ Crosslinks: {stats['docs_with_postman']} docs with Postman, "
        f"{stats['postman_with_docs']} Postman with docs, "
        f"{stats['total_links']} links"
    )
    if stats["unmatched_docs"]:
        print(f"  Docs without Postman match: {len(stats['unmatched_docs'])}")
    if stats["unmatched_postman"]:
        print(f"  Postman without doc match: {len(stats['unmatched_postman'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
