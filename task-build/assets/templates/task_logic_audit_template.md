# Task Logic Audit Template

Use this file as `references/task_logic_audit.md` before coding.

**WARNING:** DO NOT fill this template by reverse-engineering existing code (`src/run_trial.py`) or using automated scripts. You MUST extract the trial flow, timing, and conditions directly from the text, figures, and tables of the selected literature.
**WARNING:** If this task was initialized from MID (or any other task), treat that source as structure-only scaffolding. Rebuild the paradigm state machine from zero-base literature logic.

## 1. Paradigm Intent

- Task:
- Primary construct:
- Manipulated factors:
- Dependent measures:
- Key citations:

## 2. Block/Trial Workflow

### Block Structure

- Total blocks:
- Trials per block:
- Randomization/counterbalancing:
- Condition weight policy:
  - If weighted generation is used, where is `task.condition_weights` defined in config?
  - Is runtime resolution delegated to `TaskSettings.resolve_condition_weights()`?
  - If omitted/null, confirm even/default generation (or document custom generator behavior).
- Condition generation method:
  - Built-in `BlockUnit.generate_conditions(...)` or custom generator?
  - If custom generator is used, why can simple condition labels not represent the task?
  - What is the generated condition data shape passed into `run_trial.py`?
- Runtime-generated trial values (if any):
  - What is generated in `run_trial.py` instead of precomputed conditions?
  - How is generation made deterministic/reproducible (seed source, trial ID, block seed, etc.)?

### Trial State Machine

List each state in order with entry/exit conditions:

1. State name:
   - Onset trigger:
   - Stimuli shown:
   - Valid keys:
   - Timeout behavior:
   - Next state:

## 3. Condition Semantics

For each condition token in `task.conditions`:

- Condition ID:
- Participant-facing meaning:
- Concrete stimulus realization (visual/audio):
- Outcome rules:

Also document where participant-facing condition text/stimuli are defined:

- Participant-facing text source (config stimuli / code formatting / generated assets):
- Why this source is appropriate for auditability:
- Localization strategy (how language variants are swapped via config without code edits):

## 4. Response and Scoring Rules

- Response mapping:
- Response key source (config field vs code constant):
- If code-defined, why config-driven mapping is not sufficient:
- Missing-response policy:
- Correctness logic:
- Reward/penalty updates:
- Running metrics:

## 5. Stimulus Layout Plan

For every screen with multiple simultaneous options/stimuli:

- Screen name:
- Stimulus IDs shown together:
- Layout anchors (`pos`):
- Size/spacing (`height`, width, wrap):
- Readability/overlap checks:
- Rationale:

## 6. Trigger Plan

Map each phase/state to trigger code and semantics.

## 7. Architecture Decisions (Auditability)

- `main.py` runtime flow style (simple single flow / helper-heavy / why):
- `utils.py` used? (yes/no)
- If yes, exact purpose (adaptive controller / sequence generation / asset pool / other):
- Custom controller used? (yes/no)
- If yes, why PsyFlow-native path is insufficient:
- Legacy/backward-compatibility fallback logic required? (yes/no)
- If yes, scope and removal plan:

## 8. Inference Log

List any inferred decisions not directly specified by references:

- Decision:
- Why inference was required:
- Citation-supported rationale:

## Contract Note

- Participant-facing labels/instructions/options should be config-defined whenever possible.
- `src/run_trial.py` should not hardcode participant-facing text that would require code edits for localization.
