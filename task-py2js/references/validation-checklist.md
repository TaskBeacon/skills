# Validation Checklist

Run this checklist before calling a port aligned.

## Source Review

- Read local `taskbeacon.yaml`, `main.py`, `config/config.yaml`, `src/run_trial.py`.
- Read local `controller` and `utils` modules if they exist.
- Identify the canonical condition set, timing values, and score logic.

## Repo Structure

- Create or normalize a TAPS-like `Hxxxxxx-*` layout.
- Keep build tooling out of the individual task repo.
- Keep the same `slug` and set `variant: html`.

## Procedure Alignment

- Compare local and web stage order side by side.
- Compare valid keys and response windows side by side.
- Compare feedback branch logic side by side.
- Compare controller update timing and formulas side by side.

## Parameter Alignment

- Match timing parameters unless the change is explicitly preview-only.
- Match instructions and task-facing texts.
- Match score semantics and displayed outcome meaning.
- Match condition balancing logic.

## Data Alignment

- Confirm raw output contains enough stage detail for audit.
- Confirm reduced output is one logical trial per row.
- Confirm reduced column meanings still support the same downstream analysis.

## Framework Boundary

- Confirm task files do not import `jsPsych` directly.
- Confirm generic browser behaviors live in `psyflow-web`.
- Confirm `main.ts` still reads as task orchestration, not framework plumbing.

## Final Verification

- Run the task in the browser.
- Verify at least one representative hit and miss path.
- Verify exports download correctly.
- Confirm `.github/workflows/notify-psyflow-web.yml` exists in the `H` repo.
- Confirm the workflow points to `TaskBeacon/psyflow-web` and uses `event_type: html-task-updated`.
- Document any intentional local-vs-web differences.
