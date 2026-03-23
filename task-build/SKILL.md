---
name: task-build
description: Build or refactor cognitive experiment tasks into PsyFlow/TAPS standard from literature evidence, with strict reference-aligned stimulus implementation (no placeholders).
---

# Task Build

Build a task from literature to validated, publishable PsyFlow/TAPS structure.

## Required Inputs

Collect these fields before execution:

- `task_id` (example: `T000016`)
- `task_slug` (example: `cpt`)
- `task_title`
- `task_path`
- `acquisition` (`behavior|eeg|fmri|meg|...`)

Use defaults unless explicitly overridden:

- `variant=baseline`
- `language=Chinese`
- `voice_name=zh-CN-YunyangNeural`
- `citation_threshold=100`
- `max_retries=3`

Language/font default policy:

- If `language=Chinese`, set participant-facing text stimuli to `font: SimHei`.
- For non-Chinese languages, choose a readable font with strong glyph coverage for that language/script.

Input-mode routing:

- `Mode A: literature-first` (default)
  - Use when the user asks to build a task but does not provide a concrete paper/method source.
  - Run full literature discovery and selection policy first.
- `Mode B: provided-source-first`
  - Use when the user provides a paper URL, PDF, or explicit methods description and asks to build from that source.
  - Treat the provided source as primary protocol evidence.
  - Fill missing protocol details with supporting literature and mark unresolved values as `inferred`.

## Workflow

### Phase -1: Environment Warm-Up (Mandatory on a New Machine)

1. Run preflight checks:
   - `python scripts/preflight_env.py`
2. If required modules are missing, install them:
   - `python scripts/preflight_env.py --install-missing --psyflow-source <path-to-psyflow-checkout>`
3. Continue only after preflight reports `PASS`.

### Phase 0: Paradigm Logic Audit (Mandatory Before Coding)

1. Create `references/task_logic_audit.md` before editing task code.
   - Start from `assets/templates/task_logic_audit_template.md`.
   - **CRITICAL:** Do NOT generate this file by reverse-engineering existing code or using automated scripts that read `src/run_trial.py`.
   - **CRITICAL:** Extract the state machine and timing directly from the text, figures, and tables of the cited papers.
   - **CRITICAL:** If you initialize files from a MID template, treat it as scaffolding only (CLI/mode wiring, file layout). Discard MID trial logic and rebuild phases from literature.
2. Specify the full paradigm workflow:
   - research question and manipulated factors
   - block and trial state machine (sequence of states)
   - response rules and timeout rules
   - scoring/reward update rules
   - trigger plan by phase
3. For every condition, describe concrete participant-facing sensory content (what is seen/heard), not abstract IDs.
4. For every screen with multiple concurrent options/stimuli, define an explicit layout plan (`pos`, spacing, alignment, visual hierarchy) before implementation.
5. **Stop implementation** if any trial phase is still represented only by template text, abstract condition labels, or if the logic is being "imported" from an unrelated task (e.g., using MID's Cue-Anticipation-Target structure for a choice-based task).

### Phase 1A (Mode A): Discover and Filter Literature

1. Run `scripts/select_papers.py` with task keywords and acquisition modality.
2. Enforce all filter rules:
   - citation count `>=100`
   - open-access only (skip paywalled)
   - at least one paper from `references/high_impact_psyneuro_journals.yaml`
   - at least three selected papers
3. Stop with an explicit blocker if constraints are not satisfied.

### Phase 1B (Mode B): Register Provided Source and Add Supporting Literature

1. Register the provided protocol source:
   - `python scripts/register_provided_source.py --task-path <task_path> --paper-url <url>`
   - or `--paper-pdf <path>`
   - or `--methods-file <path>` / `--methods-text "..."`
2. If protocol details are incomplete, collect supporting literature via `scripts/select_papers.py`.
3. Compose the selected bundle with the provided source as primary:
   - `python scripts/compose_selected_from_provided.py --task-path <task_path>`
   - optional: `--supplement-json <selected_papers_from_lit.json>`
4. Continue to Phase 2 using the composed `references/selected_papers.json`.

### Phase 2: Build Evidence Artifacts

1. Run `scripts/build_reference_bundle.py`.
2. Create in task repo:
   - `references/references.yaml`
   - `references/references.md`
   - `references/parameter_mapping.md`
   - `references/stimulus_mapping.md`
   - `references/task_logic_audit.md`
   - Seed mapping files from templates when needed:
     - `assets/templates/parameter_mapping_template.md`
     - `assets/templates/stimulus_mapping_template.md`
3. Mark unresolved protocol decisions as `inferred` and explain rationale.
4. Do not continue to implementation unless `stimulus_mapping.md` is fully resolved.

Reference artifact schema (mandatory):

- `references/references.yaml`
  - Must contain top-level keys: `task_id`, `generated_at`, `selection_policy`, `citation_threshold`, `papers`.
  - Each paper entry must include: `id`, `title`, `year`, `journal`, `doi_or_url`, `citation_count`, `open_access`, `is_high_impact`, `used_for`.
- `references/references.md`
  - Must include `# References` and `## Selected Papers`.
  - Must include a paper table with columns: `ID`, `Year`, `Citations`, `Journal`, `High Impact`, `Open Access`, `Title`.
- `references/parameter_mapping.md`
  - Must include `# Parameter Mapping` and `## Mapping Table`.
  - Must include a mapping table with columns: `Parameter ID`, `Config Path`, `Implemented Value`, `Source Paper ID`, `Evidence (quote/figure/table)`, `Decision Type`, `Notes`.
- `references/stimulus_mapping.md`
  - Must include `# Stimulus Mapping` and `## Mapping Table`.
  - Must include a mapping table with columns: `Condition`, `Stage/Phase`, `Stimulus IDs`, `Participant-Facing Content`, `Source Paper ID`, `Evidence (quote/figure/table)`, `Implementation Mode`, `Asset References`, `Notes`.
  - Must not contain unresolved markers (`UNSET`, `TODO`, `required_review`).
- `references/task_logic_audit.md`
  - Must follow the section structure defined in `assets/templates/task_logic_audit_template.md` (sections `## 1` through `## 8`).

### Phase 3: Build or Refactor Task to PsyFlow/TAPS Standard

Ensure mandatory structure exists and is aligned:

- `main.py` mode-aware for `human|qa|sim`
- `src/run_trial.py` with `set_trial_context(...)`
- `config/config.yaml`
- `config/config_qa.yaml`
- `config/config_scripted_sim.yaml`
- `config/config_sampler_sim.yaml`
- `responders/__init__.py`
- `responders/task_sampler.py`
- `assets/README.md`
- `README.md`
- `CHANGELOG.md`
- `taskbeacon.yaml` with `contracts.psyflow_taps`
- `.gitignore` aligned to outputs

Template bootstrap policy:

- You may initialize a new task from an existing template (including MID) for non-paradigm-specific scaffolding only.
- Before writing `src/run_trial.py` and `config/config.yaml`, reset to zero-base literature logic: re-derive states, transitions, and stimuli from citations.
- Any borrowed phase sequence from an unrelated paradigm is invalid, even if all gates pass.

PsyFlow-first implementation decision rules:

- Start from the simplest PsyFlow-native implementation path, then add task-specific abstractions only when the native path cannot express the paradigm.
- Condition generation:
  - Default path: use built-in `BlockUnit.generate_conditions(...)` to produce label-level trial conditions.
  - `src/run_trial.py` should realize concrete stimuli/parameters from each `condition` label (for example set size, layout, timing jitter, stimulus composition).
  - For duration ranges/jitter, pass ranges directly to `StimUnit.show(...)` / `StimUnit.capture_response(...)`; do not duplicate task-local `_sample_duration` logic unless explicitly required by the protocol or audit design.
  - If deterministic runtime sampling is needed, derive randomness from a stable seed basis (for example block seed + trial index/trial id) and keep sampling auditable.
  - Prefer built-in `BlockUnit.generate_conditions(...)` using config-defined condition labels/weights/order.
  - If weighted generation is required, define `task.condition_weights` explicitly in `config/config.yaml` (and mirrored mode profiles as needed).
  - `task.condition_weights` can be a mapping by condition label or a list aligned to `task.conditions`.
  - Runtime code should resolve weight policy through `TaskSettings.resolve_condition_weights()` instead of custom helper functions.
  - If `task.condition_weights` is omitted (or `null`), assume even/default generation unless a custom generator is documented.
  - Use a custom generation function only when label-level generation cannot represent required semantics (for example cross-trial constraints, forbidden repeats, precompiled special sequences, or mandatory item-level preplans for audit/replay).
  - If custom generation is used, document the reason and data shape in `references/task_logic_audit.md` before coding.
- `utils.py` scope:
  - `utils.py` is optional and should only hold task-specific helpers that fill real framework gaps (for example adaptive RT/staircase control, complex sequence generation, asset pools, stimulus bookkeeping).
  - Do not introduce a unified controller/manager abstraction by default.
- Config-first runtime design:
  - Prefer config-defined participant-facing stimuli and task parameters when values are static or condition-indexable.
  - Prefer config-defined response keys/mappings unless the paradigm requires runtime adaptation.
  - Participant-facing labels/text/options must be defined in `config/*.yaml` stimuli (or config templates consumed via `stim_bank.get_and_format(...)`), not hardcoded inside `src/run_trial.py`.
  - `src/run_trial.py` should orchestrate trial flow and state updates; participant wording should remain in config for localization portability.
- `main.py` style:
  - Prefer one simple, auditable mode-aware flow (`human|qa|sim`) with consistent setup order.
  - Avoid over-fragmenting `main.py` into many helpers unless complexity clearly justifies it.
- `src/run_trial.py` auditability:
  - Avoid legacy/backward-compatibility fallback branches unless migration support is explicitly required.
  - Keep phase labels and internal unit labels aligned to the literature audit state names.
  - If values are generated at runtime, make generation deterministic when possible and log enough information to audit reproduction.

Use `references/psyflow_task_standard_checklist.md` as the source of truth.

### Phase 4: Implement Reference-Exact Stimuli

Stimulus policy is strict:

- Implement the exact stimulus logic/material from selected references.
- Prefer PsychoPy built-in drawing primitives (`text`, `circle`, `rect`, `polygon`, `shape`) when possible.
- If external media is required, generate/build non-placeholder assets aligned to references.
- Always render concrete task stimuli (draw/generate actual task materials). Do not leave participant-facing stages as generic template text.
- Every implemented stimulus must map to citation evidence in `references/stimulus_mapping.md`.
- Do not show internal condition labels or debugging cues to participants unless explicitly required by the reference protocol.
- Do not display raw condition tokens as participant stimuli (for example `high_risk`, `deck_a`, `mixed_frame`) unless a cited protocol explicitly requires label exposure.
- Placeholder/template participant text is forbidden (for example `CUE: ...`, `TARGET: ...`, `Respond as quickly and accurately as possible`, `Press SPACE to continue` as sole trial content).
- Hardcoding participant-facing labels/instructions/options in `src/run_trial.py` is forbidden unless references explicitly require runtime-generated wording that cannot be represented through config templates.
- Participant-facing text in YAML must be encoding-clean (no mojibake and no repeated `?` corruption such as `????`).
- If key mapping is already clearly taught in instructions, do not redundantly repeat `F/J left/right` mapping text on every trial screen unless the reference protocol explicitly requires repeated reminders.
- When multiple `text`/`textbox` stimuli are displayed in the same frame, layout must be explicitly separated (`pos`, `height`, `wrapWidth`) to prevent overlap across supported window sizes.
- When multiple options are displayed together, use a sensible spatial arrangement (left/right grid, radial, card row, etc.) with explicit anchors and perceptual grouping cues.
- Verify multi-stimulus layout with QA output and adjust spacing until labels/options are readable without overlap.

### Phase 5: Execute Gates with Auto-Fix Loop

Run `scripts/run_gates.py`.

Required gates:

- `python scripts/check_task_standard.py --task-path <task_path>`
- `python -m psyflow.validate <task_path>` (or `psyflow-validate` if available)
- `psyflow-qa <task_path> --config config/config_qa.yaml --no-maturity-update`
- `python main.py sim --config config/config_scripted_sim.yaml`
- `python main.py sim --config config/config_sampler_sim.yaml`

Rules:

- Retry up to `max_retries=3` after failures.
- Apply deterministic basic fixes only.
- Emit a gate report under `outputs/qa/gate_report.json`.

### Phase 6: Finalize and Publish

1. Update `README.md` metadata and runtime instructions.
2. Update `CHANGELOG.md` with concrete changes.
3. Update `taskbeacon.yaml` release tag and contracts version.
4. Run `scripts/publish_task.py` to commit and push.

README contract requirements:

- Follow `psyflow/psyflow/templates/task2doc_prompt.txt` structure exactly.
- Include all required sections:
  - `## 1. Task Overview`
  - `## 2. Task Flow`
  - `## 3. Configuration Summary`
  - `## 4. Methods (for academic publication)`
- In `## 2`, include block-level flow, trial-level flow, controller logic, and other logic (if present).
- If `<task>/task_flow.png` exists, `README.md` must place `![Task Flow](task_flow.png)` at the beginning of section `## 2. Task Flow` as the default flow preview.
- In `## 3`, include subject info, window settings, stimuli, timing, triggers (if present), and adaptive controller (if present).
- Ensure table formatting is consistent and auditable (header row + separator + blank line after each table).

## Guardrails

- **Zero-Base Implementation:** Do not implement paradigms by copying unrelated task templates (for example MID) without paradigm-specific logic refit. If a task is not an incentive-delay paradigm, it MUST NOT use the `cue -> anticipation -> target -> feedback` state machine.
- **Scaffold-Only Reuse:** MID can be used to bootstrap project structure, but not as task logic. Keep only generic runtime plumbing; replace all paradigm-specific state machine, response logic, and stimuli from literature.
- **Audit-to-Code Traceability:** Every phase in `src/run_trial.py` must correspond to a state defined in `references/task_logic_audit.md`.
- **Anti-Poisoning:** Explicitly verify that the task logic matches the literature. For example, Cyberball must involve ball-tossing interactions, and choice-based games must involve explicit choice stages, not just "hit/miss" targets.
- **PsyFlow-First Simplicity:** Prefer the simplest built-in PsyFlow path first (standard block condition generation, config-defined keys/stimuli, direct trial logic). Escalate abstraction only when the paradigm requires it.
- **Localization Portability:** Keep participant-facing text in config stimuli/templates. Do not require code edits in `run_trial.py` for language localization.
- Do not introduce protocol decisions without references or `inferred` labeling.
- Do not implement paradigms by copying unrelated task templates (for example MID) without paradigm-specific logic refit.
- Do not treat gate pass as paradigm validity; logic and stimulus fidelity must be manually audited against references.
- Ensure all `config/*.yaml` files are written and saved as UTF-8 with correct multilingual rendering (Chinese/Japanese/English/French etc.) and no corrupted glyph sequences.
- Do not mix mode sections across configs:
  - `config.yaml`: no `qa`, no `sim`
  - `config_qa.yaml`: has `qa`, no `sim`
  - `config_scripted_sim.yaml`: has `sim`, no `qa`
  - `config_sampler_sim.yaml`: has `sim`, no `qa`
- Placeholder or dummy assets are forbidden.
- Do not publish if any gate fails.

## Generic Development Experience

Apply these cross-task lessons by default:

- Separate **framework compliance** from **paradigm validity**: passing gates is necessary but not sufficient.
- Implement one task at a time end-to-end before scaling to batch work.
- Prefer PsychoPy built-ins for core stimuli when possible; reduce external asset dependency.
- Keep participant-facing text language-consistent with the configured task language.
- Use language-appropriate fonts consistently:
  - Chinese tasks default to `SimHei`.
  - Other languages use fonts that fully support their scripts.
- Keep pre-response displays neutral unless required by protocol (avoid leaking condition identity before response).
- Avoid redundant key-reminder text on trial screens when instruction phase already defines key mapping.
- For screens with multiple text elements, define explicit non-overlapping layout anchors and verify visually in QA.
- Resolve stimulus evidence mapping before runtime tuning or polishing.
- Add strict fail-fast checks early (`check_task_standard.py`) to avoid long failing gate loops.
- Keep QA and sim profiles short but mechanism-complete (cover all conditions/stages).
- Avoid over-automation that invents paradigm logic; when unsure, stop and mark inference explicitly.
- Prefer a single clear runtime path over fallback-heavy implementations unless backward compatibility is explicitly required.
- Prefer config parameterization for static participant-facing text and key mappings instead of code-side translation tables when no dynamic behavior is needed.
- Prefer adding a custom condition generator only after confirming built-in block condition generation cannot represent the paradigm cleanly.
- Treat `utils.py` as an optional extension point, not a mandatory controller layer.

## Command Quick Start

```powershell
# 0) Warm up environment (check / optional install)
python scripts/preflight_env.py
python scripts/preflight_env.py --install-missing --psyflow-source e:\Taskbeacon\psyflow

# Mode A (default): literature-first
# 1) Select papers
python scripts/select_papers.py --task-name "monetary incentive delay" --task-path e:\Taskbeacon\T000006-mid --acquisition eeg

# 2) Build reference bundle (includes stimulus_mapping.md)
python scripts/build_reference_bundle.py --task-path e:\Taskbeacon\T000006-mid

# 3) Check standard + stimulus fidelity constraints
python scripts/check_task_standard.py --task-path e:\Taskbeacon\T000006-mid

# 4) Run full gate suite
python scripts/run_gates.py --task-path e:\Taskbeacon\T000006-mid --max-retries 3

# 5) Publish
python scripts/publish_task.py --task-path e:\Taskbeacon\T000006-mid

# Mode B: provided-source-first (URL/PDF/method text)
# B1) Register user-provided source
python scripts/register_provided_source.py --task-path e:\Taskbeacon\T000006-mid --paper-url "https://..."
# or
python scripts/register_provided_source.py --task-path e:\Taskbeacon\T000006-mid --paper-pdf e:\papers\protocol.pdf
# or
python scripts/register_provided_source.py --task-path e:\Taskbeacon\T000006-mid --methods-file e:\papers\methods.md

# B2) Optional: gather supporting literature for missing details
python scripts/select_papers.py --task-name "monetary incentive delay" --task-path e:\Taskbeacon\T000006-mid --acquisition eeg

# B3) Compose selected papers (provided primary + optional supports)
python scripts/compose_selected_from_provided.py --task-path e:\Taskbeacon\T000006-mid

# B4) Build reference artifacts from composed selected papers
python scripts/build_reference_bundle.py --task-path e:\Taskbeacon\T000006-mid --selection-policy provided_source_plus_supporting_literature
```

## References to Load on Demand

- `references/literature_search_playbook.md`
- `references/task_param_inference_rules.md`
- `references/psyflow_task_standard_checklist.md`
- `references/publish_checklist.md`
- `references/high_impact_psyneuro_journals.yaml`
- `references/stimulus_fidelity_policy.md`
- `references/task_development_experience.md`
- `references/reference_artifact_contract.md`
