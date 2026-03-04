#!/usr/bin/env python3
"""Validate and render task_plot_spec v0.2 to PNG."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from task_plot_contract import ValidationError, load_document, validate_and_prepare_spec
from task_plot_renderer import render_task_flow_png


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and render task_plot_spec to PNG.")
    parser.add_argument("--spec", required=True, help="Path to task_plot_spec YAML/JSON.")
    parser.add_argument("--out-png", required=True, help="Output PNG path.")
    parser.add_argument("--dpi", type=int, help="Override output DPI.")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        doc = load_document(args.spec)
        validation = validate_and_prepare_spec(doc)
    except ValidationError as exc:
        print(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] failed to parse spec: {exc}")
        return 1

    if args.validate_only:
        print("[OK] spec valid")
        return 0

    try:
        render_task_flow_png(validation.spec_root, out_png=args.out_png, dpi_override=args.dpi)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] render failed: {exc}")
        return 1

    print(f"[OK] rendered: {args.out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
