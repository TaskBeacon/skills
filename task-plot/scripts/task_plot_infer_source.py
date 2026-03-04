#!/usr/bin/env python3
"""Infer timeline-collection task_plot_spec from source inputs."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import fitz
import requests
from bs4 import BeautifulSoup


def infer_from_source(
    source_kind: str,
    source_value: str,
    max_conditions: int = 4,
    screens_per_timeline: int = 6,
) -> dict:
    text, provenance = _load_source_text(source_kind, source_value)
    task_name = _infer_task_name(text, provenance)

    phases, phase_evidence, inferred_items = _extract_phases(text)
    conditions = _extract_conditions(text)
    if not conditions:
        conditions = ["default"]
        inferred_items.append("no explicit conditions found; injected default condition")

    selected_conditions = list(conditions)

    timelines = []
    for condition in selected_conditions:
        condition_phases = []
        for phase in phases[:screens_per_timeline]:
            condition_phases.append(
                {
                    "phase_name": phase["phase_name"],
                    "display_phase_label": _display_phase_label(phase["phase_name"]),
                    "duration_ms": phase.get("duration_ms"),
                    "response_window_ms": phase.get("response_window_ms"),
                    "display_timing_label": _display_timing_label(
                        phase.get("duration_ms"),
                        phase.get("response_window_ms"),
                    ),
                    "stim_ids": [],
                    "stimulus_example": {
                        "summary": phase.get("summary", "[annotation]"),
                        "modality": phase.get("modality", "other"),
                        "draw_hint": phase.get("draw_hint", "annotation"),
                        "render_items": [{"kind": "text", "text": phase.get("summary", "Stimulus")}],
                    },
                    "notes": "source-derived phase",
                }
            )
        if not condition_phases:
            condition_phases = [
                {
                    "phase_name": "trial",
                    "display_phase_label": "Trial",
                    "duration_ms": None,
                    "response_window_ms": None,
                    "display_timing_label": "",
                    "stim_ids": [],
                    "stimulus_example": {
                        "summary": "[annotation] no parseable phase found",
                        "modality": "other",
                        "draw_hint": "annotation",
                        "render_items": [{"kind": "annotation", "text": "No Parseable Phase Found"}],
                    },
                    "notes": "fallback phase injected",
                }
            ]
            inferred_items.append(f"{condition}: no phase parsed; fallback inserted")

        timelines.append(
            {
                "condition": condition,
                "display_condition_label": _display_condition_label(condition),
                "phases": condition_phases,
            }
        )

    timelines = _collapse_similar_timelines(timelines, inferred_items)
    if len(timelines) > max_conditions:
        inferred_items.append(f"timelines truncated from {len(timelines)} to {max_conditions} by max_conditions")
        timelines = timelines[:max_conditions]
    selected_conditions = [str(t.get("condition", "")) for t in timelines]

    spec = {
        "spec_version": "0.2",
        "meta": {"task_name": task_name, "mode": "source"},
        "figure": {
            "output": {
                "filename": "task_flow.png",
                "dpi": 300,
                "width_in": 16.0,
                "background": "white",
            },
            "layout": {
                "max_conditions": max_conditions,
                "screens_per_timeline": screens_per_timeline,
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
            },
        },
        "timelines": timelines,
        "legend": [],
    }

    source_excerpt = _build_source_excerpt(task_name, text, selected_conditions, phases)

    return {
        "task_name": task_name,
        "spec_root": {"task_plot_spec": spec},
        "audit": {
            "inputs": [provenance],
            "readme_evidence": ["N/A (source mode)"] ,
            "source_evidence": phase_evidence,
            "mapping": [
                "timeline collection: one representative timeline per unique source-derived logic",
                "phase order inferred by keyword order in source",
                "duration/response window inferred from nearby numeric units",
                "conditions with equivalent phase/timing logic collapsed and annotated as variants",
            ],
            "inferred_items": inferred_items,
            "style_rationale": "Single timeline-collection view selected by policy: one representative condition per unique timeline logic.",
            "source_excerpt": source_excerpt,
        },
    }


def _load_source_text(source_kind: str, source_value: str) -> tuple[str, str]:
    if source_kind == "pdf":
        path = Path(source_value)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        doc = fitz.open(path)
        parts = [page.get_text("text") for page in doc]
        return _normalize_text("\n".join(parts)), f"pdf:{path}"

    if source_kind == "url":
        resp = requests.get(source_value, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        tags = soup.find_all(["h1", "h2", "h3", "p", "li"])
        parts = []
        for tag in tags[:600]:
            text = tag.get_text(" ", strip=True)
            if text:
                parts.append(text)
        return _normalize_text("\n".join(parts)), f"url:{source_value}"

    if source_kind == "methods_file":
        path = Path(source_value)
        if not path.exists():
            raise FileNotFoundError(f"methods file not found: {path}")
        return _normalize_text(path.read_text(encoding="utf-8", errors="ignore")), f"methods_file:{path}"

    if source_kind == "methods_text":
        return _normalize_text(source_value), "methods_text:inline"

    raise ValueError(f"unsupported source kind: {source_kind}")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _infer_task_name(text: str, provenance: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        if 4 <= len(line) <= 100 and not re.search(r"\d{4}", line):
            return line[:80]
    if provenance.startswith("url:"):
        parsed = urlparse(provenance[4:])
        token = parsed.path.strip("/").split("/")[-1] or parsed.netloc
        token = token.replace("-", " ").replace("_", " ")
        return token[:80] if token else "Source-derived Task"
    return "Source-derived Task"


def _extract_conditions(text: str) -> list[str]:
    condition_words = [
        "go",
        "stop",
        "congruent",
        "incongruent",
        "neutral",
        "match",
        "nomatch",
        "old",
        "new",
        "easy",
        "hard",
        "reward",
        "loss",
    ]
    lower = text.lower()
    out = []
    for word in condition_words:
        if re.search(rf"\b{re.escape(word)}\b", lower):
            out.append(word)
    return out


def _collapse_similar_timelines(
    timelines: list[dict],
    inferred_items: list[str],
) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for timeline in timelines:
        signature = _timeline_logic_signature(timeline)
        if signature not in grouped:
            grouped[signature] = []
            order.append(signature)
        grouped[signature].append(timeline)

    collapsed: list[dict] = []
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


def _timeline_logic_signature(timeline: dict) -> tuple:
    phases = timeline.get("phases", [])
    signature: list[tuple[str, str, str]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_name = " ".join(str(phase.get("phase_name", "")).strip().lower().replace("_", " ").split())
        duration_sig = _duration_signature(phase.get("duration_ms"))
        response_sig = _duration_signature(phase.get("response_window_ms"))
        signature.append((phase_name, duration_sig, response_sig))
    return tuple(signature)


def _duration_signature(value: object) -> str:
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


def _extract_phases(text: str) -> tuple[list[dict], list[str], list[str]]:
    phase_aliases = [
        ("Fixation", [r"\bfixation\b"]),
        ("Cue", [r"\bcue\b"]),
        ("Memory Set", [r"\bmemory set\b", r"\bencoding\b"]),
        ("Delay", [r"\bdelay\b", r"\bretention\b"]),
        ("Target", [r"\btarget\b", r"\bstimulus\b"]),
        ("Probe", [r"\bprobe\b"]),
        ("Response", [r"\bresponse\b"]),
        ("Feedback", [r"\bfeedback\b"]),
        ("Inter-Trial Interval", [r"\binter[- ]trial interval\b", r"\biti\b"]),
    ]

    hits = []
    lower = text.lower()
    for phase_name, patterns in phase_aliases:
        pos = None
        for pattern in patterns:
            m = re.search(pattern, lower)
            if m:
                pos = m.start()
                break
        if pos is not None:
            duration = _find_duration_near(text, pos)
            response = _find_response_window_near(text, pos)
            hits.append((pos, phase_name, duration, response))

    hits.sort(key=lambda x: x[0])
    phases = []
    evidence = []
    inferred = []
    seen = set()
    for _, phase_name, duration, response in hits:
        key = phase_name.lower()
        if key in seen:
            continue
        seen.add(key)
        phases.append(
            {
                "phase_name": phase_name,
                "duration_ms": duration,
                "response_window_ms": response,
                "summary": _phase_summary(phase_name),
                "modality": "visual" if phase_name.lower() != "feedback" else "mixed",
                "draw_hint": "text",
            }
        )
        evidence.append(f"phase={phase_name}; duration={duration}; response_window={response}")
        if duration is None:
            inferred.append(f"duration missing for phase '{phase_name}'")

    if not phases:
        inferred.append("no phase keywords parsed from source")

    return phases, evidence, inferred


def _find_duration_near(text: str, pos: int) -> dict | None:
    start = max(0, pos - 220)
    end = min(len(text), pos + 220)
    window = text[start:end]

    range_pat = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(\d+(?:\.\d+)?)\s*(ms|msec|milliseconds|s|sec|seconds)",
        flags=re.IGNORECASE,
    )
    fixed_pat = re.compile(
        r"(\d+(?:\.\d+)?)\s*(ms|msec|milliseconds|s|sec|seconds)",
        flags=re.IGNORECASE,
    )

    m = range_pat.search(window)
    if m:
        lo = _unit_to_ms(float(m.group(1)), m.group(3))
        hi = _unit_to_ms(float(m.group(2)), m.group(3))
        return {"range": [min(lo, hi), max(lo, hi)]}

    m = fixed_pat.search(window)
    if m:
        return {"fixed": _unit_to_ms(float(m.group(1)), m.group(2))}

    return None


def _find_response_window_near(text: str, pos: int) -> dict | None:
    start = max(0, pos - 220)
    end = min(len(text), pos + 220)
    window = text[start:end]
    if not re.search(r"response|respond|press|withhold", window, flags=re.IGNORECASE):
        return None
    return _find_duration_near(text, pos)


def _unit_to_ms(value: float, unit: str) -> int:
    u = unit.lower()
    if u.startswith("s"):
        return int(round(value * 1000))
    return int(round(value))


def _phase_summary(phase_name: str) -> str:
    p = phase_name.lower()
    if p == "fixation":
        return "+"
    if p == "cue":
        return "Cue symbol"
    if p == "memory set":
        return "Memory items (example)"
    if p == "delay":
        return "+"
    if p == "target":
        return "Target stimulus"
    if p == "probe":
        return "Probe stimulus"
    if p == "response":
        return "Response window"
    if p == "feedback":
        return "Outcome feedback"
    if p == "inter-trial interval":
        return "+"
    return "Stimulus example"


def _build_source_excerpt(task_name: str, text: str, conditions: list[str], phases: list[dict]) -> str:
    lines = [
        f"# Source Excerpt ({task_name})",
        "",
        "## Parsed Conditions",
        "- " + ", ".join(conditions),
        "",
        "## Parsed Phases",
    ]
    if phases:
        for phase in phases:
            lines.append(
                f"- {phase['phase_name']}: duration={phase.get('duration_ms')}, response={phase.get('response_window_ms')}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Normalized Source Text (excerpt)", "", text[:8000] if text else "(empty)"])
    return "\n".join(lines).strip() + "\n"


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


def _display_timing_label(duration_ms: dict | None, response_window_ms: dict | None) -> str:
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


def _duration_to_text(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    if "fixed" in value:
        return f"{int(round(float(value['fixed'])))} ms"
    if "range" in value and isinstance(value["range"], list) and len(value["range"]) == 2:
        lo = int(round(float(value["range"][0])))
        hi = int(round(float(value["range"][1])))
        return f"{lo}-{hi} ms"
    return None


def _shorten(text: str, n: int = 46) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


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

