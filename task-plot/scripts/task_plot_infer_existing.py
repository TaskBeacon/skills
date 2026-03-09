#!/usr/bin/env python3
"""Infer timeline-collection task_plot_spec from an existing PsyFlow task."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


Predicate = Callable[[str], bool]


@dataclass
class PhaseTemplate:
    order: int
    unit_var: str
    phase_expr: str
    deadline_expr: str
    valid_keys_expr: str
    stim_id_expr: str
    predicates: list[Predicate]
    predicate_labels: list[str]


@dataclass
class CaptureTemplate:
    order: int
    unit_var: str
    duration_expr: str
    keys_expr: str
    predicates: list[Predicate]
    predicate_labels: list[str]


@dataclass
class VisibleShowTemplate:
    order: int
    unit_var: str
    unit_label_expr: str
    duration_expr: str
    stim_exprs: list[str]
    predicates: list[Predicate]
    predicate_labels: list[str]


def infer_from_existing_task(task_path: str | Path) -> dict[str, Any]:
    task_dir = Path(task_path).resolve()
    readme_path = task_dir / "README.md"
    config_path = task_dir / "config" / "config.yaml"
    run_trial_path = task_dir / "src" / "run_trial.py"

    if not readme_path.exists():
        raise FileNotFoundError(f"README.md not found: {readme_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"config/config.yaml not found: {config_path}")
    if not run_trial_path.exists():
        raise FileNotFoundError(f"src/run_trial.py not found: {run_trial_path}")

    readme_text = readme_path.read_text(encoding="utf-8", errors="ignore")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError("config/config.yaml must contain a mapping.")
    run_trial_src = run_trial_path.read_text(encoding="utf-8", errors="ignore")
    run_trial_tree = ast.parse(run_trial_src)

    task_name = _extract_task_name(readme_text, task_dir.name)
    conditions = _extract_conditions(config)
    if not conditions:
        conditions = ["default"]

    layout_defaults = _layout_defaults(config)
    selected_conditions = list(conditions)

    extraction = _extract_phase_templates(run_trial_tree)
    phase_templates = extraction["phases"]
    capture_templates = extraction["captures"]
    visible_show_templates = extraction["visible_shows"]
    unit_stim_calls = extraction["unit_stims"]
    var_exprs = extraction["var_exprs"]
    unresolved_predicates = extraction["unresolved_predicates"]

    stimuli_cfg = config.get("stimuli") if isinstance(config.get("stimuli"), dict) else {}
    timing_cfg = config.get("timing") if isinstance(config.get("timing"), dict) else {}
    task_cfg = config.get("task") if isinstance(config.get("task"), dict) else {}
    controller_cfg = config.get("controller") if isinstance(config.get("controller"), dict) else {}
    settings_values = _build_settings_values(timing_cfg, task_cfg, controller_cfg)

    timelines = []
    config_evidence: list[str] = []
    inferred_items: list[str] = []
    warning_items: list[str] = []

    for condition in selected_conditions:
        phase_rows: list[tuple[int, dict[str, Any]]] = []
        for template in sorted(phase_templates, key=lambda p: p.order):
            if not _matches_predicates(condition, template.predicates):
                continue
            phase_name = _resolve_phase_name(template.phase_expr)
            duration_ms, duration_note = _resolve_duration(
                template.deadline_expr,
                settings_values=settings_values,
                var_exprs=var_exprs,
            )
            if duration_note:
                inferred_items.append(f"{condition}:{phase_name}:{duration_note}")

            capture = _match_capture_for_template(condition, template, capture_templates)
            response_window_ms = None
            response_note = ""
            if capture:
                response_window_ms, response_note = _resolve_duration(
                    capture.duration_expr,
                    settings_values=settings_values,
                    var_exprs=var_exprs,
                )
                if response_note:
                    inferred_items.append(f"{condition}:{phase_name}:{response_note}")

            stim_ids = _resolve_stim_ids(
                template.stim_id_expr,
                condition=condition,
                stimuli_cfg=stimuli_cfg,
                var_exprs=var_exprs,
            )
            if not stim_ids:
                stim_ids = _resolve_stim_ids_from_calls(
                    unit_stim_calls.get(template.unit_var, []),
                    condition,
                    stimuli_cfg=stimuli_cfg,
                    var_exprs=var_exprs,
                )

            stim_example = _build_stimulus_example(
                stim_ids=stim_ids,
                condition=condition,
                phase_name=phase_name,
                stimuli_cfg=stimuli_cfg,
                task_dir=task_dir,
            )
            if not stim_ids:
                inferred_items.append(f"{condition}:{phase_name}:stimulus unresolved, used textual fallback")

            phase_rows.append(
                (
                    template.order,
                    {
                        "phase_name": phase_name,
                        "display_phase_label": _display_phase_label(phase_name),
                        "duration_ms": duration_ms,
                        "response_window_ms": response_window_ms,
                        "display_timing_label": _display_timing_label(duration_ms, response_window_ms),
                        "stim_ids": stim_ids,
                        "stimulus_example": stim_example,
                        "notes": _combine_notes(template.predicate_labels, capture.predicate_labels if capture else []),
                    },
                )
            )

            config_evidence.append(
                f"{condition}: phase={phase_name}, deadline_expr={template.deadline_expr}, "
                f"response_expr={capture.duration_expr if capture else 'n/a'}, stim_expr={template.stim_id_expr}"
            )

        for show in sorted(visible_show_templates, key=lambda s: s.order):
            if not _matches_predicates(condition, show.predicates):
                continue
            if _visible_show_has_context(show, condition, phase_templates):
                continue

            phase_name = _phase_name_from_visible_show(
                show,
                condition=condition,
                stimuli_cfg=stimuli_cfg,
                var_exprs=var_exprs,
            )
            duration_ms, duration_note = _resolve_duration(
                show.duration_expr,
                settings_values=settings_values,
                var_exprs=var_exprs,
            )
            if duration_note:
                inferred_items.append(f"{condition}:{phase_name}:{duration_note}")

            stim_ids = _resolve_stim_ids_from_calls(
                show.stim_exprs,
                condition,
                stimuli_cfg=stimuli_cfg,
                var_exprs=var_exprs,
            )
            stim_example = _build_stimulus_example(
                stim_ids=stim_ids,
                condition=condition,
                phase_name=phase_name,
                stimuli_cfg=stimuli_cfg,
                task_dir=task_dir,
            )
            if not stim_ids:
                inferred_items.append(f"{condition}:{phase_name}:stimulus unresolved, used textual fallback")

            warning = (
                f"{condition}:{phase_name}: participant-visible phase inferred from show() "
                "because set_trial_context(...) is missing"
            )
            warning_items.append(warning)
            config_evidence.append(
                f"{condition}: visible_show_without_context phase={phase_name}, "
                f"unit_label_expr={show.unit_label_expr or '(none)'}, duration_expr={show.duration_expr or '(none)'}, "
                f"stim_exprs={show.stim_exprs or []}"
            )
            phase_rows.append(
                (
                    show.order,
                    {
                        "phase_name": phase_name,
                        "display_phase_label": _display_phase_label(phase_name),
                        "duration_ms": duration_ms,
                        "response_window_ms": None,
                        "display_timing_label": _display_timing_label(duration_ms, None),
                        "stim_ids": stim_ids,
                        "stimulus_example": stim_example,
                        "notes": _combine_notes(
                            show.predicate_labels,
                            ["inferred from show() without set_trial_context"],
                        ),
                    },
                )
            )

        phase_rows.sort(key=lambda item: item[0])
        phases = [row[1] for row in phase_rows]
        screens_cap = layout_defaults["screens_per_timeline"]
        if len(phases) > screens_cap:
            phases = phases[:screens_cap]
            inferred_items.append(f"{condition}: phases truncated to screens_per_timeline={screens_cap}")

        if not phases:
            phases = [
                {
                    "phase_name": "trial",
                    "display_phase_label": "Trial",
                    "duration_ms": None,
                    "response_window_ms": None,
                    "display_timing_label": "",
                    "stim_ids": [],
                    "stimulus_example": {
                        "summary": "[unresolved] review run_trial manually",
                        "modality": "other",
                        "draw_hint": "annotation",
                    },
                    "notes": "fallback phase injected",
                }
            ]
            inferred_items.append(f"{condition}: no phase extracted from run_trial; injected fallback phase")

        timelines.append(
            {
                "condition": str(condition),
                "display_condition_label": _display_condition_label(str(condition)),
                "phases": phases,
            }
        )

    timelines = _collapse_similar_timelines(timelines, inferred_items)
    if len(timelines) > layout_defaults["max_conditions"]:
        inferred_items.append(
            f"timelines truncated from {len(timelines)} to {layout_defaults['max_conditions']} by max_conditions"
        )
        timelines = timelines[: layout_defaults["max_conditions"]]
    selected_conditions = [str(t.get("condition", "")) for t in timelines]

    readme_evidence = _extract_trial_flow_evidence(readme_text)
    if unresolved_predicates:
        inferred_items.append(
            "unparsed if-tests defaulted to condition-agnostic applicability: "
            + "; ".join(sorted(set(unresolved_predicates))[:6])
        )

    spec = _build_spec(
        task_name=task_name,
        mode="existing",
        timelines=timelines,
        layout_defaults=layout_defaults,
    )

    source_excerpt = _build_source_excerpt(
        task_name=task_name,
        readme_path=readme_path,
        config_path=config_path,
        run_trial_path=run_trial_path,
        conditions=selected_conditions,
    )

    return {
        "task_name": task_name,
        "spec_root": {"task_plot_spec": spec},
        "audit": {
            "inputs": [str(readme_path), str(config_path), str(run_trial_path)],
            "readme_evidence": readme_evidence,
            "source_evidence": config_evidence,
            "mapping": [
                "timeline collection: one representative timeline per unique trial logic",
                "phase flow inferred from run_trial set_trial_context order and branch predicates",
                "participant-visible show() phases without set_trial_context are inferred where possible and warned",
                "duration/response inferred from deadline/capture expressions",
                "stimulus examples inferred from stim_id + config stimuli",
                "conditions with equivalent phase/timing logic collapsed and annotated as variants",
            ],
            "inferred_items": _dedupe(inferred_items),
            "warnings": _dedupe(warning_items),
            "style_rationale": (
                "Single timeline-collection view selected by policy: one representative condition per unique timeline logic."
            ),
            "source_excerpt": source_excerpt,
        },
    }


def _layout_defaults(config: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "max_conditions": 4,
        "screens_per_timeline": 6,
        "screen_overlap_ratio": 0.10,
        "screen_slope": 0.08,
        "screen_slope_deg": 25.0,
        "timeline_gap": 0.18,
        "screen_aspect_ratio": 16 / 11,
        "left_margin": 0.20,
        "right_margin": 0.03,
        "top_margin": 0.03,
        "bottom_margin": 0.05,
        "condition_label_gap": 0.014,
        "phase_label_pad": 0.010,
        "duration_label_gap": 0.006,
        "timeline_arrow_gap": 0.010,
        "timeline_arrow_screen_clearance": 0.007,
        "timeline_arrow_text_clearance": 0.010,
        "timeline_arrow_extra_per_screen": 0.015,
        "timeline_arrow_min_y": 0.020,
        "timeline_arrow_max_y": 0.96,
    }
    tp = config.get("task_plot")
    if isinstance(tp, dict):
        for key in list(defaults.keys()):
            if key in tp:
                defaults[key] = tp[key]
    return defaults


def _extract_task_name(readme_text: str, fallback: str) -> str:
    for line in readme_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    m = re.search(r"^\|\s*Name\s*\|\s*(.+?)\s*\|", readme_text, flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fallback


def _extract_conditions(config: dict[str, Any]) -> list[str]:
    task = config.get("task")
    if not isinstance(task, dict):
        return []
    conditions = task.get("conditions")
    if not isinstance(conditions, list):
        return []
    return [str(c) for c in conditions if str(c).strip()]


def _build_settings_values(
    timing_cfg: dict[str, Any],
    task_cfg: dict[str, Any],
    controller_cfg: dict[str, Any],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    values.update({str(k): v for k, v in timing_cfg.items()})
    values.update({str(k): v for k, v in task_cfg.items()})
    values.update({str(k): v for k, v in controller_cfg.items()})
    return values


def _extract_phase_templates(tree: ast.AST) -> dict[str, Any]:
    run_trial_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_trial":
            run_trial_fn = node
            break
    if run_trial_fn is None:
        raise ValueError("run_trial function not found in src/run_trial.py")

    phases: list[PhaseTemplate] = []
    captures: list[CaptureTemplate] = []
    visible_shows: list[VisibleShowTemplate] = []
    unit_stims: dict[str, list[str]] = {}
    unit_labels: dict[str, str] = {}
    var_exprs: dict[str, str] = {}
    unresolved_predicates: list[str] = []
    order = 0

    def traverse(stmts: list[ast.stmt], predicates: list[Predicate], labels: list[str]) -> None:
        nonlocal order
        for stmt in stmts:
            _collect_var_assign(stmt, var_exprs, unit_labels)
            _collect_unit_stims(stmt, unit_stims)

            if isinstance(stmt, ast.If):
                pred, label, unresolved = _predicate_from_test(stmt.test)
                if unresolved:
                    unresolved_predicates.append(unresolved)
                traverse(stmt.body, predicates + [pred], labels + [label])
                if stmt.orelse:
                    neg = _negate(pred)
                    traverse(stmt.orelse, predicates + [neg], labels + [f"NOT({label})"])
                continue

            if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
                traverse(stmt.body, predicates, labels)
                if hasattr(stmt, "orelse") and getattr(stmt, "orelse"):
                    traverse(stmt.orelse, predicates, labels)
                continue

            if isinstance(stmt, ast.Try):
                traverse(stmt.body, predicates, labels)
                for handler in stmt.handlers:
                    traverse(handler.body, predicates, labels)
                if stmt.orelse:
                    traverse(stmt.orelse, predicates, labels)
                if stmt.finalbody:
                    traverse(stmt.finalbody, predicates, labels)
                continue

            call = _extract_call(stmt)
            if call is None:
                continue
            order += 1
            if _is_name_call(call, "set_trial_context"):
                unit_var = _name_of_node(call.args[0]) if call.args else "unit"
                phase_expr = _kw_expr(call, "phase")
                deadline_expr = _kw_expr(call, "deadline_s")
                valid_keys_expr = _kw_expr(call, "valid_keys")
                stim_id_expr = _kw_expr(call, "stim_id")
                phases.append(
                    PhaseTemplate(
                        order=order,
                        unit_var=unit_var,
                        phase_expr=phase_expr,
                        deadline_expr=deadline_expr,
                        valid_keys_expr=valid_keys_expr,
                        stim_id_expr=stim_id_expr,
                        predicates=list(predicates),
                        predicate_labels=list(labels),
                    )
                )
            elif _is_attr_call(call, "capture_response"):
                unit_var = _name_of_node(call.func.value) if isinstance(call.func, ast.Attribute) else "unit"
                captures.append(
                    CaptureTemplate(
                        order=order,
                        unit_var=unit_var,
                        duration_expr=_kw_expr(call, "duration"),
                        keys_expr=_kw_expr(call, "keys"),
                        predicates=list(predicates),
                        predicate_labels=list(labels),
                    )
                )
            elif _is_attr_call(call, "show"):
                visible = _extract_visible_show_template(
                    call,
                    order=order,
                    predicates=predicates,
                    labels=labels,
                    unit_stims=unit_stims,
                    unit_labels=unit_labels,
                )
                if visible is not None:
                    visible_shows.append(visible)

    traverse(run_trial_fn.body, [], [])

    return {
        "phases": phases,
        "captures": captures,
        "visible_shows": visible_shows,
        "unit_stims": unit_stims,
        "var_exprs": var_exprs,
        "unresolved_predicates": unresolved_predicates,
    }


def _collect_var_assign(stmt: ast.stmt, var_exprs: dict[str, str], unit_labels: dict[str, str]) -> None:
    if not isinstance(stmt, ast.Assign):
        return
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return
    target = stmt.targets[0].id
    expr = _unparse(stmt.value)
    var_exprs[target] = expr
    unit_label_expr = _extract_unit_label_expr_from_chain(stmt.value)
    if unit_label_expr:
        unit_labels[target] = unit_label_expr


def _collect_unit_stims(stmt: ast.stmt, unit_stims: dict[str, list[str]]) -> None:
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        var = stmt.targets[0].id
        stim_exprs = _extract_add_stim_exprs(stmt.value)
        if stim_exprs:
            unit_stims.setdefault(var, []).extend(stim_exprs)

    call = _extract_call(stmt)
    if call is None or not _is_attr_call(call, "add_stim"):
        return
    if not isinstance(call.func, ast.Attribute):
        return
    var = _name_of_node(call.func.value)
    if not var:
        return
    if call.args:
        unit_stims.setdefault(var, []).append(_unparse(call.args[0]))


def _extract_add_stim_exprs(node: ast.AST) -> list[str]:
    out: list[str] = []
    current = node
    while isinstance(current, ast.Call):
        if isinstance(current.func, ast.Attribute) and current.func.attr == "add_stim" and current.args:
            out.append(_unparse(current.args[0]))
            current = current.func.value
        elif isinstance(current.func, ast.Attribute):
            current = current.func.value
        else:
            break
    out.reverse()
    return out


def _extract_unit_label_expr_from_chain(node: ast.AST) -> str:
    current = node
    while isinstance(current, ast.Call):
        if isinstance(current.func, ast.Name) and current.func.id in {"make_unit", "StimUnit"}:
            kw = _kw_expr(current, "unit_label")
            if kw:
                return kw
            if current.args:
                return _unparse(current.args[0])
            return ""
        if isinstance(current.func, ast.Attribute):
            current = current.func.value
            continue
        break
    return ""


def _extract_visible_show_template(
    call: ast.Call,
    order: int,
    predicates: list[Predicate],
    labels: list[str],
    unit_stims: dict[str, list[str]],
    unit_labels: dict[str, str],
) -> VisibleShowTemplate | None:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "show":
        return None
    base = call.func.value
    unit_var = _name_of_node(base)
    stim_exprs = []
    if unit_var:
        stim_exprs.extend(unit_stims.get(unit_var, []))
    chain_exprs = _extract_add_stim_exprs(base)
    for expr in chain_exprs:
        if expr not in stim_exprs:
            stim_exprs.append(expr)
    if not stim_exprs:
        return None
    unit_label_expr = _extract_unit_label_expr_from_chain(base)
    if not unit_label_expr and unit_var:
        unit_label_expr = unit_labels.get(unit_var, "")
    return VisibleShowTemplate(
        order=order,
        unit_var=unit_var,
        unit_label_expr=unit_label_expr,
        duration_expr=_kw_expr(call, "duration"),
        stim_exprs=stim_exprs,
        predicates=list(predicates),
        predicate_labels=list(labels),
    )


def _extract_call(stmt: ast.stmt) -> ast.Call | None:
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return stmt.value
    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
        return stmt.value
    return None


def _is_name_call(call: ast.Call, name: str) -> bool:
    return isinstance(call.func, ast.Name) and call.func.id == name


def _is_attr_call(call: ast.Call, attr: str) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == attr


def _name_of_node(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _kw_expr(call: ast.Call, key: str) -> str:
    for kw in call.keywords:
        if kw.arg == key:
            return _unparse(kw.value)
    return ""


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _negate(pred: Predicate) -> Predicate:
    return lambda condition, p=pred: not p(condition)


def _predicate_from_test(node: ast.AST) -> tuple[Predicate, str, str]:
    expr = _unparse(node)
    unresolved = ""

    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = _unparse(node.left)
        right = _unparse(node.comparators[0]).strip("'\"")
        op = node.ops[0]

        if left == "cond_kind":
            if isinstance(op, ast.Eq):
                return (lambda c, v=right: _cond_kind(c) == v), f"cond_kind=={right}", unresolved
            if isinstance(op, ast.NotEq):
                return (lambda c, v=right: _cond_kind(c) != v), f"cond_kind!={right}", unresolved

        if left in {"condition", "str(condition)"}:
            if isinstance(op, ast.Eq):
                return (lambda c, v=right: str(c) == v), f"condition=={right}", unresolved
            if isinstance(op, ast.NotEq):
                return (lambda c, v=right: str(c) != v), f"condition!={right}", unresolved
            if isinstance(op, ast.In):
                values = [x.strip("'\" ") for x in right.strip("[](){}").split(",") if x.strip()]
                return (lambda c, arr=values: str(c) in arr), f"condition in {values}", unresolved
            if isinstance(op, ast.NotIn):
                values = [x.strip("'\" ") for x in right.strip("[](){}").split(",") if x.strip()]
                return (lambda c, arr=values: str(c) not in arr), f"condition not in {values}", unresolved

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        func = node.func
        if func.attr == "startswith" and node.args:
            target = _unparse(func.value)
            prefix = _unparse(node.args[0]).strip("'\"")
            if target in {"condition", "str(condition)"}:
                return (
                    lambda c, p=prefix: str(c).startswith(p),
                    f"condition.startswith({prefix})",
                    unresolved,
                )

    if isinstance(node, ast.BoolOp) and node.values:
        parts = [_predicate_from_test(v) for v in node.values]
        funcs = [p[0] for p in parts]
        labels = [p[1] for p in parts]
        unresolved_parts = [p[2] for p in parts if p[2]]
        unresolved = "; ".join(unresolved_parts)
        if isinstance(node.op, ast.And):
            return (
                lambda c, fs=funcs: all(f(c) for f in fs),
                " AND ".join(labels),
                unresolved,
            )
        if isinstance(node.op, ast.Or):
            return (
                lambda c, fs=funcs: any(f(c) for f in fs),
                " OR ".join(labels),
                unresolved,
            )

    unresolved = expr if expr else "<unknown if test>"
    return (lambda _c: True), "unparsed_condition_test", unresolved


def _cond_kind(condition: str) -> str:
    value = str(condition)
    if "_" in value:
        return value.split("_", 1)[0]
    return value


def _matches_predicates(condition: str, predicates: list[Predicate]) -> bool:
    return all(pred(condition) for pred in predicates)


def _match_capture_for_template(
    condition: str,
    template: PhaseTemplate,
    captures: list[CaptureTemplate],
) -> CaptureTemplate | None:
    cands = [
        c
        for c in captures
        if c.unit_var == template.unit_var and c.order >= template.order and _matches_predicates(condition, c.predicates)
    ]
    if not cands:
        return None
    cands.sort(key=lambda x: x.order)
    return cands[0]


def _resolve_phase_name(phase_expr: str) -> str:
    s = phase_expr.strip()
    if not s:
        return "phase"
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1]
    s = s.replace("_", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:48] if s else "phase"


def _resolve_duration(
    expr: str,
    settings_values: dict[str, Any],
    var_exprs: dict[str, str],
) -> tuple[dict[str, Any] | None, str]:
    expr = (expr or "").strip()
    if not expr:
        return None, "duration expression missing"

    if re.fullmatch(r"-?\d+(\.\d+)?", expr):
        value = float(expr)
        return {"fixed": _num_to_ms(value)}, ""

    if expr.startswith("[") or expr.startswith("("):
        nums = re.findall(r"-?\d+(?:\.\d+)?", expr)
        if len(nums) >= 2:
            lo = _num_to_ms(float(nums[0]))
            hi = _num_to_ms(float(nums[1]))
            return {"range": [min(lo, hi), max(lo, hi)]}, ""

    m = re.fullmatch(r"settings\.([A-Za-z_][A-Za-z0-9_]*)", expr)
    if m:
        key = m.group(1)
        if key in settings_values:
            return _value_to_duration(settings_values[key]), ""
        return None, f"settings key '{key}' not found"

    m = re.fullmatch(r"_deadline_s\((.+)\)", expr)
    if m:
        inner = m.group(1).strip()
        return _resolve_duration(inner, settings_values, var_exprs)

    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr):
        if expr in var_exprs:
            return _resolve_duration(var_exprs[expr], settings_values, var_exprs)
        if expr in settings_values:
            return _value_to_duration(settings_values[expr]), ""
        if "ssd" in expr.lower():
            rng = _ssd_range(settings_values)
            return {"range": rng}, ""
        return None, f"unresolved variable '{expr}'"

    m = re.search(r'getattr\(settings,\s*"([^"]+)"\s*,\s*([^)]+)\)', expr)
    if m:
        key = m.group(1)
        default_expr = m.group(2).strip()
        if key in settings_values:
            return _value_to_duration(settings_values[key]), ""
        if re.fullmatch(r"-?\d+(\.\d+)?", default_expr):
            return {"fixed": _num_to_ms(float(default_expr))}, f"used getattr default for '{key}'"
        return None, f"getattr key '{key}' unresolved"

    if "ssd" in expr.lower():
        ssd_rng = _ssd_range(settings_values)
        if "-" in expr and "go_duration" in expr:
            go_value = settings_values.get("go_duration")
            go_ms = _num_to_ms(float(go_value)) if isinstance(go_value, (int, float)) else 1000
            lo = max(0, go_ms - ssd_rng[1])
            hi = max(0, go_ms - ssd_rng[0])
            return {"range": [lo, hi]}, ""
        return {"range": ssd_rng}, ""

    nums = re.findall(r"-?\d+(?:\.\d+)?", expr)
    if len(nums) == 1:
        return {"fixed": _num_to_ms(float(nums[0]))}, f"heuristic numeric parse from '{expr}'"
    if len(nums) >= 2:
        lo = _num_to_ms(float(nums[0]))
        hi = _num_to_ms(float(nums[1]))
        return {"range": [min(lo, hi), max(lo, hi)]}, f"heuristic range parse from '{expr}'"

    return None, f"unable to resolve duration from '{expr}'"


def _ssd_range(settings_values: dict[str, Any]) -> list[int]:
    lo = settings_values.get("min_ssd")
    hi = settings_values.get("max_ssd")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        lo_ms = _num_to_ms(float(lo))
        hi_ms = _num_to_ms(float(hi))
        return [min(lo_ms, hi_ms), max(lo_ms, hi_ms)]
    return [50, 500]


def _value_to_duration(value: Any) -> dict[str, Any] | None:
    if isinstance(value, (int, float)):
        return {"fixed": _num_to_ms(float(value))}
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        lo = _num_to_ms(float(value[0]))
        hi = _num_to_ms(float(value[1]))
        return {"range": [min(lo, hi), max(lo, hi)]}
    return None


def _num_to_ms(value: float) -> int:
    if abs(value) <= 20:
        return int(round(value * 1000.0))
    return int(round(value))


def _eval_expr_value(
    expr: str,
    condition: str,
    var_exprs: dict[str, str],
    *,
    depth: int = 0,
) -> Any | None:
    if depth > 8:
        return None
    expr = (expr or "").strip()
    if not expr:
        return None
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None
    return _eval_expr_node(node, condition=condition, var_exprs=var_exprs, depth=depth)


def _eval_expr_node(
    node: ast.AST,
    condition: str,
    var_exprs: dict[str, str],
    *,
    depth: int,
) -> Any | None:
    if depth > 8:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "condition":
            return condition
        if node.id in var_exprs:
            return _eval_expr_value(var_exprs[node.id], condition, var_exprs, depth=depth + 1)
        return None
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            resolved = _eval_expr_node(value, condition, var_exprs, depth=depth + 1)
            if resolved is None:
                return None
            parts.append(str(resolved))
        return "".join(parts)
    if isinstance(node, ast.FormattedValue):
        resolved = _eval_expr_node(node.value, condition, var_exprs, depth=depth + 1)
        return None if resolved is None else str(resolved)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _eval_expr_node(node.left, condition, var_exprs, depth=depth + 1)
        right = _eval_expr_node(node.right, condition, var_exprs, depth=depth + 1)
        if left is None or right is None:
            return None
        if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
            return None
        return f"{left}{right}"
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
            resolved = _eval_expr_node(node.args[0], condition, var_exprs, depth=depth + 1)
            return None if resolved is None else str(resolved)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "replace" and node.args:
            base = _eval_expr_node(node.func.value, condition, var_exprs, depth=depth + 1)
            old = _eval_expr_node(node.args[0], condition, var_exprs, depth=depth + 1)
            new = _eval_expr_node(node.args[1], condition, var_exprs, depth=depth + 1) if len(node.args) > 1 else ""
            if isinstance(base, str) and isinstance(old, str) and isinstance(new, str):
                return base.replace(old, new)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"lower", "upper"}:
            base = _eval_expr_node(node.func.value, condition, var_exprs, depth=depth + 1)
            if isinstance(base, str):
                return getattr(base, node.func.attr)()
        return None
    if isinstance(node, ast.Subscript):
        base = _eval_expr_node(node.value, condition, var_exprs, depth=depth + 1)
        if base is None:
            return None
        idx_node = node.slice
        if isinstance(idx_node, ast.Index):  # pragma: no cover
            idx_node = idx_node.value
        idx = _eval_expr_node(idx_node, condition, var_exprs, depth=depth + 1)
        try:
            return base[idx]
        except Exception:  # noqa: BLE001
            return None
    if isinstance(node, ast.Tuple):
        vals = [_eval_expr_node(item, condition, var_exprs, depth=depth + 1) for item in node.elts]
        return vals if all(v is not None for v in vals) else None
    if isinstance(node, ast.List):
        vals = [_eval_expr_node(item, condition, var_exprs, depth=depth + 1) for item in node.elts]
        return vals if all(v is not None for v in vals) else None
    if isinstance(node, ast.IfExp):
        test = _eval_expr_node(node.test, condition, var_exprs, depth=depth + 1)
        if isinstance(test, bool):
            branch = node.body if test else node.orelse
            return _eval_expr_node(branch, condition, var_exprs, depth=depth + 1)
        return None
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
        left = _eval_expr_node(node.left, condition, var_exprs, depth=depth + 1)
        right = _eval_expr_node(node.comparators[0], condition, var_exprs, depth=depth + 1)
        if left is None or right is None:
            return None
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _eval_expr_node(node.operand, condition, var_exprs, depth=depth + 1)
        if isinstance(value, (int, float)):
            return -value
    return None


def _strings_from_value(value: Any) -> list[str]:
    if isinstance(value, str):
        return _split_compound_stim_id(value)
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.extend(_split_compound_stim_id(item))
        return out
    return []


def _resolve_stim_ids(
    expr: str,
    condition: str,
    stimuli_cfg: dict[str, Any],
    var_exprs: dict[str, str],
) -> list[str]:
    expr = (expr or "").strip()
    if not expr:
        return []

    resolved = _strings_from_value(_eval_expr_value(expr, condition, var_exprs))
    if resolved:
        return _dedupe_preserve_order(resolved)

    if (expr.startswith("'") and expr.endswith("'")) or (expr.startswith('"') and expr.endswith('"')):
        token = expr[1:-1]
        return _split_compound_stim_id(token)

    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr):
        if expr in var_exprs and var_exprs[expr] != expr:
            return _resolve_stim_ids(var_exprs[expr], condition, stimuli_cfg, var_exprs)
        if expr.endswith("_id"):
            prefix = expr[:-3]
            matches = [k for k in stimuli_cfg.keys() if str(k).startswith(prefix + "_")]
            if matches:
                return [matches[0]]
        return []

    if expr in {"str(condition)", "condition"}:
        return [condition]

    m = re.fullmatch(
        r"condition\.replace\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
        expr,
    )
    if m:
        return [condition.replace(m.group(1), m.group(2))]

    if "+" in expr and all(part.strip().startswith(("'", '"')) for part in expr.split("+")):
        ids = []
        for part in expr.split("+"):
            part = part.strip()
            if (part.startswith("'") and part.endswith("'")) or (part.startswith('"') and part.endswith('"')):
                ids.extend(_split_compound_stim_id(part[1:-1]))
        return ids

    m = re.search(r'get(?:_and_format)?\(\s*"([^"]+)"', expr)
    if m:
        return [m.group(1)]

    return []


def _split_compound_stim_id(token: str) -> list[str]:
    parts = [p.strip() for p in token.split("+") if p.strip()]
    return parts if parts else [token.strip()]


def _resolve_stim_ids_from_calls(
    stim_exprs: list[str],
    condition: str,
    *,
    stimuli_cfg: dict[str, Any],
    var_exprs: dict[str, str],
) -> list[str]:
    out = []
    for stim_expr in stim_exprs:
        out.extend(_extract_stim_ids_from_call_expr(stim_expr, condition, stimuli_cfg=stimuli_cfg, var_exprs=var_exprs))
    return _dedupe_preserve_order(out)


def _extract_stim_ids_from_call_expr(
    stim_expr: str,
    condition: str,
    *,
    stimuli_cfg: dict[str, Any],
    var_exprs: dict[str, str],
) -> list[str]:
    expr = (stim_expr or "").strip()
    if not expr:
        return []
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError:
        node = None
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"get", "get_and_format", "rebuild"} and node.args:
            value = _eval_expr_node(node.args[0], condition, var_exprs, depth=0)
            strings = _strings_from_value(value)
            if strings:
                return _dedupe_preserve_order(strings)
    out = _resolve_stim_ids(expr, condition=condition, stimuli_cfg=stimuli_cfg, var_exprs=var_exprs)
    if out:
        return out
    m = re.search(r'get(?:_and_format|_and_rebuild|_or_none|)?\(\s*"([^"]+)"', expr)
    if m:
        return [m.group(1)]
    return []


def _build_stimulus_example(
    stim_ids: list[str],
    condition: str,
    phase_name: str,
    stimuli_cfg: dict[str, Any],
    task_dir: Path,
) -> dict[str, Any]:
    if not stim_ids:
        return {
            "summary": f"[annotation] {phase_name}",
            "modality": "other",
            "draw_hint": "annotation",
            "render_items": [{"kind": "annotation", "text": f"{phase_name}"}],
        }

    parts = []
    modalities = set()
    draw_hints = set()
    render_items: list[dict[str, Any]] = []
    for stim_id in stim_ids:
        stim = stimuli_cfg.get(stim_id)
        if isinstance(stim, dict):
            text_type = str(stim.get("type", "")).lower()
            if text_type in {"text", "textbox"}:
                raw = str(stim.get("text", stim_id))
                example = _fill_placeholder_text(raw, condition=condition)
                parts.append(example)
                modalities.add("visual")
                draw_hints.add("text")
                render_items.append(
                    {
                        "kind": "text",
                        "text": example,
                        "color": _color_token(stim.get("color")),
                        "pos": _extract_pos_token(stim.get("pos")),
                        "height": _extract_text_height(stim.get("height")),
                    }
                )
            elif text_type in {"shape", "polygon"}:
                token = _shape_token(stim_id, condition)
                parts.append(token["label"])
                modalities.add("visual")
                draw_hints.add("shape")
                token["kind"] = "shape"
                token["color"] = _color_token(stim.get("fillColor"))
                token["pos"] = _extract_pos_token(stim.get("pos"))
                token["size"] = _extract_size_token(stim.get("size"))
                render_items.append(token)
            elif "sound" in text_type or "audio" in text_type:
                parts.append(f"[audio:{stim_id}]")
                modalities.add("audio")
                draw_hints.add("annotation")
                render_items.append({"kind": "annotation", "text": f"Audio: {stim_id}"})
            elif "movie" in text_type or "video" in text_type:
                parts.append(f"[video:{stim_id}]")
                modalities.add("visual")
                draw_hints.add("annotation")
                render_items.append({"kind": "annotation", "text": f"Video: {stim_id}"})
            elif "image" in text_type:
                image_path = _resolve_stim_asset_path(task_dir, stim)
                parts.append(_shorten(stim_id))
                modalities.add("visual")
                draw_hints.add("image")
                render_items.append(
                    {
                        "kind": "image_ref",
                        "path": str(image_path) if image_path else "",
                        "label": stim_id,
                    }
                )
            else:
                parts.append(f"[{text_type or 'stim'}:{stim_id}]")
                modalities.add("other")
                draw_hints.add("annotation")
                render_items.append({"kind": "annotation", "text": f"{text_type or 'stim'}: {stim_id}"})
        else:
            parts.append(f"[dynamic:{stim_id}]")
            modalities.add("other")
            draw_hints.add("annotation")
            render_items.append({"kind": "annotation", "text": f"Dynamic: {stim_id}"})

    summary = " + ".join(_shorten(p) for p in parts)
    modality = "mixed" if len(modalities) > 1 else (next(iter(modalities)) if modalities else "other")
    draw_hint = "annotation" if "annotation" in draw_hints else (next(iter(draw_hints)) if draw_hints else "text")
    return {
        "summary": summary,
        "modality": modality,
        "draw_hint": draw_hint,
        "render_items": render_items,
    }


def _resolve_stim_asset_path(task_dir: Path, stim: dict[str, Any]) -> Path | None:
    for key in ("image", "file", "filename", "path"):
        value = stim.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value.strip())
        if not path.is_absolute():
            path = (task_dir / path).resolve()
        if path.exists():
            return path
    return None


def _shape_token(stim_id: str, condition: str) -> dict[str, str]:
    sid = (stim_id or "").lower()
    cond = (condition or "").lower()
    text = sid or cond
    if "left" in text:
        return {"shape": "arrow_left", "label": "Left Arrow"}
    if "right" in text:
        return {"shape": "arrow_right", "label": "Right Arrow"}
    if "stop" in text:
        return {"shape": "stop", "label": "Stop Signal"}
    return {"shape": "generic", "label": f"Shape: {stim_id}"}


def _color_token(value: Any) -> str:
    if isinstance(value, str):
        token = value.strip().lower()
        if token:
            return token
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            rgb = [float(value[0]), float(value[1]), float(value[2])]
            # PsychoPy color triples may be either [-1,1] or [0,1].
            if all(-1.0 <= x <= 1.0 for x in rgb):
                rgb = [(x + 1.0) / 2.0 for x in rgb]
            return "#{:02x}{:02x}{:02x}".format(
                int(max(0, min(1, rgb[0])) * 255),
                int(max(0, min(1, rgb[1])) * 255),
                int(max(0, min(1, rgb[2])) * 255),
            )
        except Exception:
            return ""
    return ""


def _extract_pos_token(value: Any) -> list[float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        x = _float_or_none(value[0])
        y = _float_or_none(value[1])
        if x is not None and y is not None:
            return [x, y]
    return None


def _extract_size_token(value: Any) -> float | list[float] | None:
    if isinstance(value, (int, float)):
        v = _float_or_none(value)
        return v if v is not None else None
    if isinstance(value, (list, tuple)) and value:
        vals = []
        for item in value[:2]:
            num = _float_or_none(item)
            if num is not None:
                vals.append(num)
        if vals:
            return vals
    return None


def _extract_text_height(value: Any) -> float | None:
    return _float_or_none(value)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _fill_placeholder_text(raw: str, condition: str) -> str:
    sample_map = {
        "old_key": "F",
        "new_key": "J",
        "left_key": "F",
        "right_key": "J",
        "probe_item": "X",
        "memory_set_display": "B D F",
        "score_delta": "1",
        "score_after": "10",
        "correct_key": "F",
        "condition": condition,
    }
    line = raw.strip().splitlines()[0] if raw.strip() else ""
    line = re.sub(r"\{([A-Za-z0-9_:.%+-]+)\}", lambda m: sample_map.get(m.group(1).split(":")[0], "…"), line)
    return _shorten(line if line else "[text]")


def _visible_show_has_context(
    show: VisibleShowTemplate,
    condition: str,
    phase_templates: list[PhaseTemplate],
) -> bool:
    if not show.unit_var:
        return False
    for template in phase_templates:
        if template.unit_var != show.unit_var:
            continue
        if _matches_predicates(condition, template.predicates):
            return True
    return False


def _phase_name_from_visible_show(
    show: VisibleShowTemplate,
    *,
    condition: str,
    stimuli_cfg: dict[str, Any],
    var_exprs: dict[str, str],
) -> str:
    unit_label = _eval_expr_value(show.unit_label_expr, condition, var_exprs)
    if isinstance(unit_label, str) and unit_label.strip():
        return _normalize_phase_seed(unit_label)
    stim_ids = _resolve_stim_ids_from_calls(
        show.stim_exprs,
        condition,
        stimuli_cfg=stimuli_cfg,
        var_exprs=var_exprs,
    )
    if stim_ids:
        return _phase_name_from_stim_ids(stim_ids)
    if show.unit_var:
        return _normalize_phase_seed(show.unit_var)
    return "visible_phase"


def _phase_name_from_stim_ids(stim_ids: list[str]) -> str:
    if not stim_ids:
        return "visible_phase"
    preferred = next((sid for sid in stim_ids if "sound" not in sid.lower() and "audio" not in sid.lower()), stim_ids[0])
    low = preferred.lower()
    if low == "fixation":
        return "fixation"
    if low.startswith("cue_"):
        return "cue"
    if low.startswith("probe_"):
        return "probe"
    if low.endswith("_balloon"):
        return "pump_decision"
    if low.endswith("_pop"):
        return "pop_outcome"
    if low.endswith("_feedback"):
        return "feedback"
    if low.endswith("_screen"):
        return _normalize_phase_seed(low.rsplit("_", 1)[0])
    return _normalize_phase_seed(preferred)


def _normalize_phase_seed(text: str) -> str:
    raw = str(text or "").strip().strip("'\"")
    raw = re.sub(r"[^A-Za-z0-9_ -]+", "_", raw)
    raw = raw.replace("-", "_").replace(" ", "_")
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw.lower() or "visible_phase"


def _shorten(text: str, n: int = 46) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _combine_notes(*label_lists: list[str]) -> str:
    labels = []
    for arr in label_lists:
        for item in arr:
            if item and item not in labels:
                labels.append(item)
    if not labels:
        return ""
    return " / ".join(labels)[:120]


def _collapse_similar_timelines(
    timelines: list[dict[str, Any]],
    inferred_items: list[str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    order: list[tuple[Any, ...]] = []

    for timeline in timelines:
        signature = _timeline_logic_signature(timeline)
        if signature not in grouped:
            grouped[signature] = []
            order.append(signature)
        grouped[signature].append(timeline)

    collapsed: list[dict[str, Any]] = []
    for signature in order:
        members = grouped[signature]
        rep = dict(members[0])
        variants = [str(t.get("condition", "")).strip() for t in members[1:] if str(t.get("condition", "")).strip()]
        if variants:
            rep["condition_variants"] = variants
            rep["display_condition_note"] = "Also: " + ", ".join(_display_condition_label(v) for v in variants)
            all_names = [str(rep.get("condition", ""))] + variants
            inferred_items.append("collapsed equivalent condition logic into representative timeline: " + ", ".join(all_names))
        collapsed.append(rep)
    return collapsed


def _timeline_logic_signature(timeline: dict[str, Any]) -> tuple[Any, ...]:
    phases = timeline.get("phases", [])
    signature: list[tuple[str, str, str]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_name = _norm_text(str(phase.get("phase_name", "")))
        duration_sig = _duration_signature(phase.get("duration_ms"))
        response_sig = _duration_signature(phase.get("response_window_ms"))
        signature.append((phase_name, duration_sig, response_sig))
    return tuple(signature)


def _duration_signature(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    if "fixed" in value:
        try:
            return f"fixed:{int(round(float(value['fixed'])))}"
        except Exception:  # noqa: BLE001
            return "fixed:invalid"
    if "range" in value and isinstance(value["range"], list) and len(value["range"]) == 2:
        try:
            lo = int(round(float(value["range"][0])))
            hi = int(round(float(value["range"][1])))
            return f"range:{lo}-{hi}"
        except Exception:  # noqa: BLE001
            return "range:invalid"
    return ""


def _norm_text(text: str) -> str:
    return " ".join(str(text).strip().lower().replace("_", " ").split())


def _build_spec(
    task_name: str,
    mode: str,
    timelines: list[dict[str, Any]],
    layout_defaults: dict[str, Any],
) -> dict[str, Any]:
    return {
        "spec_version": "0.2",
        "meta": {
            "task_name": task_name,
            "mode": mode,
        },
        "figure": {
            "output": {
                "filename": "task_flow.png",
                "dpi": 300,
                "width_in": 16.0,
                "background": "white",
            },
            "layout": layout_defaults,
        },
        "timelines": timelines,
        "legend": [],
    }


def _display_condition_label(text: str) -> str:
    return _cap_label(text)


def _display_phase_label(text: str) -> str:
    raw = " ".join(str(text).replace("_", " ").replace("-", " ").split())
    low = raw.lower()
    if not low:
        return "Phase"
    if "fix" in low:
        return "Fixation"
    if "inter trial" in low or low == "iti" or " iti " in f" {low} ":
        return "ITI"
    if "stop signal" in low or ("stop" in low and "signal" in low):
        return "Stop Signal"
    if "pre stop" in low and "go" in low:
        return "GO"
    if low.startswith("go ") or " go " in f" {low} ":
        if "window" in low or "response" in low or low.strip() == "go":
            return "GO"
    if "memory set" in low or "encoding" in low:
        return "Memory Set"
    if "retention" in low:
        return "Retention"
    if "delay" in low:
        return "Delay"
    if "probe" in low:
        return "Probe"
    if "feedback" in low:
        return "Feedback"
    if "cue" in low:
        return "Cue"
    if "target" in low:
        return "Target"
    compact = re.sub(r"\b(phase|window|screen|response)\b", "", low)
    compact = " ".join(compact.split())
    return _shorten(_cap_label(compact or raw), 20)


def _display_timing_label(duration_ms: dict[str, Any] | None, response_window_ms: dict[str, Any] | None) -> str:
    d = _duration_to_text(duration_ms)
    r = _duration_to_text(response_window_ms)
    if d and r:
        if d == r:
            return d
        return f"{d} | Resp {r}"
    if d:
        return d
    if r:
        return f"Resp {r}"
    return ""


def _duration_to_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    if "fixed" in value:
        return f"{int(round(float(value['fixed'])))} ms"
    if "range" in value and isinstance(value["range"], list) and len(value["range"]) == 2:
        lo = int(round(float(value["range"][0])))
        hi = int(round(float(value["range"][1])))
        return f"{lo}-{hi} ms"
    return None


def _cap_label(text: str) -> str:
    raw = " ".join(str(text).replace("_", " ").replace("-", " ").split())
    if not raw:
        return raw
    words = []
    for w in raw.split(" "):
        wl = w.lower()
        if wl in {"iti", "ssd", "rt"}:
            words.append(wl.upper())
        elif len(w) <= 2 and w.isupper():
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _extract_trial_flow_evidence(readme_text: str) -> list[str]:
    lines = readme_text.splitlines()
    out = []
    in_trial = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower() == "### trial-level flow":
            in_trial = True
            continue
        if in_trial and stripped.startswith("### "):
            break
        if in_trial and "|" in stripped and stripped.startswith("|"):
            out.append(stripped)
    if not out:
        out.append("Trial-Level Flow table not found; run_trial.py used as primary source.")
    return out[:20]


def _build_source_excerpt(
    task_name: str,
    readme_path: Path,
    config_path: Path,
    run_trial_path: Path,
    conditions: list[str],
) -> str:
    lines = [
        f"# Source Excerpt ({task_name})",
        "",
        "## Input Files",
        f"- README: {readme_path}",
        f"- Config: {config_path}",
        f"- run_trial: {run_trial_path}",
        "",
        "## Selected Conditions",
        "- " + ", ".join(conditions),
        "",
        "## Note",
        "- Timelines were inferred from run_trial phase/context calls with condition-branch filtering.",
    ]
    return "\n".join(lines).strip() + "\n"


def _dedupe(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    return _dedupe(items)

