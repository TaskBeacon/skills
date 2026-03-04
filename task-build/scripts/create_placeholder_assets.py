#!/usr/bin/env python3
"""Legacy placeholder generator (disabled by policy)."""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Placeholder generation is disabled. Stimuli must be implemented from references "
            "using PsychoPy built-ins or reference-aligned generated assets."
        )
    )
    parser.add_argument("--task-path", required=False)
    return parser.parse_args()


def main() -> int:
    _ = parse_args()
    msg = (
        "[task-build] ERROR: create_placeholder_assets.py is disabled by policy.\n"
        "[task-build] Use reference-aligned stimulus implementation instead "
        "(PsychoPy primitives or non-placeholder generated assets), and document it in references/stimulus_mapping.md."
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
