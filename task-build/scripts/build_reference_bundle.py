#!/usr/bin/env python3
"""Build references.yaml, references.md, and parameter_mapping.md for a task."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import yaml


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            next_prefix = f"{prefix}.{k}" if prefix else str(k)
            _flatten(next_prefix, v, out)
    else:
        out[prefix] = value


def _md_cell(value: Any) -> str:
    return str(value).replace("|", " ").replace("\n", " ").strip()


def _conditions_from_config(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    task_cfg = payload.get("task", {}) if isinstance(payload, dict) else {}
    conditions = task_cfg.get("conditions", []) if isinstance(task_cfg, dict) else []
    out: list[str] = []
    if isinstance(conditions, list):
        for item in conditions:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
    return out


def _load_selected(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Selected papers file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("selected_papers.json must contain a list")
    return payload


def _load_task_id(task_path: Path) -> str:
    tb = task_path / "taskbeacon.yaml"
    if tb.exists():
        payload = yaml.safe_load(tb.read_text(encoding="utf-8")) or {}
        if payload.get("id"):
            return str(payload["id"])
    return task_path.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create reference artifacts from selected papers.")
    parser.add_argument("--task-path", required=True)
    parser.add_argument("--selected-json", default=None, help="Path to selected_papers.json")
    parser.add_argument(
        "--selection-policy",
        default="tiered_mix_high_impact_plus_high_citation_open_access",
        help="Selection policy label written into references.yaml",
    )
    parser.add_argument("--citation-threshold", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()
    refs_dir = task_path / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    selected_json = Path(args.selected_json).resolve() if args.selected_json else refs_dir / "selected_papers.json"
    selected = _load_selected(selected_json)

    task_id = _load_task_id(task_path)
    generated_at = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    papers_payload: list[dict[str, Any]] = []
    for p in selected:
        papers_payload.append(
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "authors": p.get("authors", []),
                "year": p.get("year"),
                "journal": p.get("journal"),
                "doi_or_url": p.get("doi_or_url"),
                "citation_count": int(p.get("citation_count", 0)),
                "is_high_impact": bool(p.get("is_high_impact", False)),
                "open_access": bool(p.get("open_access", False)),
                "used_for": p.get("used_for", ["task_workflow", "timing_parameters"]),
                "parameter_bindings": p.get("parameter_bindings", {}),
                "notes": p.get("notes", ""),
            }
        )

    references_yaml = {
        "task_id": task_id,
        "generated_at": generated_at,
        "selection_policy": args.selection_policy,
        "citation_threshold": args.citation_threshold,
        "papers": papers_payload,
    }

    references_yaml_path = refs_dir / "references.yaml"
    references_yaml_path.write_text(yaml.safe_dump(references_yaml, sort_keys=False, allow_unicode=True), encoding="utf-8")

    references_md_path = refs_dir / "references.md"
    references_md_lines = [
        "# References",
        "",
        f"- Task ID: `{task_id}`",
        f"- Generated at: `{generated_at}`",
        f"- Selection policy: `{args.selection_policy}`",
        f"- Citation threshold: `{args.citation_threshold}`",
        "",
        "## Selected Papers",
        "",
        "| ID | Year | Citations | Journal | High Impact | Open Access | Title |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for p in papers_payload:
        references_md_lines.append(
            "| {id} | {year} | {citation_count} | {journal} | {impact} | {open_access} | {title} |".format(
                id=_md_cell(p.get("id", "")),
                year=_md_cell(p.get("year", "")),
                citation_count=_md_cell(p.get("citation_count", 0)),
                journal=_md_cell(p.get("journal", "")),
                impact="yes" if p.get("is_high_impact") else "no",
                open_access="yes" if p.get("open_access") else "no",
                title=_md_cell(p.get("title", "")),
            )
        )
    references_md_lines.extend([
        "",
        "## Notes",
        "",
        "- Paywalled papers were skipped by policy.",
        "- Any unresolved protocol values are documented as `inferred` in `parameter_mapping.md`.",
        "",
    ])
    references_md_path.write_text("\n".join(references_md_lines), encoding="utf-8")

    parameter_mapping_path = refs_dir / "parameter_mapping.md"
    rows: list[tuple[str, str, Any, str, str, str, str]] = []
    cfg_path = task_path / "config" / "config.yaml"
    primary_source = papers_payload[0]["id"] if papers_payload else "inferred"
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        flattened: dict[str, Any] = {}
        _flatten("", cfg, flattened)
        for key, value in sorted(flattened.items()):
            key_str = key.strip(".")
            if not key_str:
                continue
            if key_str.startswith("task.") or key_str.startswith("timing.") or key_str.startswith("triggers.map."):
                param_id = key_str.split(".")[-1]
                rows.append(
                    (
                        param_id,
                        key_str,
                        value,
                        str(primary_source),
                        "Protocol-derived parameter; exact citation detail should be curated manually.",
                        "inferred",
                        "Auto-populated from config.yaml; verify against selected papers.",
                    )
                )

    header = [
        "# Parameter Mapping",
        "",
        "## Mapping Table",
        "",
        "| Parameter ID | Config Path | Implemented Value | Source Paper ID | Evidence (quote/figure/table) | Decision Type | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    if not rows:
        header.append(
            "| _none_detected_ | _n/a_ | _n/a_ | _n/a_ | _n/a_ | inferred | Add mappings manually after protocol extraction. |"
        )
    else:
        for param_id, config_path, value, source, evidence, decision_type, notes in rows:
            header.append(
                "| `{param_id}` | `{config_path}` | `{value}` | `{source}` | {evidence} | `{decision_type}` | {notes} |".format(
                    param_id=_md_cell(param_id),
                    config_path=_md_cell(config_path),
                    value=_md_cell(value),
                    source=_md_cell(source),
                    evidence=_md_cell(evidence),
                    decision_type=_md_cell(decision_type),
                    notes=_md_cell(notes),
                )
            )

    parameter_mapping_path.write_text("\n".join(header) + "\n", encoding="utf-8")

    stimulus_mapping_path = refs_dir / "stimulus_mapping.md"
    if not stimulus_mapping_path.exists():
        conditions = _conditions_from_config(cfg_path)
        stim_lines = [
            "# Stimulus Mapping",
            "",
            "Map each implemented condition/stimulus to the selected literature source.",
            "All `UNSET` values must be resolved before publish.",
            "",
            "## Mapping Table",
            "",
            "| Condition | Stage/Phase | Stimulus IDs | Participant-Facing Content | Source Paper ID | Evidence (quote/figure/table) | Implementation Mode | Asset References | Notes |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        if conditions:
            for cond in conditions:
                stim_lines.append(
                    f"| `{cond}` | `UNSET` | `{cond}_cue`, `{cond}_target` | `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` |"
                )
        else:
            stim_lines.append(
                "| `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` | `UNSET` |"
            )
        stim_lines.extend(
            [
                "",
                "Accepted implementation modes:",
                "- `psychopy_builtin`",
                "- `generated_reference_asset`",
                "- `licensed_external_asset`",
                "",
                "Decision rule:",
                "- Participant-facing text should be configured in `config/*.yaml` stimuli and referenced via stimulus IDs.",
                "",
            ]
        )
        stimulus_mapping_path.write_text("\n".join(stim_lines), encoding="utf-8")
    else:
        # Preserve manual curation if file already exists.
        pass

    print(f"[task-build] wrote {references_yaml_path}")
    print(f"[task-build] wrote {references_md_path}")
    print(f"[task-build] wrote {parameter_mapping_path}")
    print(f"[task-build] wrote {stimulus_mapping_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
