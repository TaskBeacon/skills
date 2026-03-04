#!/usr/bin/env python3
"""Contract parsing and validation for task-plot v0.2."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT_KEY = "task_plot_spec"
LEGACY_ROOT_KEY = "TaskIllustrationSpec"
SUPPORTED_SPEC_VERSION = "0.2"


@dataclass
class ValidationResult:
    spec_root: dict[str, Any]
    warnings: list[str]


class ValidationError(RuntimeError):
    """Raised when a spec fails validation."""

    def __init__(self, issues: list[str]) -> None:
        message = "Spec validation failed:\n- " + "\n- ".join(issues)
        super().__init__(message)
        self.issues = issues


def load_document(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        doc = json.loads(text)
    else:
        doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise ValidationError([f"{p} must contain a mapping at top level."])
    return doc


def dump_yaml_document(data: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def dump_json_document(data: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_and_prepare_spec(spec_root: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    warnings: list[str] = []
    root = copy.deepcopy(spec_root)

    if LEGACY_ROOT_KEY in root:
        raise ValidationError(
            [
                f"Legacy root key '{LEGACY_ROOT_KEY}' is not supported.",
                f"Rename root key to '{ROOT_KEY}'.",
            ]
        )
    if ROOT_KEY not in root:
        raise ValidationError([f"Missing required root key '{ROOT_KEY}'."])
    spec = root.get(ROOT_KEY)
    if not isinstance(spec, dict):
        raise ValidationError([f"'{ROOT_KEY}' must be an object mapping."])

    _apply_defaults(spec)
    _validate_common(spec, issues)
    _validate_timelines(spec, issues, warnings)

    if issues:
        raise ValidationError(issues)

    return ValidationResult(spec_root={ROOT_KEY: spec}, warnings=warnings)


def _apply_defaults(spec: dict[str, Any]) -> None:
    meta = spec.setdefault("meta", {})
    meta.setdefault("task_id", "")
    meta.setdefault("mode", "existing")

    figure = spec.setdefault("figure", {})
    output = figure.setdefault("output", {})
    output.setdefault("filename", "task_flow.png")
    output.setdefault("dpi", 300)
    output.setdefault("width_in", 16.0)
    output.setdefault("background", "white")

    layout = figure.setdefault("layout", {})
    layout.setdefault("max_conditions", 4)
    layout.setdefault("screens_per_timeline", 6)
    layout.setdefault("screen_overlap_ratio", 0.10)
    layout.setdefault("screen_slope", 0.08)
    layout.setdefault("screen_slope_deg", 25.0)
    layout.setdefault("timeline_gap", 0.18)
    layout.setdefault("screen_aspect_ratio", 16 / 11)
    layout.setdefault("left_margin", 0.20)
    layout.setdefault("right_margin", 0.03)
    layout.setdefault("top_margin", 0.03)
    layout.setdefault("bottom_margin", 0.05)
    layout.setdefault("condition_label_gap", 0.014)
    layout.setdefault("phase_label_pad", 0.010)
    layout.setdefault("duration_label_gap", 0.006)
    layout.setdefault("timeline_arrow_gap", 0.010)
    layout.setdefault("timeline_arrow_screen_clearance", 0.007)
    layout.setdefault("timeline_arrow_text_clearance", 0.010)
    layout.setdefault("timeline_arrow_extra_per_screen", 0.015)
    layout.setdefault("timeline_arrow_min_y", 0.020)
    layout.setdefault("timeline_arrow_max_y", 0.96)

    spec.setdefault("legend", [])
    spec.setdefault("timelines", [])


def _validate_common(spec: dict[str, Any], issues: list[str]) -> None:
    if spec.get("spec_version") != SUPPORTED_SPEC_VERSION:
        issues.append(
            f"spec_version must be '{SUPPORTED_SPEC_VERSION}' under {ROOT_KEY}.spec_version."
        )

    meta = spec.get("meta", {})
    if not isinstance(meta.get("task_name"), str) or not meta.get("task_name", "").strip():
        issues.append("meta.task_name is required and must be non-empty.")
    if meta.get("mode") not in {"existing", "source"}:
        issues.append("meta.mode must be one of: existing, source.")

    output = spec.get("figure", {}).get("output", {})
    if not isinstance(output.get("filename"), str) or not output.get("filename", "").strip():
        issues.append("figure.output.filename must be a non-empty string.")
    if not str(output.get("filename", "")).lower().endswith(".png"):
        issues.append("figure.output.filename must be a .png file.")
    if not isinstance(output.get("dpi"), int) or output.get("dpi", 0) < 72:
        issues.append("figure.output.dpi must be an integer >= 72.")
    if not isinstance(output.get("width_in"), (int, float)) or output.get("width_in", 0) <= 4:
        issues.append("figure.output.width_in must be > 4.")
    if output.get("background") not in {"white", "transparent"}:
        issues.append("figure.output.background must be white or transparent.")

    layout = spec.get("figure", {}).get("layout", {})
    if not isinstance(layout.get("max_conditions"), int) or layout.get("max_conditions", 0) <= 0:
        issues.append("figure.layout.max_conditions must be a positive integer.")
    if (
        not isinstance(layout.get("screens_per_timeline"), int)
        or layout.get("screens_per_timeline", 0) <= 0
    ):
        issues.append("figure.layout.screens_per_timeline must be a positive integer.")
    if (
        not isinstance(layout.get("screen_overlap_ratio"), (int, float))
        or layout.get("screen_overlap_ratio", -1) < 0
        or layout.get("screen_overlap_ratio", 1) >= 0.4
    ):
        issues.append("figure.layout.screen_overlap_ratio must be in [0, 0.4).")
    if (
        not isinstance(layout.get("screen_slope"), (int, float))
        or layout.get("screen_slope", -1) < 0
        or layout.get("screen_slope", 1) > 0.1
    ):
        issues.append("figure.layout.screen_slope must be in [0, 0.1].")
    if (
        not isinstance(layout.get("screen_slope_deg"), (int, float))
        or layout.get("screen_slope_deg", -1) < 0
        or layout.get("screen_slope_deg", 1) > 35
    ):
        issues.append("figure.layout.screen_slope_deg must be in [0, 35].")
    if (
        not isinstance(layout.get("timeline_gap"), (int, float))
        or layout.get("timeline_gap", 0) <= 0
    ):
        issues.append("figure.layout.timeline_gap must be > 0.")
    if (
        not isinstance(layout.get("screen_aspect_ratio"), (int, float))
        or layout.get("screen_aspect_ratio", 0) <= 1.15
    ):
        issues.append("figure.layout.screen_aspect_ratio must be > 1.15 (wide screen).")
    if (
        not isinstance(layout.get("left_margin"), (int, float))
        or not 0 <= float(layout.get("left_margin")) < 0.6
    ):
        issues.append("figure.layout.left_margin must be in [0, 0.6).")
    if (
        not isinstance(layout.get("right_margin"), (int, float))
        or not 0 <= float(layout.get("right_margin")) < 0.6
    ):
        issues.append("figure.layout.right_margin must be in [0, 0.6).")
    if float(layout.get("left_margin", 0.0)) + float(layout.get("right_margin", 0.0)) >= 0.85:
        issues.append("figure.layout.left_margin + right_margin must be < 0.85.")
    if (
        not isinstance(layout.get("top_margin"), (int, float))
        or not 0 <= float(layout.get("top_margin")) < 0.5
    ):
        issues.append("figure.layout.top_margin must be in [0, 0.5).")
    if (
        not isinstance(layout.get("bottom_margin"), (int, float))
        or not 0 <= float(layout.get("bottom_margin")) < 0.5
    ):
        issues.append("figure.layout.bottom_margin must be in [0, 0.5).")
    if float(layout.get("top_margin", 0.0)) + float(layout.get("bottom_margin", 0.0)) >= 0.9:
        issues.append("figure.layout.top_margin + bottom_margin must be < 0.9.")
    if (
        not isinstance(layout.get("condition_label_gap"), (int, float))
        or float(layout.get("condition_label_gap")) < 0
    ):
        issues.append("figure.layout.condition_label_gap must be >= 0.")
    if (
        not isinstance(layout.get("phase_label_pad"), (int, float))
        or float(layout.get("phase_label_pad")) < 0
    ):
        issues.append("figure.layout.phase_label_pad must be >= 0.")
    if (
        not isinstance(layout.get("duration_label_gap"), (int, float))
        or float(layout.get("duration_label_gap")) < 0
    ):
        issues.append("figure.layout.duration_label_gap must be >= 0.")
    if (
        not isinstance(layout.get("timeline_arrow_gap"), (int, float))
        or float(layout.get("timeline_arrow_gap")) < 0
    ):
        issues.append("figure.layout.timeline_arrow_gap must be >= 0.")
    if (
        not isinstance(layout.get("timeline_arrow_screen_clearance"), (int, float))
        or float(layout.get("timeline_arrow_screen_clearance")) < 0
    ):
        issues.append("figure.layout.timeline_arrow_screen_clearance must be >= 0.")
    if (
        not isinstance(layout.get("timeline_arrow_text_clearance"), (int, float))
        or float(layout.get("timeline_arrow_text_clearance")) < 0
    ):
        issues.append("figure.layout.timeline_arrow_text_clearance must be >= 0.")
    if (
        not isinstance(layout.get("timeline_arrow_extra_per_screen"), (int, float))
        or float(layout.get("timeline_arrow_extra_per_screen")) < 0
    ):
        issues.append("figure.layout.timeline_arrow_extra_per_screen must be >= 0.")
    if (
        not isinstance(layout.get("timeline_arrow_min_y"), (int, float))
        or not 0 <= float(layout.get("timeline_arrow_min_y")) <= 1
    ):
        issues.append("figure.layout.timeline_arrow_min_y must be in [0, 1].")
    if (
        not isinstance(layout.get("timeline_arrow_max_y"), (int, float))
        or not 0 <= float(layout.get("timeline_arrow_max_y")) <= 1
    ):
        issues.append("figure.layout.timeline_arrow_max_y must be in [0, 1].")
    if float(layout.get("timeline_arrow_max_y", 1.0)) <= float(layout.get("timeline_arrow_min_y", 0.0)):
        issues.append("figure.layout.timeline_arrow_max_y must be > timeline_arrow_min_y.")


def _validate_duration(obj: Any, path: str, issues: list[str]) -> None:
    if obj is None:
        return
    if not isinstance(obj, dict):
        issues.append(f"{path} must be an object when provided.")
        return
    has_fixed = "fixed" in obj
    has_range = "range" in obj
    if has_fixed and has_range:
        issues.append(f"{path} cannot have both fixed and range.")
        return
    if not has_fixed and not has_range:
        issues.append(f"{path} must have fixed or range.")
        return
    if has_fixed:
        value = obj.get("fixed")
        if not isinstance(value, (int, float)) or value < 0:
            issues.append(f"{path}.fixed must be >= 0.")
    if has_range:
        value = obj.get("range")
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(v, (int, float)) for v in value)
        ):
            issues.append(f"{path}.range must be [min,max] numeric.")
            return
        if value[0] < 0 or value[1] < value[0]:
            issues.append(f"{path}.range must satisfy 0 <= min <= max.")


def _validate_timelines(
    spec: dict[str, Any],
    issues: list[str],
    warnings: list[str],
) -> None:
    timelines = spec.get("timelines")
    if not isinstance(timelines, list) or not timelines:
        issues.append("timelines must be a non-empty list.")
        return

    layout = spec["figure"]["layout"]
    max_conditions = int(layout["max_conditions"])
    screens_cap = int(layout["screens_per_timeline"])

    if len(timelines) > max_conditions:
        issues.append(f"timelines count exceeds max_conditions ({len(timelines)} > {max_conditions}).")

    for i, tl in enumerate(timelines):
        tp = f"timelines[{i}]"
        if not isinstance(tl, dict):
            issues.append(f"{tp} must be an object.")
            continue
        if not isinstance(tl.get("condition"), str) or not tl.get("condition", "").strip():
            issues.append(f"{tp}.condition is required.")
        if not isinstance(tl.get("display_condition_label"), str) or not tl.get("display_condition_label", "").strip():
            issues.append(f"{tp}.display_condition_label is required for reproducible rendering.")
        condition_note = tl.get("display_condition_note")
        if condition_note is not None and (not isinstance(condition_note, str) or len(condition_note) > 120):
            issues.append(f"{tp}.display_condition_note must be a string <= 120 chars when provided.")
        phases = tl.get("phases")
        if not isinstance(phases, list) or not phases:
            issues.append(f"{tp}.phases must be a non-empty list.")
            continue
        if len(phases) > screens_cap:
            issues.append(f"{tp}.phases exceeds screens_per_timeline cap ({len(phases)} > {screens_cap}).")
        for j, phase in enumerate(phases):
            pp = f"{tp}.phases[{j}]"
            if not isinstance(phase, dict):
                issues.append(f"{pp} must be an object.")
                continue
            if not isinstance(phase.get("phase_name"), str) or not phase.get("phase_name", "").strip():
                issues.append(f"{pp}.phase_name is required.")
            if (
                not isinstance(phase.get("display_phase_label"), str)
                or not phase.get("display_phase_label", "").strip()
            ):
                issues.append(f"{pp}.display_phase_label is required for reproducible rendering.")
            timing_label = phase.get("display_timing_label")
            if timing_label is not None and (not isinstance(timing_label, str) or len(timing_label) > 48):
                issues.append(f"{pp}.display_timing_label must be a string <= 48 chars when provided.")
            _validate_duration(phase.get("duration_ms"), f"{pp}.duration_ms", issues)
            _validate_duration(phase.get("response_window_ms"), f"{pp}.response_window_ms", issues)

            stim_ids = phase.get("stim_ids")
            if stim_ids is None:
                phase["stim_ids"] = []
                stim_ids = phase["stim_ids"]
            if not isinstance(stim_ids, list):
                issues.append(f"{pp}.stim_ids must be a list.")

            stim_example = phase.get("stimulus_example")
            if not isinstance(stim_example, dict):
                issues.append(f"{pp}.stimulus_example must be an object.")
                continue
            summary = stim_example.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                issues.append(f"{pp}.stimulus_example.summary is required.")
            modality = stim_example.get("modality")
            if modality not in {"visual", "audio", "mixed", "other"}:
                issues.append(f"{pp}.stimulus_example.modality must be one of visual/audio/mixed/other.")
            draw_hint = stim_example.get("draw_hint")
            if not isinstance(draw_hint, str) or not draw_hint.strip():
                issues.append(f"{pp}.stimulus_example.draw_hint is required.")

            if phase.get("duration_ms") is None:
                warnings.append(f"{pp} missing duration_ms; renderer will annotate as n/a.")
