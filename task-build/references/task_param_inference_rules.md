# Task Parameter Inference Rules

Use these rules when literature does not fully specify implementation parameters.

## Priority

1. exact paper parameter
2. parameter from high-impact replication/review
3. bounded inference from standard practice

## Required Annotation

Mark each inferred parameter as:

- confidence: `inferred`
- rationale: short explanation
- source: linked paper ID(s)

## Preferred Mapping Targets

Map paper decisions into:

- `config/config.yaml` task and timing sections
- trigger map/event naming
- run-trial stage order and semantics
- responder behavior constraints
- stimulus construction details (shape/color/size/media/timing)

## Stimulus Rule (Strict)

- Do not use placeholder or dummy stimuli.
- If exact media files are unavailable, reconstruct reference-aligned stimuli with PsychoPy primitives or generated assets.
- Record every stimulus decision in `references/stimulus_mapping.md` with source-paper linkage.

## Inference Guardrails

- Never hide inference as exact.
- Keep inferred values conservative and task-typical.
- Do not alter core paradigm logic to simplify coding.
- If constraints conflict across papers, prefer high-impact primary paper and record conflict.

## Common Inference Cases

- response window not explicitly reported
- ITI jitter distribution omitted
- trial/block counts for QA/sim shortened relative to human profile
- trigger code numbering absent

## Failure Condition

If core paradigm cannot be reconstructed from available open-access papers, stop and report blocker:

- `insufficient_protocol_evidence`
