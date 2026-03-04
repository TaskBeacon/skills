# Stimulus Fidelity Policy

This policy defines the minimum bar for stimulus implementation in `task-build`.

## Core Rule

Implemented stimuli must be traceable to selected references. Placeholder or dummy media is not allowed.
Do not expose abstract condition IDs or template labels as participant-facing stimuli unless explicitly required by cited protocol.

## Allowed Implementation Modes

- PsychoPy primitives (`text`, `circle`, `rect`, `polygon`, `shape`, etc.) with parameter values extracted from references.
- Generated assets that replicate the referenced paradigm structure (timing, category logic, perceptual properties) and are documented in evidence files.
- Licensed external media only when required by paradigm and legally usable.

## Required Evidence

- `references/parameter_mapping.md`: parameter-level mapping.
- `references/stimulus_mapping.md`: condition/stimulus-level citation mapping.

## Hard Fail Conditions

- Any config or asset path containing `placeholder`, `dummy`, or `todo`.
- Participant-facing template text used as trial content (for example `CUE: <condition>`, `TARGET: <condition>`, stock instruction-only placeholders).
- Participant-facing text that is only a raw condition token (for example `high_risk`, `deck_a`, `mixed_frame`) without protocol-cited justification.
- Participant-facing YAML text with encoding corruption (for example `????`, `�`, or mojibake sequences such as `Ã¥...`).
- Missing asset files referenced by config.
- Unresolved entries in `references/stimulus_mapping.md`.
- Multi-option displays without explicit, readable layout separation in configuration.
