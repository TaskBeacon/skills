# Publish Checklist

Use this checklist before commit/push.

## Preconditions

- All required gates pass (`check_task_standard`, validate, qa, scripted sim, sampler sim)
- References bundle exists and is current
- `references/stimulus_mapping.md` is fully resolved and cited
- No placeholder/dummy assets exist in `assets/`
- Participant-facing language is consistent across instructions/cues/feedback/screens.

## Files to Verify

- `README.md`
- `CHANGELOG.md`
- `taskbeacon.yaml`
- `config/*.yaml`
- `responders/*`
- `references/*`

## Commit Requirements

- Commit message describes task and standard-alignment changes
- No unrelated file changes included
- No temporary files staged

## Push Requirements

- Push to active branch on `origin`
- Capture push stdout/stderr
- If push fails, provide exact remediation commands

## Post-Publish Report

Report must include:

- commit hash
- branch
- push destination
- gate summary
- notable assumptions/inferences
- stimulus evidence summary (how implemented stimuli match references)
