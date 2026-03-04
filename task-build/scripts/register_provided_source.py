#!/usr/bin/env python3
"""Register a user-provided protocol source (PDF/URL/method text) for task-build."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def _read_methods_text(methods_file: Path | None, methods_text: str | None) -> str:
    chunks: list[str] = []
    if methods_file is not None:
        chunks.append(methods_file.read_text(encoding="utf-8"))
    if methods_text:
        chunks.append(methods_text.strip())
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def _copy_into_refs(src: Path, refs_provided_dir: Path) -> Path:
    refs_provided_dir.mkdir(parents=True, exist_ok=True)
    dest = refs_provided_dir / src.name
    shutil.copy2(src, dest)
    return dest


def _default_title(args: argparse.Namespace, paper_pdf: Path | None) -> str:
    if args.title:
        return args.title.strip()
    if paper_pdf is not None:
        return paper_pdf.stem.replace("_", " ").replace("-", " ").strip() or "User provided source"
    if args.paper_url:
        return args.paper_url.strip()
    return "User provided methods source"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register provided protocol evidence for reference bundle generation.")
    parser.add_argument("--task-path", required=True, help="Task root directory.")
    parser.add_argument("--paper-url", default=None, help="Source paper URL or DOI URL.")
    parser.add_argument("--paper-pdf", default=None, help="Path to local PDF file.")
    parser.add_argument("--methods-file", default=None, help="Path to local methods text/markdown file.")
    parser.add_argument("--methods-text", default=None, help="Inline methods description text.")
    parser.add_argument("--id", default="USER_PROVIDED_001", help="Paper/source ID to write.")
    parser.add_argument("--title", default=None, help="Optional source title.")
    parser.add_argument("--year", type=int, default=None, help="Optional publication year.")
    parser.add_argument("--journal", default="User Provided", help="Journal/source venue label.")
    parser.add_argument("--citation-count", type=int, default=0, help="Citation count when known.")
    parser.add_argument(
        "--open-access",
        choices=["yes", "no"],
        default="yes",
        help="Whether provided source is open access.",
    )
    parser.add_argument(
        "--used-for",
        action="append",
        default=None,
        help="Used-for tags (repeatable). Defaults to primary protocol tags.",
    )
    parser.add_argument(
        "--notes",
        default="Primary protocol source provided by user.",
        help="Notes written into provided source record.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()
    refs_dir = task_path / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    refs_provided_dir = refs_dir / "provided"

    paper_pdf = Path(args.paper_pdf).resolve() if args.paper_pdf else None
    methods_file = Path(args.methods_file).resolve() if args.methods_file else None

    if paper_pdf is None and not args.paper_url and methods_file is None and not args.methods_text:
        raise SystemExit("At least one of --paper-url, --paper-pdf, --methods-file, or --methods-text is required.")
    if paper_pdf is not None and not paper_pdf.exists():
        raise SystemExit(f"--paper-pdf not found: {paper_pdf}")
    if methods_file is not None and not methods_file.exists():
        raise SystemExit(f"--methods-file not found: {methods_file}")

    copied_pdf: Path | None = None
    if paper_pdf is not None:
        copied_pdf = _copy_into_refs(paper_pdf, refs_provided_dir)

    methods_payload = _read_methods_text(methods_file, args.methods_text)
    methods_path: Path | None = None
    if methods_payload:
        methods_path = refs_dir / "provided_methods.md"
        methods_path.write_text(methods_payload + "\n", encoding="utf-8")

    title = _default_title(args, paper_pdf)
    locator = args.paper_url.strip() if args.paper_url else ""
    if not locator and copied_pdf is not None:
        locator = str(copied_pdf.relative_to(task_path)).replace("\\", "/")
    if not locator and methods_path is not None:
        locator = str(methods_path.relative_to(task_path)).replace("\\", "/")

    source_kinds: list[str] = []
    if args.paper_url:
        source_kinds.append("url")
    if copied_pdf is not None:
        source_kinds.append("pdf")
    if methods_path is not None:
        source_kinds.append("methods_text")
    source_kind = "+".join(source_kinds) if source_kinds else "unknown"

    used_for = args.used_for or ["primary_protocol_source", "task_workflow", "stimulus_specification", "timing_parameters"]

    provided_record: dict[str, Any] = {
        "id": str(args.id),
        "title": title,
        "authors": [],
        "year": args.year,
        "journal": args.journal,
        "doi_or_url": locator,
        "citation_count": int(args.citation_count),
        "is_high_impact": False,
        "open_access": args.open_access == "yes",
        "used_for": used_for,
        "parameter_bindings": {},
        "notes": args.notes,
        "source_kind": source_kind,
        "source_locator": locator,
        "attachments": {
            "paper_pdf": str(copied_pdf.relative_to(task_path)).replace("\\", "/") if copied_pdf is not None else None,
            "methods_path": str(methods_path.relative_to(task_path)).replace("\\", "/") if methods_path is not None else None,
        },
    }

    out_path = refs_dir / "provided_source.json"
    out_path.write_text(json.dumps(provided_record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[task-build] wrote {out_path}")
    if copied_pdf is not None:
        print(f"[task-build] copied pdf -> {copied_pdf}")
    if methods_path is not None:
        print(f"[task-build] wrote methods -> {methods_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
