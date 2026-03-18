#!/usr/bin/env python3
"""Renderer for task-plot v0.2 timeline collection."""

from __future__ import annotations

import math
import re
import textwrap
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.patches import Ellipse
from matplotlib.patches import FancyBboxPatch
from matplotlib.patches import Polygon


def render_task_flow_png(
    spec_root: dict[str, Any],
    out_png: str | Path,
    dpi_override: int | None = None,
) -> None:
    spec = spec_root["task_plot_spec"]
    figure = spec["figure"]
    layout = figure["layout"]
    output = figure["output"]

    timelines = spec["timelines"]
    n_tl = len(timelines)
    n_max_screens = max((len(t.get("phases", [])) for t in timelines), default=1)

    width_cap = float(output.get("width_in", 16.0))
    auto_width_flag = output.get("auto_width", True)
    if isinstance(auto_width_flag, str):
        auto_width_enabled = auto_width_flag.strip().lower() not in {"0", "false", "no", "off"}
    else:
        auto_width_enabled = bool(auto_width_flag)
    auto_width = 4.6 + 0.74 * n_max_screens + 0.22 * max(0, n_tl - 1)
    if auto_width_enabled:
        width_in = max(5.8, min(width_cap, auto_width))
    else:
        width_in = max(5.8, width_cap)
    target_canvas_ar = 2.0 if n_tl <= 1 else 1.85
    height_by_aspect = width_in / target_canvas_ar
    height_by_rows = 2.6 + 1.82 * max(0, n_tl - 1)
    height_in = max(3.6, height_by_aspect, height_by_rows)
    dpi = int(dpi_override or output.get("dpi", 300))

    fig = plt.figure(figsize=(width_in, height_in), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    bg = output.get("background", "white")
    if bg == "white":
        fig.patch.set_facecolor("white")
    else:
        fig.patch.set_alpha(0.0)

    header_bottom = _draw_header(ax, spec)

    left_margin = max(0.12, min(0.45, float(layout.get("left_margin", 0.20))))
    right_margin = max(0.01, min(0.35, float(layout.get("right_margin", 0.03))))
    top_margin = max(0.0, min(0.30, float(layout.get("top_margin", 0.03))))
    bottom_margin = max(0.01, min(0.30, float(layout.get("bottom_margin", 0.05))))
    condition_gap = max(0.004, float(layout.get("condition_label_gap", 0.014)))
    phase_label_pad = max(0.004, float(layout.get("phase_label_pad", 0.010)))
    duration_gap = max(0.003, float(layout.get("duration_label_gap", 0.006)))
    arrow_gap = max(0.003, float(layout.get("timeline_arrow_gap", 0.010)))

    base_overlap = float(layout.get("screen_overlap_ratio", 0.10))
    # Adaptive overlap: fewer screens -> less overlap; many screens -> more overlap.
    overlap = max(0.04, min(0.24, base_overlap + 0.035 * (n_max_screens - 4)))
    if n_max_screens <= 3:
        overlap = max(0.04, overlap - 0.05)
    slope_deg = float(layout.get("screen_slope_deg", 25.0))
    slope_deg = max(0.0, min(35.0, slope_deg))
    slope_tan = math.tan(math.radians(slope_deg))
    screen_ar = max(1.15, float(layout.get("screen_aspect_ratio", 16 / 11)))
    canvas_ar = width_in / max(height_in, 1e-6)

    title_x = 0.02
    condition_col_w = _measure_condition_block_width(ax, timelines)
    condition_col_w = max(0.08, min(0.30, condition_col_w))
    condition_left = title_x
    condition_right = condition_left + condition_col_w
    condition_center_x = 0.5 * (condition_left + condition_right)
    # Start the full timeline block immediately after the measured condition column.
    x_start = condition_right + condition_gap
    x_right = 1.0 - right_margin
    top_y = max(0.60, min(0.93, header_bottom - top_margin))
    bottom_y = bottom_margin
    available_h = max(0.2, top_y - bottom_y)
    row_slot = available_h / max(1, n_tl)

    top_label_pad = phase_label_pad
    phase_label_h = 0.020
    duration_label_h = 0.028
    row_margin = 0.018
    extras = phase_label_h + top_label_pad + duration_gap + duration_label_h + arrow_gap + row_margin

    w_by_width = (x_right - x_start) / max(1.0, (1.0 + (n_max_screens - 1) * (1.0 - overlap)))
    denom = (canvas_ar / screen_ar) + (1.0 - overlap) * slope_tan * canvas_ar * max(0, n_max_screens - 1)
    w_by_height = (row_slot - extras) / max(denom, 1e-6)
    screen_w = max(0.060, min(0.175, w_by_width, w_by_height))
    screen_h = screen_w * canvas_ar / screen_ar
    step_x = screen_w * (1.0 - overlap)
    slope = max(0.004, step_x * slope_tan * canvas_ar)
    # Keep the slope visually strong but bounded so long timelines still leave room for arrow/text.
    slope = min(slope, screen_h * 0.34)

    row_anchor_offset = (0.24 if n_tl == 1 else 0.19) * row_slot
    for row_idx, timeline in enumerate(timelines):
        y_base = top_y - row_anchor_offset - row_idx * row_slot
        _draw_timeline(
            ax=ax,
            timeline=timeline,
            condition_x=condition_center_x,
            x_start=x_start,
            y_base=y_base,
            screen_w=screen_w,
            screen_h=screen_h,
            step_x=step_x,
            slope=slope,
            row_idx=row_idx,
            row_slot=row_slot,
            top_label_pad=top_label_pad,
            phase_label_h=phase_label_h,
            duration_gap=duration_gap,
            duration_label_h=duration_label_h,
            arrow_gap=arrow_gap,
            layout=layout,
        )

    out_path = Path(out_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        out_path,
        format="png",
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.05,
        transparent=(bg == "transparent"),
    )
    plt.close(fig)


def _draw_header(ax: Any, spec: dict[str, Any]) -> float:
    title = spec.get("meta", {}).get("task_name", "Task")
    ax.text(0.02, 0.98, title, ha="left", va="top", fontsize=16, fontweight="bold")
    return 0.89


def _draw_timeline(
    ax: Any,
    timeline: dict[str, Any],
    condition_x: float,
    x_start: float,
    y_base: float,
    screen_w: float,
    screen_h: float,
    step_x: float,
    slope: float,
    row_idx: int,
    row_slot: float,
    top_label_pad: float,
    phase_label_h: float,
    duration_gap: float,
    duration_label_h: float,
    arrow_gap: float,
    layout: dict[str, Any],
) -> None:
    condition = _cap_label(
        str(
            timeline.get(
                "display_condition_label",
                timeline.get("condition", f"condition_{row_idx + 1}"),
            )
        )
    )
    phases = timeline.get("phases", [])

    ax.text(condition_x, y_base, condition, ha="center", va="center", fontsize=10, fontweight="bold")
    condition_note = str(timeline.get("display_condition_note", "")).strip()
    if not condition_note:
        condition_note = _variant_note(timeline)
    if condition_note:
        variant_offset = max(0.016, min(0.030, row_slot * 0.20))
        ax.text(
            condition_x,
            y_base - variant_offset,
            _short(condition_note, 48),
            ha="center",
            va="center",
            fontsize=7,
            color="#6B7280",
        )

    if not phases:
        return

    anchors: list[dict[str, Any]] = []

    for i, phase in enumerate(phases):
        x = x_start + i * step_x
        y = y_base - i * slope - screen_h / 2

        _draw_screen(ax, x=x, y=y, w=screen_w, h=screen_h, phase=phase)

        phase_name = _cap_label(
            str(phase.get("display_phase_label", phase.get("phase_name", "phase")))
        )
        ax.text(
            x + screen_w / 2,
            y + screen_h + top_label_pad,
            phase_name,
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )

        timing_line = _phase_timing_line(phase)
        timing_top = y - duration_gap
        timing_artist = None
        if timing_line:
            timing_artist = ax.text(
                x + screen_w / 2,
                timing_top,
                timing_line,
                ha="center",
                va="top",
                fontsize=7,
                color="#000000",
                zorder=7,
                bbox=dict(boxstyle="round,pad=0.22", facecolor="none", edgecolor="none", alpha=0.0),
            )
        anchors.append(
            {
                "x": x,
                "x_center": x + screen_w / 2,
                "x_left": x + screen_w * 0.02,
                "x_right": x + screen_w * 0.98,
                "screen_bottom": y,
                "timing_top": timing_top,
                "timing_artist": timing_artist,
            }
        )

    if anchors:
        # Keep timing labels below any screen region before placing arrow.
        _resolve_timing_label_screen_overlaps(
            ax=ax,
            anchors=anchors,
            screen_w=screen_w,
            screen_h=screen_h,
            min_clear=max(0.004, float(layout.get("timeline_arrow_text_clearance", 0.010)) * 0.65),
        )

        # Arrow direction is parallel to screen cascade: use bottom-left first/last anchors.
        x_ref0 = anchors[0]["x"]
        y_ref0 = anchors[0]["screen_bottom"]
        x_ref1 = anchors[-1]["x"]
        y_ref1 = anchors[-1]["screen_bottom"]
        ref_dx = max(1e-6, x_ref1 - x_ref0)
        ref_slope = (y_ref1 - y_ref0) / ref_dx

        x0 = x_ref0 + screen_w * 0.02
        x1 = anchors[-1]["x"] + screen_w * 0.96
        dx = max(1e-6, x1 - x0)
        base_y0 = _line_y_at(x0, x_ref0, y_ref0, ref_slope) - arrow_gap
        line_slope = ref_slope

        screen_clear = float(layout.get("timeline_arrow_screen_clearance", 0.007))
        text_clear = float(layout.get("timeline_arrow_text_clearance", 0.010))
        extra_per_screen = float(layout.get("timeline_arrow_extra_per_screen", 0.015))
        min_y = float(layout.get("timeline_arrow_min_y", 0.020))
        max_y = float(layout.get("timeline_arrow_max_y", 0.96))

        constraints: list[tuple[float, float]] = []
        has_timing = any(a.get("timing_artist") is not None for a in anchors)
        renderer = None
        if has_timing:
            ax.figure.canvas.draw()
            renderer = ax.figure.canvas.get_renderer()
        for a in anchors:
            for xs in (a["x"], a["x"] + screen_w):
                allow_screen = a["screen_bottom"] - screen_clear
                constraints.append((xs, allow_screen))

            artist = a.get("timing_artist")
            if artist is not None and renderer is not None:
                box = artist.get_window_extent(renderer=renderer)
                p0 = ax.transData.inverted().transform((box.x0, box.y0))
                p1 = ax.transData.inverted().transform((box.x1, box.y1))
                x_left = min(float(p0[0]), float(p1[0]))
                x_right = max(float(p0[0]), float(p1[0]))
                y_bottom = min(float(p0[1]), float(p1[1]))
                y_est = float(a["timing_top"]) - duration_label_h
                y_text_bottom = min(y_bottom, y_est)
                x_mid = 0.5 * (x_left + x_right)
                for xt in (x_left, x_mid, x_right):
                    allow_text = y_text_bottom - text_clear
                    constraints.append((xt, allow_text))

        required_shift = 0.0
        for xt, y_limit in constraints:
            y_base = _line_y_at(xt, x0, base_y0, line_slope)
            required_shift = max(required_shift, y_base - y_limit)

        required_shift += max(0.0, extra_per_screen * (len(anchors) - 3))
        y0 = base_y0 - required_shift
        y1 = y0 + line_slope * dx

        if max(y0, y1) > max_y:
            shift = max(y0, y1) - max_y
            y0 -= shift
            y1 -= shift
        if min(y0, y1) < min_y:
            trial_shift = min_y - min(y0, y1)
            t0 = y0 + trial_shift
            max_violation = 0.0
            for xt, y_limit in constraints:
                y_val = _line_y_at(xt, x0, t0, line_slope)
                max_violation = max(max_violation, y_val - y_limit)
            if max_violation <= 0.004:
                y0 = t0
                y1 = y0 + line_slope * dx

        # Single sloped timeline arrow under duration labels.
        ax.annotate(
            "",
            xy=(x1, y1),
            xytext=(x0, y0),
            arrowprops=dict(arrowstyle="->", lw=1.2, color="#6B7280"),
            zorder=4,
        )


def _resolve_timing_label_screen_overlaps(
    ax: Any,
    anchors: list[dict[str, Any]],
    screen_w: float,
    screen_h: float,
    min_clear: float,
) -> None:
    if not any(a.get("timing_artist") is not None for a in anchors):
        return

    screen_boxes = [
        (float(a["x"]), float(a["screen_bottom"]), float(a["x"] + screen_w), float(a["screen_bottom"] + screen_h))
        for a in anchors
    ]
    max_passes = 4
    for _ in range(max_passes):
        ax.figure.canvas.draw()
        renderer = ax.figure.canvas.get_renderer()
        moved = False
        for a in anchors:
            artist = a.get("timing_artist")
            if artist is None:
                continue
            x_left, x_right, y_bottom, y_top = _artist_bbox_data(ax, artist, renderer)
            required_shift = 0.0
            for sx0, sy0, sx1, sy1 in screen_boxes:
                if not _rect_overlap(x_left, x_right, y_bottom, y_top, sx0, sx1, sy0, sy1):
                    continue
                shift = y_top - (sy0 - min_clear)
                required_shift = max(required_shift, shift)
            if required_shift > 1e-6:
                pos_x, pos_y = artist.get_position()
                new_y = pos_y - required_shift
                artist.set_position((pos_x, new_y))
                a["timing_top"] = float(new_y)
                moved = True
        if not moved:
            break


def _artist_bbox_data(ax: Any, artist: Any, renderer: Any) -> tuple[float, float, float, float]:
    box = artist.get_window_extent(renderer=renderer)
    p0 = ax.transData.inverted().transform((box.x0, box.y0))
    p1 = ax.transData.inverted().transform((box.x1, box.y1))
    x_left = min(float(p0[0]), float(p1[0]))
    x_right = max(float(p0[0]), float(p1[0]))
    y_bottom = min(float(p0[1]), float(p1[1]))
    y_top = max(float(p0[1]), float(p1[1]))
    return x_left, x_right, y_bottom, y_top


def _rect_overlap(
    a_x0: float,
    a_x1: float,
    a_y0: float,
    a_y1: float,
    b_x0: float,
    b_x1: float,
    b_y0: float,
    b_y1: float,
) -> bool:
    if a_x1 <= b_x0 or a_x0 >= b_x1:
        return False
    if a_y1 <= b_y0 or a_y0 >= b_y1:
        return False
    return True


def _draw_screen(ax: Any, x: float, y: float, w: float, h: float, phase: dict[str, Any]) -> None:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.004,rounding_size=0.004",
        facecolor="#111111",
        edgecolor="#E5E7EB",
        linewidth=1.1,
    )
    ax.add_patch(patch)
    _draw_stimulus_content(ax, x=x, y=y, w=w, h=h, phase=phase)


def _phase_timing_line(phase: dict[str, Any]) -> str:
    explicit = str(phase.get("display_timing_label", "")).strip()
    if explicit:
        return explicit
    d = _duration_to_text(phase.get("duration_ms"))
    r = _duration_to_text(phase.get("response_window_ms"))
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


def _draw_legend(ax: Any, spec: dict[str, Any]) -> None:
    legend_items = spec.get("legend") or []
    if not legend_items:
        return

    x0 = 0.72
    y0 = 0.02
    ax.text(x0, y0 + 0.10, "Legend", ha="left", va="bottom", fontsize=8, fontweight="bold")
    y = y0 + 0.085
    for item in legend_items[:6]:
        key = str(item.get("key", ""))
        meaning = str(item.get("meaning", ""))
        ax.text(x0, y, f"{key}: {meaning}", ha="left", va="top", fontsize=7, color="#374151")
        y -= 0.016


def _draw_stimulus_content(ax: Any, x: float, y: float, w: float, h: float, phase: dict[str, Any]) -> None:
    stim = phase.get("stimulus_example") or {}
    render_items = stim.get("render_items")
    if not isinstance(render_items, list) or not render_items:
        summary = str(stim.get("summary", ""))
        _draw_text_lines(ax, x, y, w, h, [_short(_cap_label(summary), 60)], color="#FFFFFF", size=7)
        return

    text_lines: list[str] = []
    placed_text: list[dict[str, Any]] = []
    shape_items: list[dict[str, Any]] = []
    image_item = None
    for item in render_items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).lower()
        if kind == "image_ref" and image_item is None:
            image_item = item
            continue
        if kind == "shape":
            shape_items.append(item)
            continue
        if kind == "text" and _has_pos(item.get("pos")):
            placed_text.append(item)
            continue
        label = item.get("text") or item.get("label") or ""
        if label:
            text_lines.extend(_expand_text_fragments(_cap_label(str(label))))

    if image_item is not None:
        _draw_image_ref(ax, x, y, w, h, image_item)

    for shape_item in shape_items[:8]:
        _draw_shape_icon(ax, x, y, w, h, shape_item)

    for item in placed_text[:8]:
        _draw_positioned_text(ax, x, y, w, h, item, dense=(len(placed_text) > 1))

    if text_lines:
        _draw_text_lines(ax, x, y, w, h, text_lines[:4], color="#FFFFFF", size=7)


def _draw_image_ref(ax: Any, x: float, y: float, w: float, h: float, item: dict[str, Any]) -> None:
    path = str(item.get("path", "")).strip()
    if not path:
        label = str(item.get("label", "Image")).strip() or "Image"
        _draw_text_lines(ax, x, y, w, h, [_short(_cap_label(label), 24)], color="#FFFFFF", size=7)
        return
    try:
        arr = plt.imread(path)
        pad_x = w * 0.05
        pad_y = h * 0.07
        ax.imshow(
            arr,
            extent=(x + pad_x, x + w - pad_x, y + pad_y, y + h - pad_y),
            zorder=2.5,
            aspect="auto",
        )
    except Exception:  # noqa: BLE001
        label = str(item.get("label", Path(path).stem)).strip() or Path(path).stem
        _draw_text_lines(ax, x, y, w, h, [_short(_cap_label(label), 24)], color="#FFFFFF", size=7)


def _draw_shape_icon(ax: Any, x: float, y: float, w: float, h: float, item: dict[str, Any]) -> None:
    shape = str(item.get("shape", "generic")).lower()
    color = _resolve_color(item.get("color"), default="#FFFFFF")
    line_color = _resolve_color(item.get("line_color"), default=color)
    try:
        line_width = float(item.get("line_width", 1.0))
    except Exception:  # noqa: BLE001
        line_width = 1.0
    line_width = max(0.6, min(3.2, line_width))
    try:
        alpha = float(item.get("alpha", 1.0))
    except Exception:  # noqa: BLE001
        alpha = 1.0
    alpha = max(0.2, min(1.0, alpha))
    cx, cy = _map_pos_to_screen(item.get("pos"), x, y, w, h, default_x_frac=0.5, default_y_frac=0.56)
    base = min(w, h)
    size_scale = _size_scale(item.get("size"), default=0.44)
    sx = base * size_scale
    sy = sx * 0.78

    if shape in {"circle", "ring", "dot"}:
        if shape == "dot":
            radius = sx * 0.20
            face_color = color
            edge_color = color
        else:
            radius = sx * 0.33
            face_color = "none" if shape == "ring" else color
            edge_color = line_color
        # Axes data coords are not square in pixel space; compensate so circles stay visually round.
        y_radius = _radius_y_for_visual_circle(ax=ax, radius_x=radius)
        if abs(y_radius - radius) <= 1e-6:
            patch = Circle(
                (cx, cy),
                radius=radius,
                facecolor=face_color,
                edgecolor=edge_color,
                linewidth=line_width,
                alpha=alpha,
            )
        else:
            patch = Ellipse(
                (cx, cy),
                width=2.0 * radius,
                height=2.0 * y_radius,
                facecolor=face_color,
                edgecolor=edge_color,
                linewidth=line_width,
                alpha=alpha,
            )
        ax.add_patch(patch)
        return

    if shape == "arrow_left":
        points = [
            (cx + sx * 0.55, cy + sy * 0.25),
            (cx + sx * 0.05, cy + sy * 0.25),
            (cx + sx * 0.05, cy + sy * 0.45),
            (cx - sx * 0.65, cy),
            (cx + sx * 0.05, cy - sy * 0.45),
            (cx + sx * 0.05, cy - sy * 0.25),
            (cx + sx * 0.55, cy - sy * 0.25),
        ]
    elif shape == "arrow_right":
        points = [
            (cx - sx * 0.55, cy + sy * 0.25),
            (cx - sx * 0.05, cy + sy * 0.25),
            (cx - sx * 0.05, cy + sy * 0.45),
            (cx + sx * 0.65, cy),
            (cx - sx * 0.05, cy - sy * 0.45),
            (cx - sx * 0.05, cy - sy * 0.25),
            (cx - sx * 0.55, cy - sy * 0.25),
        ]
    elif shape == "stop":
        points = [
            (cx - sx * 0.45, cy + sy * 0.45),
            (cx + sx * 0.45, cy + sy * 0.45),
            (cx + sx * 0.45, cy - sy * 0.45),
            (cx - sx * 0.45, cy - sy * 0.45),
        ]
    else:
        points = [
            (cx - sx * 0.45, cy + sy * 0.35),
            (cx + sx * 0.45, cy + sy * 0.35),
            (cx + sx * 0.45, cy - sy * 0.35),
            (cx - sx * 0.45, cy - sy * 0.35),
        ]
    patch = Polygon(
        points,
        closed=True,
        facecolor=color,
        edgecolor=line_color,
        linewidth=line_width,
        alpha=alpha,
    )
    ax.add_patch(patch)

    if shape == "stop":
        ax.text(cx, cy, "STOP", ha="center", va="center", fontsize=6, color="#111111", fontweight="bold")


def _measure_condition_block_width(ax: Any, timelines: list[dict[str, Any]]) -> float:
    texts: list[Any] = []
    for idx, timeline in enumerate(timelines):
        cond = _cap_label(
            str(
                timeline.get(
                    "display_condition_label",
                    timeline.get("condition", f"condition_{idx + 1}"),
                )
            )
        )
        texts.append(
            ax.text(0.0, 0.0, cond, ha="left", va="bottom", fontsize=10, fontweight="bold", alpha=0.0)
        )
        note = str(timeline.get("display_condition_note", "")).strip() or _variant_note(timeline)
        if note:
            texts.append(
                ax.text(0.0, 0.0, _short(note, 48), ha="left", va="bottom", fontsize=7, alpha=0.0)
            )

    if not texts:
        return 0.12
    ax.figure.canvas.draw()
    renderer = ax.figure.canvas.get_renderer()
    axes_box = ax.get_window_extent(renderer=renderer)
    axes_w = max(1.0, float(axes_box.width))
    max_w = 0.0
    for t in texts:
        box = t.get_window_extent(renderer=renderer)
        max_w = max(max_w, float(box.width) / axes_w)
        t.remove()
    return max_w


def _variant_note(timeline: dict[str, Any]) -> str:
    variants = timeline.get("condition_variants")
    if not isinstance(variants, list) or not variants:
        return ""
    label = "Also: " + ", ".join(_cap_label(str(v)) for v in variants[:3])
    if len(variants) > 3:
        label += f" (+{len(variants) - 3})"
    return label


def _draw_text_lines(ax: Any, x: float, y: float, w: float, h: float, lines: list[str], color: str, size: int) -> None:
    if not lines:
        return
    wrapped = _wrap_lines(lines, width=max(14, int(18 + w * 60)), max_lines=5)
    text_blob = "\n".join(wrapped)
    ax.text(
        x + w / 2,
        y + h * 0.56,
        text_blob,
        ha="center",
        va="center",
        fontsize=size,
        color=color,
        linespacing=1.08,
        **_font_kwargs_for_text(text_blob),
    )


def _resolve_color(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _draw_positioned_text(
    ax: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    item: dict[str, Any],
    dense: bool,
) -> None:
    text = str(item.get("text", "")).strip()
    if not text:
        return
    cx, cy = _map_pos_to_screen(item.get("pos"), x, y, w, h, default_x_frac=0.5, default_y_frac=0.58)
    color = _resolve_color(item.get("color"), "#FFFFFF")
    size = _text_size(item.get("height"), default=(6 if dense else 7))
    wrapped = _wrap_lines(
        _expand_text_fragments(_cap_label(text)),
        width=max(12, int(16 + w * 52)),
        max_lines=(2 if dense else 3),
    )
    text_blob = "\n".join(wrapped)
    ax.text(
        cx,
        cy,
        text_blob,
        ha="center",
        va="center",
        fontsize=size,
        color=color,
        linespacing=1.08,
        **_font_kwargs_for_text(text_blob),
    )


def _has_pos(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _map_pos_to_screen(
    pos: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    default_x_frac: float,
    default_y_frac: float,
) -> tuple[float, float]:
    if _has_pos(pos):
        px = _to_float(pos[0])
        py = _to_float(pos[1])
        if px is not None and py is not None:
            if max(abs(px), abs(py)) > 3:
                px *= 0.004
                py *= 0.004
            px = max(-1.0, min(1.0, px))
            py = max(-1.0, min(1.0, py))
            x_frac = max(0.12, min(0.88, 0.5 + 0.40 * px))
            y_frac = max(0.18, min(0.86, 0.55 + 0.45 * py))
            return (x + w * x_frac, y + h * y_frac)
    return (x + w * default_x_frac, y + h * default_y_frac)


def _size_scale(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        v = float(value)
        if 0 < v <= 2.0:
            return max(0.24, min(0.62, v * 0.42 if v <= 1 else v * 0.24))
    if isinstance(value, (list, tuple)) and value:
        vals = [abs(v) for v in (_to_float(x) for x in value[:2]) if v is not None]
        if vals:
            v = max(vals)
            if 0 < v <= 2.0:
                return max(0.24, min(0.62, v * 0.42 if v <= 1 else v * 0.24))
    return default


def _text_size(value: Any, default: int) -> int:
    if isinstance(value, (int, float)):
        v = float(value)
        if 0 < v <= 1.0:
            return int(max(6, min(10, round(5 + v * 9))))
        if 1.0 < v <= 4.0:
            return int(max(6, min(10, round(v + 4))))
    return default


def _expand_text_fragments(text: str) -> list[str]:
    raw = " ".join(str(text).split())
    if not raw:
        return []
    chunks = []
    for part in raw.split("|"):
        token = part.strip(" ;")
        if not token:
            continue
        token = re.sub(r"\s+(?=[A-Za-z]\s*=)", "\n", token)
        chunks.extend([s.strip() for s in token.split("\n") if s.strip()])
    return chunks or [raw]


def _wrap_lines(lines: list[str], width: int, max_lines: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        segment = " ".join(str(line).split())
        if not segment:
            continue
        pieces = textwrap.wrap(segment, width=width, break_long_words=False, break_on_hyphens=False)
        wrapped.extend(pieces if pieces else [segment])
    if not wrapped:
        return []
    if len(wrapped) > max_lines:
        trimmed = wrapped[: max_lines]
        trimmed[-1] = _short(trimmed[-1], max(8, width - 2))
        return trimmed
    return wrapped


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


def _compact_phase_label(text: str) -> str:
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
    return _short(_cap_label(compact or raw), 20)


def _line_y_at(x: float, x0: float, y0: float, slope: float) -> float:
    return y0 + (x - x0) * slope


def _timing_half_width(label: str, screen_w: float) -> float:
    # Lightweight width estimate in axes units for 7pt timing labels.
    chars = len(" ".join(str(label).split()))
    est = 0.0038 * chars + 0.03
    return max(0.055, min(screen_w * 0.48, est))


def _short(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _font_kwargs_for_text(text: str) -> dict[str, Any]:
    if _contains_cjk(text):
        return {"fontfamily": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]}
    return {}


def _contains_cjk(text: str) -> bool:
    for ch in str(text or ""):
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or 0x3000 <= code <= 0x303F:
            return True
    return False


def _radius_y_for_visual_circle(ax: Any, radius_x: float) -> float:
    try:
        box = ax.get_window_extent()
        w_px = float(box.width)
        h_px = float(box.height)
        if w_px <= 0 or h_px <= 0:
            return radius_x
        return radius_x * (w_px / h_px)
    except Exception:  # noqa: BLE001
        return radius_x
