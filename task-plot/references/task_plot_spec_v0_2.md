# task_plot_spec v0.2

Root key:

```yaml
task_plot_spec:
  spec_version: "0.2"
  ...
```

Legacy root key `TaskIllustrationSpec` is rejected.

## Purpose

Represent one task flow figure as a collection of condition timelines.

- One timeline row per condition.
- One screen snapshot per phase in the condition's typical trial progression.
- Figure text labels are reproducible from spec (no hidden renderer-only label logic).

## Required Structure

```yaml
task_plot_spec:
  spec_version: "0.2"
  meta:
    task_name: string
    mode: existing|source
    task_id: string (optional)

  figure:
    output:
      filename: "task_flow.png"
      dpi: int >= 72
      width_in: float > 4
      auto_width: bool (optional, default true)
      background: white|transparent

    layout:
      max_conditions: int > 0
      screens_per_timeline: int > 0
      screen_overlap_ratio: float in [0, 0.4)
      screen_slope: float in [0, 0.1]
      screen_slope_deg: float in [0, 35]
      timeline_gap: float > 0
      screen_aspect_ratio: float > 1.2
      left_margin: float in [0, 0.6)
      right_margin: float in [0, 0.6)
      top_margin: float in [0, 0.5)
      bottom_margin: float in [0, 0.5)
      condition_label_gap: float >= 0
      phase_label_pad: float >= 0
      duration_label_gap: float >= 0
      timeline_arrow_gap: float >= 0
      timeline_arrow_screen_clearance: float >= 0
      timeline_arrow_text_clearance: float >= 0
      timeline_arrow_extra_per_screen: float >= 0
      timeline_arrow_min_y: float in [0, 1]
      timeline_arrow_max_y: float in [0, 1]

  timelines:
    - condition: string
      display_condition_label: string   # required (render label)
      display_condition_note: string (optional)
      phases:
        - phase_name: string
          display_phase_label: string    # required (render label)
          duration_ms:
            fixed: int|float
            # OR
            range: [int|float, int|float]
          response_window_ms:
            fixed: int|float
            # OR
            range: [int|float, int|float]
            # optional
          display_timing_label: string   # optional precomputed render label
          stim_ids: [string, ...]
          stimulus_example:
            summary: string
            modality: visual|audio|mixed|other
            draw_hint: string
          notes: string (optional)

  legend:
    - key: string
      meaning: string
```

## Rules

- Timeline collection only; no storyboard/matrix mode.
- `len(timelines) <= figure.layout.max_conditions`.
- `len(timeline.phases) <= figure.layout.screens_per_timeline`.
- Output figure path in task root by default: `task_flow.png`.
- Persist spec as both `task_plot_spec.yaml` and `task_plot_spec.json`.
- Every phase should include duration and response window when inferable.
- Duration labels are rendered as black text on transparent background and must clear all screen rectangles.
- Timeline arrow is rendered parallel to the screen cascade (using first/last screen anchor geometry) and offset downward.
- When `figure.output.auto_width=false`, renderer uses `width_in` directly instead of auto-compacting by phase count.
- Screen content should show the exact sample participant-visible stimulus whenever config/runtime evidence is sufficient.
- Abstract internal labels or condition/debug tokens must not be used as the screen content when the actual stimulus can be resolved.
- If a participant-visible phase is inferred from `show()` because `set_trial_context(...)` is missing, the plot audit must emit an explicit warning.
- For non-visual/dynamic stimuli, use annotation text examples only when a visual sample is genuinely unavailable.
