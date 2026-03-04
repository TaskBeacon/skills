# Reference Artifact Contract

This contract defines minimum format and structure requirements for evidence artifacts under `references/`.

## 1. `references.yaml`

Top-level keys:

- `task_id`
- `generated_at`
- `selection_policy`
- `citation_threshold`
- `papers`

Each `papers[]` entry must include:

- `id`
- `title`
- `year`
- `journal`
- `doi_or_url`
- `citation_count`
- `open_access`
- `is_high_impact`
- `used_for`

## 2. `references.md`

Required headings:

- `# References`
- `## Selected Papers`

Required table columns (single table):

- `ID`
- `Year`
- `Citations`
- `Journal`
- `High Impact`
- `Open Access`
- `Title`

## 3. `parameter_mapping.md`

Required headings:

- `# Parameter Mapping`
- `## Mapping Table`

Required table columns:

- `Parameter ID`
- `Config Path`
- `Implemented Value`
- `Source Paper ID`
- `Evidence (quote/figure/table)`
- `Decision Type`
- `Notes`

`Decision Type` should be one of:

- `direct`
- `adapted`
- `inferred`

## 4. `stimulus_mapping.md`

Required headings:

- `# Stimulus Mapping`
- `## Mapping Table`

Required table columns:

- `Condition`
- `Stage/Phase`
- `Stimulus IDs`
- `Participant-Facing Content`
- `Source Paper ID`
- `Evidence (quote/figure/table)`
- `Implementation Mode`
- `Asset References`
- `Notes`

Forbidden unresolved markers:

- `UNSET`
- `TODO`
- `required_review`

Allowed `Implementation Mode` values:

- `psychopy_builtin`
- `generated_reference_asset`
- `licensed_external_asset`

## 5. `task_logic_audit.md`

Must contain the section headings from `assets/templates/task_logic_audit_template.md`:

- `## 1. Paradigm Intent`
- `## 2. Block/Trial Workflow`
- `## 3. Condition Semantics`
- `## 4. Response and Scoring Rules`
- `## 5. Stimulus Layout Plan`
- `## 6. Trigger Plan`
- `## 7. Architecture Decisions (Auditability)`
- `## 8. Inference Log`
