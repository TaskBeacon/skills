# PsyFlow Task Standard Checklist

Use this checklist before running final gates.

## Required Files

- `main.py`
- `src/run_trial.py`
- `config/config.yaml`
- `config/config_qa.yaml`
- `config/config_scripted_sim.yaml`
- `config/config_sampler_sim.yaml`
- `responders/__init__.py`
- `responders/task_sampler.py`
- `README.md`
- `CHANGELOG.md`
- `taskbeacon.yaml`
- `.gitignore`
- `references/references.yaml`
- `references/references.md`
- `references/parameter_mapping.md`
- `references/stimulus_mapping.md`
- `references/task_logic_audit.md`

## Runtime Pattern

- `main.py` supports modes: `human`, `qa`, `sim`
- `main.py` uses `parse_task_run_options(...)`
- `run_trial.py` uses `set_trial_context(...)`
- trigger schema is structured (`map/driver/policy/timing`)
- Prefer a simple, auditable mode-aware runtime flow in `main.py` (avoid unnecessary abstraction layers).
- Participant-facing labels/text/options are config-driven (`config/*.yaml` stimuli), not hardcoded in `src/run_trial.py`.
- `src/run_trial.py` should not directly instantiate participant-facing text stimuli with literal text; use `stim_bank.get(...)` / `stim_bank.get_and_format(...)`.
- If custom condition generation is used, `references/task_logic_audit.md` documents why built-in block condition generation is insufficient.
- Default condition path uses built-in `BlockUnit.generate_conditions(...)` for label-level scheduling, and `src/run_trial.py` realizes condition-specific stimuli/parameters at runtime.
- Duration ranges/jitter should be passed directly to `StimUnit.show(...)` / `StimUnit.capture_response(...)`; avoid duplicating task-local `_sample_duration` helpers unless explicitly justified by protocol/audit requirements.
- Runtime sampling that depends on condition should be reproducible from stable seeds (for example block seed + trial index/trial id) when reproducibility is required.
- Custom `generate_*_conditions` is reserved for cross-trial/global sequence constraints, forbidden-repeat rules, or required item-level precompiled plans.
- If weighted condition generation is used, `task.condition_weights` is explicitly defined in config and aligned with `task.conditions`.
- Runtime resolves `task.condition_weights` through `TaskSettings.resolve_condition_weights()` (no task-local duplicate parser).
- If `task.condition_weights` is omitted (or `null`) and no custom generator is used, condition generation is treated as even/default by design.
- If a task-specific controller exists, `references/task_logic_audit.md` documents why it is needed (for example adaptive timing or online control).
- Response keys/mappings are config-driven unless the audit documents a justified runtime exception.
- Legacy/backward-compatibility fallback branches are avoided unless the audit explicitly requires them.

## Config Separation Rules

- `config.yaml`: no `qa`, no `sim`
- `config_qa.yaml`: contains `qa`, no `sim`
- `config_scripted_sim.yaml`: contains `sim`, no `qa`
- `config_sampler_sim.yaml`: contains `sim`, no `qa`

## Stimulus Fidelity Rules

- Placeholder/dummy stimuli are forbidden.
- Placeholder template participant text is forbidden (for example `CUE: ...`, `TARGET: ...`, generic stock prompts with no paradigm content).
- Participant-facing YAML text must not contain encoding corruption (for example `????`, `�`, or mojibake like `Ã¥...`).
- Configs must not reference files containing tokens like `placeholder`, `dummy`, `todo`.
- Asset-backed stimuli (`image`, `movie`, `sound`) must point to existing files.
- `references/stimulus_mapping.md` must be fully resolved (no `UNSET`, `TODO`, or review markers).
- Every base-config condition must appear in `references/stimulus_mapping.md`.
- Internal condition/debug labels must not be shown to participants unless references require them.
- Raw condition tokens (for example `high_risk`, `deck_a`) must not be displayed to participants unless protocol-cited.
- If key mapping is already explicitly provided in instructions, trial screens should not redundantly repeat the same `F/J left/right` mapping unless references require that reminder.
- Frames with multiple text/textbox stimuli must use explicit non-overlapping layout settings (`pos`, `height`, `wrapWidth`) and be checked in QA.
- Multi-option screens must use sensible layout/grouping (explicit anchors, spacing, and legibility checks in QA).
- Prefer config-defined participant-facing text/stimuli for static or condition-indexable content to keep runtime logic easier to audit.

## Metadata Rules

- `taskbeacon.yaml` includes `contracts.psyflow_taps`
- README metadata reflects current version/date
- CHANGELOG includes current implementation summary
- Participant-facing text is language-consistent with task config (for example, `task.language`).
- Participant-facing text uses script-appropriate fonts:
  - Chinese text defaults to `font: SimHei`.
  - Other languages use fonts with full script coverage.
- README includes all reproducibility sections:
  - `## 1. Task Overview`
  - `## 2. Task Flow`
  - `## 3. Configuration Summary`
  - `## 4. Methods (for academic publication)`
- If `<task>/task_flow.png` exists, section `## 2. Task Flow` starts with `![Task Flow](task_flow.png)` as the default visual preview.
- README task flow includes block-level, trial-level, controller logic, and other logic (if applicable).
- README configuration summary includes subject info, window, stimuli, timing, triggers (if present), and adaptive controller (if present).
- README/audit descriptions of condition generation and controller usage match the actual runtime implementation (no stale references to removed abstractions).

## Reference Artifact Contract

- `references/references.yaml` contains required top-level metadata and per-paper fields.
- `references/references.md` includes required headings and a standardized selected-paper table.
- `references/parameter_mapping.md` includes standardized headings and mapping columns.
- `references/stimulus_mapping.md` includes standardized headings/columns and no unresolved markers.
- `references/task_logic_audit.md` includes all required `## 1` to `## 8` sections from the audit template.

## Required Gates

- `check_task_standard.py` pass
- validate pass
- qa pass
- scripted sim pass
- sampler sim pass
