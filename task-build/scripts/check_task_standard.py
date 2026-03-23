#!/usr/bin/env python3
"""Check whether a task matches PsyFlow/TAPS structural and stimulus-fidelity standards."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FILES = [
    "main.py",
    "src/run_trial.py",
    "config/config.yaml",
    "config/config_qa.yaml",
    "config/config_scripted_sim.yaml",
    "config/config_sampler_sim.yaml",
    "responders/__init__.py",
    "responders/task_sampler.py",
    "README.md",
    "CHANGELOG.md",
    "taskbeacon.yaml",
    ".gitignore",
    "references/references.yaml",
    "references/references.md",
    "references/parameter_mapping.md",
    "references/stimulus_mapping.md",
    "references/task_logic_audit.md",
]

FORBIDDEN_TOKENS = ("placeholder", "dummy", "todo")
REQUIRED_README_HEADINGS = (
    "## 1. Task Overview",
    "## 2. Task Flow",
    "## 3. Configuration Summary",
    "## 4. Methods (for academic publication)",
)
RECOMMENDED_README_SUBHEADINGS = (
    "### Block-Level Flow",
    "### Trial-Level Flow",
    "### Controller Logic",
    "### a. Subject Info",
    "### b. Window Settings",
    "### c. Stimuli",
    "### d. Timing",
)
REFERENCE_REQUIRED_HEADINGS: dict[str, tuple[str, ...]] = {
    "references/references.md": (
        "# References",
        "## Selected Papers",
    ),
    "references/parameter_mapping.md": (
        "# Parameter Mapping",
        "## Mapping Table",
    ),
    "references/stimulus_mapping.md": (
        "# Stimulus Mapping",
        "## Mapping Table",
    ),
    "references/task_logic_audit.md": (
        "## 1. Paradigm Intent",
        "## 2. Block/Trial Workflow",
        "## 3. Condition Semantics",
        "## 4. Response and Scoring Rules",
        "## 5. Stimulus Layout Plan",
        "## 6. Trigger Plan",
        "## 7. Architecture Decisions (Auditability)",
        "## 8. Inference Log",
    ),
}
REFERENCE_REQUIRED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "references/references.md": (
        "ID",
        "Year",
        "Citations",
        "Journal",
        "High Impact",
        "Open Access",
        "Title",
    ),
    "references/parameter_mapping.md": (
        "Parameter ID",
        "Config Path",
        "Implemented Value",
        "Source Paper ID",
        "Evidence (quote/figure/table)",
        "Decision Type",
        "Notes",
    ),
    "references/stimulus_mapping.md": (
        "Condition",
        "Stage/Phase",
        "Stimulus IDs",
        "Participant-Facing Content",
        "Source Paper ID",
        "Evidence (quote/figure/table)",
        "Implementation Mode",
        "Asset References",
        "Notes",
    ),
}
REFERENCE_FORBIDDEN_MARKERS: dict[str, tuple[str, ...]] = {
    "references/stimulus_mapping.md": ("UNSET", "TODO", "required_review"),
}
TEMPLATE_TEXT_SNIPPETS = (
    "respond as quickly and accurately as possible",
    "press space to continue",
    "press space to quit",
)
PLACEHOLDER_CUE_TARGET_RE = re.compile(r"^\s*(cue|target)\s*[:：]\s*[a-z0-9_\-\s]+\s*$", flags=re.IGNORECASE)
MOJIBAKE_SEQ_RE = re.compile(r"(?:Ã.|Â.|â.|ð.)")
MOJIBAKE_CHAR_MARKERS = ("Ã", "Â", "â", "ð", "�")
TASK_FLOW_HEADING_RE = re.compile(r"^\s*##\s+2\.\s*Task Flow\s*$", flags=re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"^\s*##\s+")


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected dictionary YAML in {path}")
    return payload


def _validate_task_flow_embed(readme_text: str, image_name: str = "task_flow.png") -> str | None:
    lines = readme_text.splitlines()
    heading_idx = next((i for i, line in enumerate(lines) if TASK_FLOW_HEADING_RE.match(line)), None)
    if heading_idx is None:
        return "README.md missing required heading: ## 2. Task Flow"

    section_start = heading_idx + 1
    section_end = len(lines)
    for i in range(section_start, len(lines)):
        if SECTION_HEADING_RE.match(lines[i]):
            section_end = i
            break

    section_lines = lines[section_start:section_end]
    first_non_empty = next((line.strip() for line in section_lines if line.strip()), None)
    expected = f"![Task Flow]({image_name})"
    if first_non_empty != expected:
        return (
            f"{image_name} exists but README.md section '## 2. Task Flow' must start with "
            f"'{expected}'"
        )
    return None


def _contains_forbidden_token(text: str) -> str | None:
    lower = text.lower()
    for token in FORBIDDEN_TOKENS:
        if token in lower:
            return token
    return None


def _normalize_label(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def _normalize_md_col(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _extract_md_table_headers(text: str) -> list[list[str]]:
    headers: list[list[str]] = []
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        head = lines[i].strip()
        sep = lines[i + 1].strip()
        if not (head.startswith("|") and sep.startswith("|")):
            continue
        if not re.match(r"^\|\s*:?-{2,}", sep):
            continue
        cols = [c.strip() for c in head.strip("|").split("|")]
        if cols:
            headers.append(cols)
    return headers


def _md_has_columns(text: str, required: tuple[str, ...]) -> bool:
    if not required:
        return True
    required_norm = {_normalize_md_col(c) for c in required}
    for header in _extract_md_table_headers(text):
        header_norm = {_normalize_md_col(c) for c in header}
        if required_norm.issubset(header_norm):
            return True
    return False


def _ast_is_nonempty_str(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(node.value.strip())


def _check_run_trial_localization(run_trial_path: Path, failures: list[str]) -> None:
    text = run_trial_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        failures.append("src/run_trial.py could not be parsed for localization checks")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn_name = ""
            if isinstance(node.func, ast.Name):
                fn_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fn_name = node.func.attr

            if fn_name in {"TextStim", "TextBox2", "TextBox"}:
                for kw in node.keywords:
                    if kw.arg == "text" and _ast_is_nonempty_str(kw.value):
                        failures.append(
                            "src/run_trial.py hardcodes participant text via TextStim/TextBox constructor; "
                            "move text to config stimuli and load via StimBank"
                        )
                        break

            if isinstance(node.func, ast.Attribute) and node.func.attr == "setText":
                if node.args and _ast_is_nonempty_str(node.args[0]):
                    failures.append(
                        "src/run_trial.py uses setText(...) with a literal string; "
                        "move participant text to config stimuli"
                    )

        if isinstance(node, ast.Assign):
            if _ast_is_nonempty_str(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "text":
                        failures.append(
                            "src/run_trial.py assigns literal text to .text at runtime; "
                            "move participant text to config stimuli"
                        )
                        break


def _stim_asset_path(spec: dict[str, Any], stim_type: str) -> str | None:
    if stim_type == "image":
        keys = ("image", "file", "filename")
    elif stim_type == "movie":
        keys = ("movie", "file", "filename")
    elif stim_type == "sound":
        keys = ("file", "sound", "filename")
    else:
        return None
    for k in keys:
        v = spec.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _check_asset_backed_stimuli(cfg: dict[str, Any], *, cfg_name: str, task_path: Path, failures: list[str]) -> None:
    stimuli = cfg.get("stimuli", {}) if isinstance(cfg, dict) else {}
    if not isinstance(stimuli, dict):
        failures.append(f"{cfg_name}: stimuli section must be a dict")
        return

    for stim_id, spec in stimuli.items():
        if not isinstance(spec, dict):
            continue
        stim_type = str(spec.get("type", "")).strip().lower()
        if stim_type not in {"image", "movie", "sound"}:
            continue
        asset_rel = _stim_asset_path(spec, stim_type)
        if not asset_rel:
            failures.append(f"{cfg_name}: stimulus '{stim_id}' ({stim_type}) missing asset path field")
            continue

        if _contains_forbidden_token(asset_rel):
            failures.append(f"{cfg_name}: stimulus '{stim_id}' uses forbidden asset token in path: {asset_rel}")

        asset_path = task_path / asset_rel
        if not asset_path.exists():
            failures.append(f"{cfg_name}: stimulus '{stim_id}' asset file not found: {asset_rel}")


def _check_text_stimulus_fidelity(
    cfg: dict[str, Any],
    *,
    cfg_name: str,
    condition_labels: set[str],
    failures: list[str],
) -> None:
    stimuli = cfg.get("stimuli", {}) if isinstance(cfg, dict) else {}
    if not isinstance(stimuli, dict):
        return

    for stim_id, spec in stimuli.items():
        if not isinstance(spec, dict):
            continue
        stim_type = str(spec.get("type", "")).strip().lower()
        if stim_type not in {"text", "textbox"}:
            continue

        raw_text = spec.get("text")
        if not isinstance(raw_text, str):
            continue
        text = raw_text.strip()
        if not text:
            continue

        norm = _normalize_label(text)
        if not norm:
            continue

        if PLACEHOLDER_CUE_TARGET_RE.match(text):
            failures.append(
                f"{cfg_name}: stimulus '{stim_id}' uses placeholder cue/target text '{text}'"
            )

        if norm in condition_labels:
            failures.append(
                f"{cfg_name}: stimulus '{stim_id}' text is raw condition label '{text}'"
            )

        for snippet in TEMPLATE_TEXT_SNIPPETS:
            if snippet in norm and len(norm.split()) <= 24:
                failures.append(
                    f"{cfg_name}: stimulus '{stim_id}' contains template instruction text '{snippet}'"
                )


def _garbled_reason(text: str) -> str | None:
    if not text:
        return None
    if "\ufffd" in text:
        return "contains replacement character U+FFFD"
    if "??" in text or text.count("?") >= 3:
        return "contains repeated '?' characters"
    if any(ch in text for ch in MOJIBAKE_CHAR_MARKERS) and MOJIBAKE_SEQ_RE.search(text):
        return "contains likely mojibake sequence"
    return None


def _check_text_encoding_quality(cfg: dict[str, Any], *, cfg_name: str, failures: list[str]) -> None:
    subinfo_mapping = cfg.get("subinfo_mapping", {}) if isinstance(cfg, dict) else {}
    if isinstance(subinfo_mapping, dict):
        for key, value in subinfo_mapping.items():
            if isinstance(value, str):
                reason = _garbled_reason(value)
                if reason:
                    failures.append(f"{cfg_name}: subinfo_mapping['{key}'] {reason}")

    stimuli = cfg.get("stimuli", {}) if isinstance(cfg, dict) else {}
    if not isinstance(stimuli, dict):
        return
    for stim_id, spec in stimuli.items():
        if not isinstance(spec, dict):
            continue
        stim_type = str(spec.get("type", "")).strip().lower()
        if stim_type not in {"text", "textbox"}:
            continue
        text = spec.get("text")
        if not isinstance(text, str):
            continue
        reason = _garbled_reason(text)
        if reason:
            failures.append(f"{cfg_name}: stimulus '{stim_id}' text {reason}")


def _check_reference_artifacts(task_path: Path, failures: list[str]) -> None:
    refs_yaml_path = task_path / "references" / "references.yaml"
    try:
        refs_yaml = _load_yaml(refs_yaml_path)
    except Exception as exc:
        failures.append(f"references/references.yaml parse error: {exc}")
        refs_yaml = {}

    required_top = ("task_id", "generated_at", "selection_policy", "citation_threshold", "papers")
    for key in required_top:
        if key not in refs_yaml:
            failures.append(f"references/references.yaml missing required key: {key}")

    papers = refs_yaml.get("papers")
    if not isinstance(papers, list) or not papers:
        failures.append("references/references.yaml must include non-empty papers list")
    else:
        paper_required = (
            "id",
            "title",
            "year",
            "journal",
            "doi_or_url",
            "citation_count",
            "open_access",
            "is_high_impact",
            "used_for",
        )
        for i, paper in enumerate(papers):
            if not isinstance(paper, dict):
                failures.append(f"references/references.yaml papers[{i}] must be a mapping")
                continue
            for key in paper_required:
                if key not in paper:
                    failures.append(f"references/references.yaml papers[{i}] missing key: {key}")

    for rel, headings in REFERENCE_REQUIRED_HEADINGS.items():
        path = task_path / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        for heading in headings:
            if heading not in text:
                failures.append(f"{rel} missing required heading: {heading}")

    for rel, cols in REFERENCE_REQUIRED_TABLE_COLUMNS.items():
        path = task_path / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not _md_has_columns(text, cols):
            failures.append(f"{rel} missing required table columns: {list(cols)}")

    for rel, markers in REFERENCE_FORBIDDEN_MARKERS.items():
        path = task_path / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in markers:
            if re.search(rf"\b{re.escape(marker)}\b", text):
                failures.append(f"{rel} contains unresolved marker '{marker}'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate task standard layout and patterns.")
    parser.add_argument("--task-path", required=True)
    parser.add_argument("--json-report", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()

    failures: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_FILES:
        p = task_path / rel
        if not p.exists():
            failures.append(f"Missing required file: {rel}")

    if failures:
        _emit(task_path, failures, warnings, args.json_report)
        return 2

    main_text = (task_path / "main.py").read_text(encoding="utf-8", errors="ignore")
    if "parse_task_run_options" not in main_text:
        failures.append("main.py must call parse_task_run_options(...)")
    for mode in ("human", "qa", "sim"):
        if mode not in main_text:
            failures.append(f"main.py missing mode token: {mode}")

    run_trial_text = (task_path / "src" / "run_trial.py").read_text(encoding="utf-8", errors="ignore")
    if "set_trial_context" not in run_trial_text:
        failures.append("src/run_trial.py must include set_trial_context(...) usage")
    _check_run_trial_localization(task_path / "src" / "run_trial.py", failures)

    cfg_paths = {
        "config/config.yaml": task_path / "config" / "config.yaml",
        "config/config_qa.yaml": task_path / "config" / "config_qa.yaml",
        "config/config_scripted_sim.yaml": task_path / "config" / "config_scripted_sim.yaml",
        "config/config_sampler_sim.yaml": task_path / "config" / "config_sampler_sim.yaml",
    }

    cfg_payloads: dict[str, dict[str, Any]] = {}
    for name, path in cfg_paths.items():
        text = path.read_text(encoding="utf-8", errors="ignore")
        token = _contains_forbidden_token(text)
        if token:
            failures.append(f"{name} contains forbidden token '{token}'")
        cfg_payloads[name] = _load_yaml(path)

    base_cfg = cfg_payloads["config/config.yaml"]
    qa_cfg = cfg_payloads["config/config_qa.yaml"]
    scripted_cfg = cfg_payloads["config/config_scripted_sim.yaml"]
    sampler_cfg = cfg_payloads["config/config_sampler_sim.yaml"]

    if "qa" in base_cfg or "sim" in base_cfg:
        failures.append("config/config.yaml must not include qa or sim sections")
    if "qa" not in qa_cfg:
        failures.append("config/config_qa.yaml must include qa section")
    if "sim" in qa_cfg:
        failures.append("config/config_qa.yaml must not include sim section")
    if "sim" not in scripted_cfg:
        failures.append("config/config_scripted_sim.yaml must include sim section")
    if "qa" in scripted_cfg:
        failures.append("config/config_scripted_sim.yaml must not include qa section")
    if "sim" not in sampler_cfg:
        failures.append("config/config_sampler_sim.yaml must include sim section")
    if "qa" in sampler_cfg:
        failures.append("config/config_sampler_sim.yaml must not include qa section")

    _check_asset_backed_stimuli(base_cfg, cfg_name="config/config.yaml", task_path=task_path, failures=failures)
    _check_asset_backed_stimuli(qa_cfg, cfg_name="config/config_qa.yaml", task_path=task_path, failures=failures)
    _check_asset_backed_stimuli(
        scripted_cfg,
        cfg_name="config/config_scripted_sim.yaml",
        task_path=task_path,
        failures=failures,
    )
    _check_asset_backed_stimuli(
        sampler_cfg,
        cfg_name="config/config_sampler_sim.yaml",
        task_path=task_path,
        failures=failures,
    )

    base_conditions = (
        base_cfg.get("task", {}).get("conditions", [])
        if isinstance(base_cfg.get("task", {}), dict)
        else []
    )
    condition_labels: set[str] = set()
    if isinstance(base_conditions, list):
        for cond in base_conditions:
            if isinstance(cond, str) and cond.strip():
                raw = cond.strip()
                condition_labels.add(_normalize_label(raw))
                condition_labels.add(_normalize_label(raw.replace("_", " ")))

    _check_text_stimulus_fidelity(
        base_cfg,
        cfg_name="config/config.yaml",
        condition_labels=condition_labels,
        failures=failures,
    )
    _check_text_stimulus_fidelity(
        qa_cfg,
        cfg_name="config/config_qa.yaml",
        condition_labels=condition_labels,
        failures=failures,
    )
    _check_text_stimulus_fidelity(
        scripted_cfg,
        cfg_name="config/config_scripted_sim.yaml",
        condition_labels=condition_labels,
        failures=failures,
    )
    _check_text_stimulus_fidelity(
        sampler_cfg,
        cfg_name="config/config_sampler_sim.yaml",
        condition_labels=condition_labels,
        failures=failures,
    )
    _check_text_encoding_quality(
        base_cfg,
        cfg_name="config/config.yaml",
        failures=failures,
    )
    _check_text_encoding_quality(
        qa_cfg,
        cfg_name="config/config_qa.yaml",
        failures=failures,
    )
    _check_text_encoding_quality(
        scripted_cfg,
        cfg_name="config/config_scripted_sim.yaml",
        failures=failures,
    )
    _check_text_encoding_quality(
        sampler_cfg,
        cfg_name="config/config_sampler_sim.yaml",
        failures=failures,
    )

    tb_cfg = _load_yaml(task_path / "taskbeacon.yaml")
    contracts = tb_cfg.get("contracts") if isinstance(tb_cfg, dict) else None
    if not isinstance(contracts, dict) or not contracts.get("psyflow_taps"):
        failures.append("taskbeacon.yaml must include contracts.psyflow_taps")

    gitignore_text = (task_path / ".gitignore").read_text(encoding="utf-8", errors="ignore")
    if "outputs/*" not in gitignore_text:
        warnings.append(".gitignore should include outputs/*")
    if "!/outputs/.gitkeep" not in gitignore_text:
        warnings.append(".gitignore should include !/outputs/.gitkeep")

    readme_text = (task_path / "README.md").read_text(encoding="utf-8", errors="ignore")
    for heading in REQUIRED_README_HEADINGS:
        if heading not in readme_text:
            failures.append(f"README.md missing required heading: {heading}")
    for heading in RECOMMENDED_README_SUBHEADINGS:
        if heading not in readme_text:
            warnings.append(f"README.md missing recommended heading: {heading}")
    task_flow_png = task_path / "task_flow.png"
    if task_flow_png.exists():
        task_flow_issue = _validate_task_flow_embed(readme_text, image_name="task_flow.png")
        if task_flow_issue:
            failures.append(task_flow_issue)

    assets_dir = task_path / "assets"
    if assets_dir.exists():
        for f in assets_dir.rglob("*"):
            if f.is_file():
                token = _contains_forbidden_token(f.name)
                if token:
                    failures.append(f"Forbidden asset filename token '{token}' in: {f.relative_to(task_path)}")

    assets_readme = task_path / "assets" / "README.md"
    if assets_readme.exists():
        token = _contains_forbidden_token(assets_readme.read_text(encoding="utf-8", errors="ignore"))
        if token:
            failures.append(f"assets/README.md contains forbidden token '{token}'")

    _check_reference_artifacts(task_path, failures)

    stim_map = task_path / "references" / "stimulus_mapping.md"
    stim_text = stim_map.read_text(encoding="utf-8", errors="ignore")

    if isinstance(base_conditions, list):
        for cond in base_conditions:
            if isinstance(cond, str) and cond.strip():
                token = f"`{cond.strip()}`"
                if token not in stim_text:
                    failures.append(
                        f"references/stimulus_mapping.md missing condition mapping row for '{cond.strip()}'"
                    )

    _emit(task_path, failures, warnings, args.json_report)
    return 0 if not failures else 1


def _emit(task_path: Path, failures: list[str], warnings: list[str], json_report: str | None) -> None:
    print(f"[task-build] task={task_path}")
    if failures:
        print("[task-build] FAIL")
        for item in failures:
            print(f"  - {item}")
    else:
        print("[task-build] PASS")
    if warnings:
        print("[task-build] WARN")
        for item in warnings:
            print(f"  - {item}")

    if json_report:
        payload = {
            "task_path": str(task_path),
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "warnings": warnings,
        }
        p = Path(json_report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[task-build] wrote {p}")


if __name__ == "__main__":
    raise SystemExit(main())
