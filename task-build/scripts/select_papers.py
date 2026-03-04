#!/usr/bin/env python3
"""Select literature candidates for a PsyFlow task using OpenAlex."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

OPENALEX_WORKS = "https://api.openalex.org/works"


@dataclass
class Paper:
    id: str
    title: str
    authors: list[str]
    year: int | None
    journal: str
    doi_or_url: str
    citation_count: int
    is_high_impact: bool
    open_access: bool
    used_for: list[str]
    parameter_bindings: dict[str, Any]
    notes: str


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_high_impact_names(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Journal whitelist not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: set[str] = set()
    for item in payload.get("journals", []):
        name = item.get("name", "")
        aliases = item.get("aliases", [])
        if name:
            out.add(_normalize(name))
        for alias in aliases:
            out.add(_normalize(str(alias)))
    return out


def _authors_from_work(work: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for a in work.get("authorships", [])[:12]:
        who = (a.get("author") or {}).get("display_name")
        if who:
            authors.append(who)
    return authors


def _paper_from_work(work: dict[str, Any], high_impact_names: set[str]) -> Paper:
    source = ((work.get("primary_location") or {}).get("source") or {})
    journal = source.get("display_name") or "Unknown"
    normalized_journal = _normalize(journal)
    doi = work.get("doi")
    openalex_id = work.get("id") or ""
    paper_id = openalex_id.rsplit("/", 1)[-1] if openalex_id else "unknown"

    return Paper(
        id=paper_id,
        title=work.get("display_name") or "Untitled",
        authors=_authors_from_work(work),
        year=work.get("publication_year"),
        journal=journal,
        doi_or_url=doi or openalex_id,
        citation_count=int(work.get("cited_by_count") or 0),
        is_high_impact=normalized_journal in high_impact_names,
        open_access=bool(((work.get("open_access") or {}).get("is_oa")) is True),
        used_for=["task_workflow", "timing_parameters"],
        parameter_bindings={},
        notes="",
    )


def _build_query(task_name: str, keywords: list[str], acquisition: str | None) -> str:
    terms = [task_name.strip()]
    terms.extend(k.strip() for k in keywords if k.strip())
    if acquisition:
        terms.append(acquisition.strip())
    return " ".join(t for t in terms if t)


def _openalex_search(query: str, *, per_page: int, pages: int, email: str | None) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        params = {
            "search": query,
            "filter": "type:article,is_retracted:false,from_publication_date:1990-01-01",
            "sort": "cited_by_count:desc",
            "per-page": str(per_page),
            "page": str(page),
        }
        if email:
            params["mailto"] = email
        url = f"{OPENALEX_WORKS}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "task-build-skill/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
        items = payload.get("results", [])
        if not items:
            break
        all_results.extend(items)
    return all_results


def _rank_key(p: Paper) -> tuple[int, int, int]:
    return (
        1 if p.is_high_impact else 0,
        p.citation_count,
        1 if p.open_access else 0,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select papers for a task with policy filters.")
    parser.add_argument("--task-name", required=True, help="Canonical task name.")
    parser.add_argument("--task-path", required=True, help="Task root directory.")
    parser.add_argument("--keyword", action="append", default=[], help="Additional keyword (repeatable).")
    parser.add_argument("--acquisition", default=None, help="Modality qualifier, e.g. eeg or fmri.")
    parser.add_argument("--min-citations", type=int, default=100)
    parser.add_argument("--min-selected", type=int, default=3)
    parser.add_argument("--min-high-impact", type=int, default=1)
    parser.add_argument("--max-results", type=int, default=120, help="Maximum OpenAlex hits to process.")
    parser.add_argument("--pages", type=int, default=2, help="OpenAlex pages to fetch.")
    parser.add_argument("--per-page", type=int, default=60, help="OpenAlex page size.")
    parser.add_argument("--email", default=None, help="Optional contact email for OpenAlex mailto parameter.")
    parser.add_argument(
        "--journal-whitelist",
        default=None,
        help="Path to high-impact journal YAML. Defaults to skill references file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()
    refs_dir = task_path / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    whitelist = Path(args.journal_whitelist).resolve() if args.journal_whitelist else (
        Path(__file__).resolve().parent.parent / "references" / "high_impact_psyneuro_journals.yaml"
    )
    high_impact_names = _load_high_impact_names(whitelist)

    query = _build_query(args.task_name, args.keyword, args.acquisition)
    works = _openalex_search(query, per_page=args.per_page, pages=args.pages, email=args.email)

    seen: set[str] = set()
    candidates: list[Paper] = []
    for w in works[: args.max_results]:
        paper = _paper_from_work(w, high_impact_names)
        if paper.id in seen:
            continue
        seen.add(paper.id)
        candidates.append(paper)

    selected = [
        p
        for p in candidates
        if p.open_access and p.citation_count >= args.min_citations
    ]
    selected.sort(key=_rank_key, reverse=True)

    high_impact_count = sum(1 for p in selected if p.is_high_impact)

    candidate_path = refs_dir / "candidate_papers.json"
    selected_path = refs_dir / "selected_papers.json"
    candidate_path.write_text(json.dumps([asdict(p) for p in candidates], indent=2), encoding="utf-8")
    selected_path.write_text(json.dumps([asdict(p) for p in selected], indent=2), encoding="utf-8")

    print(f"[task-build] query={query}")
    print(f"[task-build] candidates={len(candidates)} selected={len(selected)}")
    print(f"[task-build] high_impact_selected={high_impact_count}")
    print(f"[task-build] wrote {candidate_path}")
    print(f"[task-build] wrote {selected_path}")

    if len(selected) < args.min_selected:
        print(
            f"[task-build] FAIL: selected papers ({len(selected)}) below required minimum ({args.min_selected}).",
            file=sys.stderr,
        )
        return 2
    if high_impact_count < args.min_high_impact:
        print(
            f"[task-build] FAIL: high-impact selected papers ({high_impact_count}) below required minimum ({args.min_high_impact}).",
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
