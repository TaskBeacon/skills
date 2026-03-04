# Literature Search Playbook

Use this playbook to gather candidate papers for a task protocol.

## Goal

Produce a filtered paper set with:

- at least 3 selected papers
- at least 1 high-impact journal paper
- all selected papers open access
- all selected papers citation count >= 100

## Query Construction

Build search with three parts:

1. canonical task name
2. common aliases/synonyms
3. modality qualifiers (for example: EEG, fMRI)

Example:

- canonical: "monetary incentive delay"
- aliases: "MID task", "reward anticipation"
- modality: "EEG"

## Selection Order

1. Rank by citation count (descending)
2. Promote high-impact journal matches
3. Keep papers with clear methods/protocol descriptions
4. Remove paywalled papers
5. Prefer papers with explicit stimulus descriptions (materials, figures, timing, response options)

## Inclusion Rules

Include a paper only if all are true:

- open access = true
- citation count >= threshold
- publication type supports protocol extraction (article/report)

## Exclusion Rules

Exclude when:

- paywalled
- no methods or protocol details
- retracted
- unrelated paradigm with same keywords

## Output

Write two JSON files:

- `references/candidate_papers.json`
- `references/selected_papers.json`

Then run `build_reference_bundle.py`.

During extraction, capture stimulus-specific evidence (figure/table/text) for later entry in `references/stimulus_mapping.md`.
