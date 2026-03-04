#!/usr/bin/env python3
"""Compose selected_papers.json from a provided source plus optional supporting literature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_paper(item: dict[str, Any], *, primary: bool) -> dict[str, Any]:
    out = dict(item)
    out.setdefault("id", "UNKNOWN_SOURCE")
    out.setdefault("title", "Untitled")
    out.setdefault("authors", [])
    out.setdefault("year", None)
    out.setdefault("journal", "Unknown")
    out.setdefault("doi_or_url", "")
    out["citation_count"] = int(out.get("citation_count", 0) or 0)
    out["is_high_impact"] = bool(out.get("is_high_impact", False))
    out["open_access"] = bool(out.get("open_access", True))
    out.setdefault("used_for", [])
    out.setdefault("parameter_bindings", {})
    out.setdefault("notes", "")

    used_for = [str(x) for x in out.get("used_for", [])]
    if primary and "primary_protocol_source" not in used_for:
        used_for.insert(0, "primary_protocol_source")
    out["used_for"] = used_for
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose selected papers from provided source and optional supplements.")
    parser.add_argument("--task-path", required=True, help="Task root directory.")
    parser.add_argument(
        "--provided-json",
        default=None,
        help="Path to provided source JSON. Defaults to references/provided_source.json.",
    )
    parser.add_argument(
        "--supplement-json",
        default=None,
        help=(
            "Optional supporting literature JSON list (for example output of select_papers.py). "
            "Defaults to references/selected_papers.json if present."
        ),
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Output selected papers JSON path. Defaults to references/selected_papers.json.",
    )
    parser.add_argument(
        "--min-supporting",
        type=int,
        default=0,
        help="Require at least N supporting papers (excluding the provided primary source).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()
    refs_dir = task_path / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    provided_path = Path(args.provided_json).resolve() if args.provided_json else refs_dir / "provided_source.json"
    output_path = Path(args.output_json).resolve() if args.output_json else refs_dir / "selected_papers.json"
    supplement_path = Path(args.supplement_json).resolve() if args.supplement_json else (refs_dir / "selected_papers.json")

    if not provided_path.exists():
        raise SystemExit(f"Provided source file not found: {provided_path}")

    provided_payload = _load_json(provided_path)
    if isinstance(provided_payload, dict):
        primary = _coerce_paper(provided_payload, primary=True)
    elif isinstance(provided_payload, list) and provided_payload:
        primary = _coerce_paper(dict(provided_payload[0]), primary=True)
    else:
        raise SystemExit("provided_source.json must be an object or non-empty list.")

    supports: list[dict[str, Any]] = []
    if supplement_path.exists():
        supplement_payload = _load_json(supplement_path)
        if not isinstance(supplement_payload, list):
            raise SystemExit("Supplement JSON must be a list of papers.")
        supports = [_coerce_paper(dict(item), primary=False) for item in supplement_payload if isinstance(item, dict)]
        supports.sort(key=lambda p: int(p.get("citation_count", 0)), reverse=True)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for paper in [primary, *supports]:
        pid = str(paper.get("id", "")).strip() or "UNKNOWN_SOURCE"
        if pid in seen:
            continue
        seen.add(pid)
        merged.append(paper)

    supporting_count = max(len(merged) - 1, 0)
    if supporting_count < args.min_supporting:
        raise SystemExit(
            f"Need at least {args.min_supporting} supporting papers, but only {supporting_count} were available."
        )

    output_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[task-build] wrote {output_path}")
    print(f"[task-build] primary_id={primary.get('id')} supporting={supporting_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
