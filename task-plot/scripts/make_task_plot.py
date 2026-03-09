#!/usr/bin/env python3
"""Orchestrate task-plot v0.2 inference, validation, audit, and rendering."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

import matplotlib.image as mpimg
import numpy as np
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from task_plot_contract import (
    ValidationError,
    dump_json_document,
    dump_yaml_document,
    validate_and_prepare_spec,
)
from task_plot_infer_existing import infer_from_existing_task
from task_plot_infer_source import infer_from_source
from task_plot_renderer import render_task_flow_png


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.mode == "existing":
            result, task_dir = _run_existing_mode(args)
        else:
            result, task_dir = _run_source_mode(args)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] failed before validation: {exc}")
        return 1

    try:
        validation = validate_and_prepare_spec(result["spec_root"])
    except ValidationError as exc:
        print(str(exc))
        return 1

    spec = validation.spec_root["task_plot_spec"]
    qa_config = _build_qa_config(args)

    spec_path = task_dir / "references" / "task_plot_spec.yaml"
    spec_json_path = task_dir / "references" / "task_plot_spec.json"
    excerpt_path = task_dir / "references" / "task_plot_source_excerpt.md"
    audit_path = task_dir / "references" / "task_plot_audit.md"

    dump_yaml_document(validation.spec_root, spec_path)
    dump_json_document(validation.spec_root, spec_json_path)
    excerpt_path.write_text(result["audit"]["source_excerpt"], encoding="utf-8")

    output_name = str(spec.get("figure", {}).get("output", {}).get("filename", "task_flow.png"))
    out_png = task_dir / output_name
    output_files = [spec_path, spec_json_path, excerpt_path]
    layout_feedback_notes: list[str] = []
    layout_feedback_records: list[dict[str, Any]] = []

    if not args.validate_only:
        render_task_flow_png(validation.spec_root, out_png=out_png, dpi_override=args.dpi)
        bg_mode = str(spec.get("figure", {}).get("output", {}).get("background", "white"))
        layout_feedback_notes, layout_feedback_records = _run_layout_feedback_loop(
            validation.spec_root,
            out_png,
            bg_mode,
            max_iters=3,
            dpi_override=args.dpi,
            qa_config=qa_config,
        )
        # Persist final adjusted spec used for the rendered PNG.
        dump_yaml_document(validation.spec_root, spec_path)
        dump_json_document(validation.spec_root, spec_json_path)
        output_files.append(out_png)

    _write_audit(
        audit_path=audit_path,
        task_dir=task_dir,
        mode=args.mode,
        result=result,
        validation=validation,
        output_files=output_files,
        dpi=args.dpi or int(spec.get("figure", {}).get("output", {}).get("dpi", 300)),
        layout_feedback=layout_feedback_notes,
        layout_feedback_records=layout_feedback_records,
        qa_config=qa_config,
    )

    print(f"[OK] task_plot_spec written: {spec_path}")
    print(f"[OK] task_plot_spec JSON written: {spec_json_path}")
    print(f"[OK] source excerpt written: {excerpt_path}")
    print(f"[OK] audit written: {audit_path}")
    for warning in result.get("audit", {}).get("warnings", []) or []:
        print(f"[WARN] {warning}")
    if args.validate_only:
        print("[OK] validate-only run completed (render skipped)")
    else:
        print(f"[OK] rendered: {out_png}")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate timeline-collection task flow plot.")
    parser.add_argument("--mode", required=True, choices=["existing", "source"])
    parser.add_argument("--task-path", help="Task directory path (required for existing mode).")
    parser.add_argument("--dpi", type=int, help="Override output DPI.")
    parser.add_argument("--validate-only", action="store_true")

    parser.add_argument("--source-pdf")
    parser.add_argument("--source-url")
    parser.add_argument("--methods-file")
    parser.add_argument("--methods-text")
    parser.add_argument("--max-conditions", type=int, default=4)
    parser.add_argument("--screens-per-timeline", type=int, default=6)
    parser.add_argument(
        "--qa-mode",
        choices=["local", "api", "auto"],
        default="local",
        help="Layout QA mode: local only (default), external API only, or auto (try API if configured).",
    )
    parser.add_argument(
        "--vision-api-url",
        help="Optional external vision API URL (OpenAI-compatible chat/completions schema).",
    )
    parser.add_argument("--vision-model", help="External vision model name.")
    parser.add_argument("--vision-api-key", help="External API key value (optional).")
    parser.add_argument(
        "--vision-api-key-env",
        default="TASK_PLOT_VISION_API_KEY",
        help="Environment variable containing external API key (default: TASK_PLOT_VISION_API_KEY).",
    )
    parser.add_argument(
        "--vision-api-key-header",
        default="Authorization",
        help="Header name used for API key (default: Authorization).",
    )
    parser.add_argument(
        "--vision-api-key-prefix",
        default="Bearer",
        help="Prefix for API key header value (default: Bearer). Use empty string for raw key.",
    )
    return parser


def _run_existing_mode(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    if not args.task_path:
        raise ValueError("--task-path is required in --mode existing")
    task_dir = Path(args.task_path).resolve()
    if not task_dir.exists() or not task_dir.is_dir():
        raise ValueError(f"task path is not a directory: {task_dir}")

    _ensure_task_dirs(task_dir, task_name=task_dir.name)
    result = infer_from_existing_task(task_dir)

    # Force hard constraints from CLI.
    spec = result["spec_root"]["task_plot_spec"]
    spec["figure"]["layout"]["max_conditions"] = int(args.max_conditions)
    spec["figure"]["layout"]["screens_per_timeline"] = int(args.screens_per_timeline)
    spec["timelines"] = spec["timelines"][: int(args.max_conditions)]
    for timeline in spec["timelines"]:
        timeline["phases"] = timeline.get("phases", [])[: int(args.screens_per_timeline)]

    return result, task_dir


def _run_source_mode(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    source_kind, source_value = _resolve_source_input(args)
    result = infer_from_source(
        source_kind,
        source_value,
        max_conditions=int(args.max_conditions),
        screens_per_timeline=int(args.screens_per_timeline),
    )

    task_name = result["task_name"]
    if args.task_path:
        task_dir = Path(args.task_path).resolve()
    else:
        task_dir = _create_draft_task_dir(Path.cwd() / "task-plot-drafts", task_name)

    _ensure_task_dirs(task_dir, task_name=task_name)
    return result, task_dir


def _resolve_source_input(args: argparse.Namespace) -> tuple[str, str]:
    candidates = [
        ("pdf", args.source_pdf),
        ("url", args.source_url),
        ("methods_file", args.methods_file),
        ("methods_text", args.methods_text),
    ]
    active = [(k, v.strip()) for k, v in candidates if isinstance(v, str) and v.strip()]
    if len(active) != 1:
        raise ValueError(
            "for --mode source provide exactly one of: --source-pdf | --source-url | --methods-file | --methods-text"
        )
    return active[0]


def _ensure_task_dirs(task_dir: Path, task_name: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "references").mkdir(parents=True, exist_ok=True)
    if not (task_dir / "README.md").exists():
        (task_dir / "README.md").write_text(
            f"# {task_name}\n\nAuto-created task folder for task-plot source workflow.\n",
            encoding="utf-8",
        )


def _create_draft_task_dir(draft_root: Path, task_name: str) -> Path:
    draft_root.mkdir(parents=True, exist_ok=True)
    slug = _slugify(task_name)
    candidate = draft_root / slug
    i = 2
    while candidate.exists():
        candidate = draft_root / f"{slug}-{i}"
        i += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:64] if slug else "task-plot-draft"


def _build_qa_config(args: argparse.Namespace) -> dict[str, Any]:
    key = (args.vision_api_key or "").strip()
    env_name = (args.vision_api_key_env or "").strip()
    if not key and env_name:
        key = os.environ.get(env_name, "").strip()
    model = (args.vision_model or "").strip() or os.environ.get("TASK_PLOT_VISION_MODEL", "").strip()
    return {
        "qa_mode": str(args.qa_mode or "local").strip().lower(),
        "vision_api_url": (args.vision_api_url or "").strip(),
        "vision_model": model,
        "vision_api_key": key,
        "vision_api_key_env": env_name,
        "vision_api_key_header": (args.vision_api_key_header or "Authorization").strip(),
        "vision_api_key_prefix": str(args.vision_api_key_prefix or "").strip(),
    }


def _write_audit(
    audit_path: Path,
    task_dir: Path,
    mode: str,
    result: dict[str, Any],
    validation: Any,
    output_files: list[Path],
    dpi: int,
    layout_feedback: list[str],
    layout_feedback_records: list[dict[str, Any]],
    qa_config: dict[str, Any],
) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    spec = validation.spec_root["task_plot_spec"]
    checksums = [(p, _sha256(p)) for p in output_files if p.exists()]

    lines = [
        "# Task Plot Audit",
        "",
        f"- generated_at: {now}",
        f"- mode: {mode}",
        f"- task_path: {task_dir}",
        "",
        "## 1. Inputs and provenance",
        "",
    ]
    lines.extend([f"- {x}" for x in result["audit"].get("inputs", [])])

    lines.extend(["", "## 2. Evidence extracted from README", ""])
    lines.extend([f"- {x}" for x in result["audit"].get("readme_evidence", [])])

    lines.extend(["", "## 3. Evidence extracted from config/source", ""])
    lines.extend([f"- {x}" for x in result["audit"].get("source_evidence", [])])
    warnings = result["audit"].get("warnings", [])
    if warnings:
        lines.extend(["", "## 3b. Warnings", ""])
        lines.extend([f"- {x}" for x in warnings])

    lines.extend(["", "## 4. Mapping to task_plot_spec", ""])
    lines.extend([f"- {x}" for x in result["audit"].get("mapping", [])])
    lines.append("- root_key: task_plot_spec")
    lines.append(f"- spec_version: {spec.get('spec_version')}")

    lines.extend(["", "## 5. Style decision and rationale", ""])
    lines.append(f"- {result['audit'].get('style_rationale', '(none)')}")

    lines.extend(["", "## 6. Rendering parameters and constraints", ""])
    lines.append(f"- output_file: {spec.get('figure', {}).get('output', {}).get('filename', 'task_flow.png')}")
    lines.append(f"- dpi: {dpi}")
    lines.append(f"- max_conditions: {spec.get('figure', {}).get('layout', {}).get('max_conditions')}")
    lines.append(f"- screens_per_timeline: {spec.get('figure', {}).get('layout', {}).get('screens_per_timeline')}")
    lines.append(f"- screen_overlap_ratio: {spec.get('figure', {}).get('layout', {}).get('screen_overlap_ratio')}")
    lines.append(f"- screen_slope: {spec.get('figure', {}).get('layout', {}).get('screen_slope')}")
    lines.append(f"- screen_slope_deg: {spec.get('figure', {}).get('layout', {}).get('screen_slope_deg')}")
    lines.append(f"- screen_aspect_ratio: {spec.get('figure', {}).get('layout', {}).get('screen_aspect_ratio')}")
    lines.append(f"- qa_mode: {qa_config.get('qa_mode')}")
    if qa_config.get("qa_mode") in {"api", "auto"}:
        lines.append(f"- vision_api_url: {qa_config.get('vision_api_url') or '(not set)'}")
        lines.append(f"- vision_model: {qa_config.get('vision_model') or '(not set)'}")
        lines.append(f"- vision_api_key_env: {qa_config.get('vision_api_key_env') or '(none)'}")
    if layout_feedback:
        lines.append("- auto_layout_feedback:")
        for item in layout_feedback:
            lines.append(f"  - {item}")
    if layout_feedback_records:
        lines.append("- auto_layout_feedback_records:")
        for rec in layout_feedback_records:
            lines.append(f"  - pass: {rec.get('pass')}")
            lines.append(f"    metrics: {rec.get('metrics')}")
            model_used = rec.get("vision_model")
            if model_used:
                lines.append(f"    vision_model: {model_used}")
            for issue in rec.get("issues", [])[:5]:
                lines.append(f"    issue: {issue}")
            if rec.get("adjustments"):
                lines.append(f"    adjustments: {rec.get('adjustments')}")
    if validation.warnings:
        lines.append("- validator_warnings:")
        for warning in validation.warnings:
            lines.append(f"  - {warning}")

    lines.extend(["", "## 7. Output files and checksums", ""])
    for path, digest in checksums:
        lines.append(f"- {path}: sha256={digest}")

    lines.extend(["", "## 8. Inferred/uncertain items", ""])
    inferred_items = result["audit"].get("inferred_items", [])
    if inferred_items:
        lines.extend([f"- {x}" for x in inferred_items])
    else:
        lines.append("- none")

    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_layout_feedback_loop(
    spec_root: dict[str, Any],
    png_path: Path,
    bg_mode: str,
    max_iters: int = 3,
    dpi_override: int | None = None,
    qa_config: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    notes: list[str] = []
    records: list[dict[str, Any]] = []
    max_iters = max(1, int(max_iters))

    for i in range(max_iters):
        metrics = _inspect_png_margins(png_path, bg_mode)
        if not metrics["has_content"]:
            notes.append("no non-background content detected; auto-layout skipped")
            records.append({"pass": i + 1, "metrics": metrics, "issues": ["no_content"], "adjustments": {}})
            break

        cropped = False
        if _needs_balanced_crop(metrics):
            _crop_png_balanced(png_path, metrics)
            cropped = True
            metrics = _inspect_png_margins(png_path, bg_mode)

        local_flags = _local_layout_flags(metrics)
        vision_feedback = _vision_layout_feedback(png_path, qa_config or {})
        merged_flags = dict(local_flags)
        merged_flags.update(vision_feedback.get("flags", {}))
        adjustments = _adjustments_from_flags(merged_flags)

        if adjustments:
            _apply_layout_adjustments(spec_root, adjustments)
            render_task_flow_png(spec_root, out_png=png_path, dpi_override=dpi_override)
            action_note = ", ".join(f"{k}={v}" for k, v in sorted(adjustments.items()))
            notes.append(
                f"layout pass {i + 1}: adjusted ({action_note}); "
                f"left={metrics['left_ratio']:.3f}, right={metrics['right_ratio']:.3f}, blank={metrics['blank_ratio']:.3f}"
            )
        else:
            if cropped:
                notes.append(
                    f"layout pass {i + 1}: crop-only; "
                    f"left={metrics['left_ratio']:.3f}, right={metrics['right_ratio']:.3f}, blank={metrics['blank_ratio']:.3f}"
                )
            else:
                notes.append(
                    f"layout pass {i + 1}: no adjustment needed; "
                    f"left={metrics['left_ratio']:.3f}, right={metrics['right_ratio']:.3f}, blank={metrics['blank_ratio']:.3f}"
                )

        issues = list(vision_feedback.get("issues", []))
        if local_flags.get("large_right_margin"):
            issues.append("local:large_right_margin")
        if local_flags.get("large_left_margin"):
            issues.append("local:large_left_margin")
        if local_flags.get("large_total_whitespace"):
            issues.append("local:large_total_whitespace")
        if local_flags.get("margin_asymmetry"):
            issues.append("local:margin_asymmetry")

        records.append(
            {
                "pass": i + 1,
                "metrics": {
                    "left_ratio": round(float(metrics["left_ratio"]), 4),
                    "right_ratio": round(float(metrics["right_ratio"]), 4),
                    "blank_ratio": round(float(metrics["blank_ratio"]), 4),
                },
                "vision_model": vision_feedback.get("model"),
                "issues": issues[:8],
                "adjustments": adjustments,
            }
        )

        pass_ok = bool(vision_feedback.get("pass", True)) and not adjustments and not _needs_balanced_crop(metrics)
        if pass_ok:
            break

    return notes, records


def _inspect_png_margins(png_path: Path, bg_mode: str) -> dict[str, Any]:
    arr = mpimg.imread(png_path)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.dtype.kind in {"u", "i"}:
        arr = arr.astype(np.float32) / 255.0
    else:
        arr = arr.astype(np.float32)

    h, w = int(arr.shape[0]), int(arr.shape[1])
    rgb = arr[..., :3]
    alpha = arr[..., 3] if arr.shape[-1] >= 4 else np.ones((h, w), dtype=np.float32)

    if bg_mode == "transparent" and arr.shape[-1] >= 4:
        raw_mask = alpha > 0.03
    else:
        raw_mask = (alpha > 0.03) & np.any(rgb < 0.992, axis=2)

    row_hits = np.sum(raw_mask, axis=1)
    col_hits = np.sum(raw_mask, axis=0)
    min_row_hits = max(2, int(round(0.0025 * w)))
    min_col_hits = max(2, int(round(0.0025 * h)))
    row_idx = np.where(row_hits >= min_row_hits)[0]
    col_idx = np.where(col_hits >= min_col_hits)[0]

    if row_idx.size == 0 or col_idx.size == 0:
        return {
            "has_content": False,
            "left_ratio": 0.0,
            "right_ratio": 0.0,
            "blank_ratio": 1.0,
            "bbox": (0, h - 1, 0, w - 1),
            "shape": (h, w),
        }

    y0 = int(row_idx.min())
    y1 = int(row_idx.max())
    x0 = int(col_idx.min())
    x1 = int(col_idx.max())
    bbox_area = float(max(1, (y1 - y0 + 1) * (x1 - x0 + 1)))
    total_area = float(max(1, h * w))
    return {
        "has_content": True,
        "left_ratio": x0 / max(1.0, float(w)),
        "right_ratio": (w - 1 - x1) / max(1.0, float(w)),
        "blank_ratio": max(0.0, 1.0 - bbox_area / total_area),
        "bbox": (y0, y1, x0, x1),
        "shape": (h, w),
    }


def _needs_balanced_crop(metrics: dict[str, Any]) -> bool:
    left = float(metrics["left_ratio"])
    right = float(metrics["right_ratio"])
    blank = float(metrics["blank_ratio"])
    lr_delta = abs(left - right)
    return blank > 0.28 or lr_delta > 0.06 or max(left, right) > 0.18


def _crop_png_balanced(png_path: Path, metrics: dict[str, Any]) -> None:
    arr = mpimg.imread(png_path)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)

    h, w = metrics["shape"]
    y0, y1, x0, x1 = metrics["bbox"]
    pad_x = max(8, int(round(0.028 * w)))
    pad_y = max(8, int(round(0.028 * h)))

    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    half_w = max(cx - x0, x1 - cx) + pad_x
    half_h = max(cy - y0, y1 - cy) + pad_y

    left = int(math.floor(cx - half_w))
    right = int(math.ceil(cx + half_w))
    top = int(math.floor(cy - half_h))
    bottom = int(math.ceil(cy + half_h))

    left = max(0, left)
    top = max(0, top)
    right = min(w - 1, right)
    bottom = min(h - 1, bottom)

    cropped = arr[top : bottom + 1, left : right + 1]
    mpimg.imsave(png_path, cropped)


def _local_layout_flags(metrics: dict[str, Any]) -> dict[str, bool]:
    left = float(metrics["left_ratio"])
    right = float(metrics["right_ratio"])
    blank = float(metrics["blank_ratio"])
    return {
        "large_right_margin": right > max(0.16, left + 0.07),
        "large_left_margin": left > max(0.16, right + 0.07),
        "large_total_whitespace": blank > 0.34,
        "margin_asymmetry": abs(left - right) > 0.08,
    }


def _vision_layout_feedback(png_path: Path, qa_config: dict[str, Any]) -> dict[str, Any]:
    qa_mode = str(qa_config.get("qa_mode", "local")).strip().lower() or "local"
    if qa_mode == "local":
        return {"pass": True, "issues": [], "flags": {}, "model": None}

    api_url = str(qa_config.get("vision_api_url", "")).strip()
    if not api_url:
        if qa_mode == "api":
            return {"pass": True, "issues": ["external vision disabled: --vision-api-url missing"], "flags": {}, "model": None}
        return {"pass": True, "issues": ["external vision skipped: no API URL configured"], "flags": {}, "model": None}

    model = str(qa_config.get("vision_model", "")).strip()
    if not model:
        if qa_mode == "api":
            return {"pass": True, "issues": ["external vision disabled: --vision-model missing"], "flags": {}, "model": None}
        return {"pass": True, "issues": ["external vision skipped: no model configured"], "flags": {}, "model": None}

    img_bytes = png_path.read_bytes()
    data_url = "data:image/png;base64," + base64.b64encode(img_bytes).decode("ascii")
    prompt = (
        "You are a strict layout QA model for publication-ready task timeline figures.\n"
        "Check only these issues: arrow crossing duration text, arrow crossing screens, overlapping labels, "
        "condition labels too far from first screen, large side margins / whitespace.\n"
        "Return only valid JSON object with keys:\n"
        "{"
        '"pass": bool, '
        '"issues": [string], '
        '"flags": {'
        '"arrow_duration_overlap": bool, '
        '"arrow_screen_overlap": bool, '
        '"label_overlap": bool, '
        '"condition_label_too_far": bool, '
        '"large_right_margin": bool, '
        '"large_left_margin": bool, '
        '"large_total_whitespace": bool'
        "}"
        "}\n"
        "Use conservative judgement: if uncertain, flag false."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You output strict JSON only."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    key = str(qa_config.get("vision_api_key", "")).strip()
    key_header = str(qa_config.get("vision_api_key_header", "Authorization")).strip()
    key_prefix = str(qa_config.get("vision_api_key_prefix", "Bearer")).strip()
    if key and key_header:
        value = f"{key_prefix} {key}".strip() if key_prefix else key
        headers[key_header] = value

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=45)
        if resp.status_code >= 400:
            return {
                "pass": True,
                "issues": [f"external vision request failed: http {resp.status_code}"],
                "flags": {},
                "model": model,
            }
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _parse_json_object(content)
        if not isinstance(parsed, dict):
            return {"pass": True, "issues": ["external vision response parse failed"], "flags": {}, "model": model}
        flags = parsed.get("flags")
        if not isinstance(flags, dict):
            flags = {}
        norm_flags = {
            "arrow_duration_overlap": bool(flags.get("arrow_duration_overlap", False)),
            "arrow_screen_overlap": bool(flags.get("arrow_screen_overlap", False)),
            "label_overlap": bool(flags.get("label_overlap", False)),
            "condition_label_too_far": bool(flags.get("condition_label_too_far", False)),
            "large_right_margin": bool(flags.get("large_right_margin", False)),
            "large_left_margin": bool(flags.get("large_left_margin", False)),
            "large_total_whitespace": bool(flags.get("large_total_whitespace", False)),
        }
        issues = parsed.get("issues")
        if not isinstance(issues, list):
            issues = []
        issues = [str(x).strip() for x in issues if str(x).strip()]
        return {
            "pass": bool(parsed.get("pass", True)),
            "issues": issues,
            "flags": norm_flags,
            "model": model,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "pass": True,
            "issues": [f"external vision request error: {exc.__class__.__name__}"],
            "flags": {},
            "model": model,
        }


def _parse_json_object(text: str) -> dict[str, Any] | None:
    s = str(text or "").strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:  # noqa: BLE001
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        snippet = s[start : end + 1]
        try:
            obj = json.loads(snippet)
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001
            return None
    return None


def _adjustments_from_flags(flags: dict[str, Any]) -> dict[str, float]:
    adjustments: dict[str, float] = {}
    if bool(flags.get("arrow_duration_overlap")) or bool(flags.get("arrow_screen_overlap")):
        adjustments["timeline_arrow_gap_delta"] = 0.008
        adjustments["timeline_arrow_text_clearance_delta"] = 0.006
        adjustments["timeline_arrow_screen_clearance_delta"] = 0.004
    if bool(flags.get("label_overlap")):
        adjustments["screen_overlap_ratio_delta"] = -0.025
        adjustments["timeline_gap_delta"] = 0.020
    if bool(flags.get("condition_label_too_far")):
        adjustments["condition_label_gap_delta"] = -0.003
    if bool(flags.get("large_right_margin")):
        adjustments["left_margin_delta"] = 0.012
    if bool(flags.get("large_left_margin")):
        adjustments["left_margin_delta"] = adjustments.get("left_margin_delta", 0.0) - 0.010
    if bool(flags.get("large_total_whitespace")):
        adjustments["width_in_scale"] = 0.92
    return adjustments


def _apply_layout_adjustments(spec_root: dict[str, Any], adjustments: dict[str, float]) -> None:
    spec = spec_root.get("task_plot_spec", {})
    figure = spec.get("figure", {})
    layout = figure.get("layout", {})
    output = figure.get("output", {})

    if "timeline_arrow_gap_delta" in adjustments:
        layout["timeline_arrow_gap"] = _clamp(
            float(layout.get("timeline_arrow_gap", 0.010)) + float(adjustments["timeline_arrow_gap_delta"]),
            0.002,
            0.060,
        )
    if "timeline_arrow_text_clearance_delta" in adjustments:
        layout["timeline_arrow_text_clearance"] = _clamp(
            float(layout.get("timeline_arrow_text_clearance", 0.010))
            + float(adjustments["timeline_arrow_text_clearance_delta"]),
            0.004,
            0.060,
        )
    if "timeline_arrow_screen_clearance_delta" in adjustments:
        layout["timeline_arrow_screen_clearance"] = _clamp(
            float(layout.get("timeline_arrow_screen_clearance", 0.007))
            + float(adjustments["timeline_arrow_screen_clearance_delta"]),
            0.003,
            0.050,
        )
    if "screen_overlap_ratio_delta" in adjustments:
        layout["screen_overlap_ratio"] = _clamp(
            float(layout.get("screen_overlap_ratio", 0.10)) + float(adjustments["screen_overlap_ratio_delta"]),
            0.03,
            0.28,
        )
    if "timeline_gap_delta" in adjustments:
        layout["timeline_gap"] = _clamp(
            float(layout.get("timeline_gap", 0.18)) + float(adjustments["timeline_gap_delta"]),
            0.12,
            0.40,
        )
    if "condition_label_gap_delta" in adjustments:
        layout["condition_label_gap"] = _clamp(
            float(layout.get("condition_label_gap", 0.014)) + float(adjustments["condition_label_gap_delta"]),
            0.004,
            0.040,
        )
    if "left_margin_delta" in adjustments:
        layout["left_margin"] = _clamp(
            float(layout.get("left_margin", 0.20)) + float(adjustments["left_margin_delta"]),
            0.12,
            0.48,
        )
    if "width_in_scale" in adjustments:
        base_w = float(output.get("width_in", 16.0))
        output["width_in"] = _clamp(base_w * float(adjustments["width_in_scale"]), 5.6, 16.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


if __name__ == "__main__":
    raise SystemExit(main())
