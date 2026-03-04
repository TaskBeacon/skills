---
name: task-plot
description: Build high-fidelity task flow plots as a collection of condition timelines (one timeline per condition) by inferring participant-visible phases from run_trial.py plus config/README or external source text. Use when the user asks for task flow visualization, condition-wise trial diagrams, or auditable timeline plotting.
---

# Task Plot

## Overview

Generate one `task_flow.png` per task folder, where each row is one condition timeline and each timeline contains wide-screen phase snapshots with phase/duration/response-window annotations.
Always write reference artifacts to `references/` for audit.

## Mandatory Output Policy

Write outputs to:

- `<task>/task_flow.png`
- `<task>/references/task_plot_spec.yaml`
- `<task>/references/task_plot_spec.json`
- `<task>/references/task_plot_source_excerpt.md`
- `<task>/references/task_plot_audit.md`

Do not write figure outputs to `assets/`.

## Two Workflows

1. Existing-task workflow:
- Inputs: `<task>/README.md`, `<task>/config/config.yaml`, `<task>/src/run_trial.py`.
- Primary source of flow truth: `run_trial.py`.
- Build one timeline per selected condition.

2. Source workflow:
- Inputs: exactly one of `--source-pdf`, `--source-url`, `--methods-file`, `--methods-text`.
- Infer phases/conditions from source text.
- If `--task-path` is omitted, auto-create `task-plot-drafts/<slug>/`.

## Commands

Existing task:

```powershell
python scripts/make_task_plot.py --mode existing --task-path E:\Taskbeacon\T000035-sternberg-working-memory --max-conditions 4 --screens-per-timeline 6
```

Source mode with explicit target task folder:

```powershell
python scripts/make_task_plot.py --mode source --source-url "https://example.com/methods" --task-path E:\Taskbeacon\T000999-draft --max-conditions 3 --screens-per-timeline 5
```

Source mode with auto draft creation:

```powershell
python scripts/make_task_plot.py --mode source --methods-text "Fixation 500 ms, cue 200 ms, ..."
```

## Plot Construction Rules

- Plot type is fixed: timeline collection.
- One condition = one timeline row.
- Each timeline has up to `screens_per_timeline` screens.
- Each screen is wide-screen shaped (aspect ratio > 1.2; default 16:9).
- Screens overlap by `screen_overlap_ratio` (default `0.05`).
- Timeline baseline is sloped (`screen_slope`) and drawn as parallel lines under screens.
- Timeline start is annotated with condition label.
- Each screen is annotated with:
  - phase name
  - duration
  - response window (if any)
- Duration labels use black text on transparent background and must not overlap any screen.
- Timeline arrow must be parallel to the screen cascade and offset downward to avoid text overlap.
- Display labels must be explicit in spec for reproducibility:
  - `timeline.display_condition_label`
  - `phase.display_phase_label`
  - `phase.display_timing_label`
- Stimulus examples must reflect participant-visible content inferred from `run_trial.py` + `stimuli` config.
- For non-visual or unresolved dynamic stimuli, use textual annotation (e.g. `[audio:*]`, `[dynamic:*]`).

## Auto QA Rework Loop

- After initial render, run up to 3 auto QA passes.
- Each pass includes:
  - pixel-level margin inspection/crop,
  - local QA checks for overlap/margin/label checks (default),
  - optional external vision QA on PNG when configured,
  - bounded layout parameter adjustments + re-render when needed.
- Record each pass in `task_plot_audit.md`.

External vision is optional and provider-agnostic (OpenAI-compatible endpoint shape):

```powershell
python scripts/make_task_plot.py --mode existing --task-path E:\Taskbeacon\T000012-sst --qa-mode api --vision-api-url "https://<provider>/v1/chat/completions" --vision-model "<model_name>" --vision-api-key-env "MY_VISION_API_KEY"
```

Default is local-only:

```powershell
python scripts/make_task_plot.py --mode existing --task-path E:\Taskbeacon\T000012-sst --qa-mode local
```

## Hard Constraints

- Root key must be `task_plot_spec`.
- `spec_version` must be `0.2`.
- Max number of timelines must not exceed `max_conditions`.
- Max number of screens per timeline must not exceed `screens_per_timeline`.
- Output filename must be `.png` and defaults to `task_flow.png`.

## References To Load On Demand

- `references/task_plot_spec_v0_2.md`
- `references/task_plot_audit_template.md`
- `references/inference_rules.md`

## Validation

```powershell
python C:\Users\frued\.codex\skills\.system\skill-creator\scripts\quick_validate.py E:\Taskbeacon\skills\task-plot
python scripts/smoke_test.py
```
