---
name: task-py2js
description: Convert a local psyflow task into an aligned psyflow-web task inside the TaskBeacon repository. Use when the user wants to port a `Txxxxxx-*` Python task to an `Hxxxxxx-*` HTML task, keep `main/config/run_trial/controller/utils` aligned, preserve trial procedure and parameter semantics, or review whether a web task stays faithful to its local canonical task.
---

# Task Py2Js

Port the task by preserving the local task contract, not by translating PsychoPy calls line by line.
Treat the local `Txxxxxx-*` repo as canonical and make the web `Hxxxxxx-*` repo a browser-native re-authoring of the same experiment.

## Workflow

### 1. Load the canonical local task

Read these files from the local task first:

- `taskbeacon.yaml`
- `main.py`
- `config/config.yaml`
- `src/run_trial.py`
- `src/controller.py` when present
- `src/utils.py` when present

Then read the current web runtime seam:

- `psyflow-web/src/core/`
- `psyflow-web/src/app/`
- `psyflow-web/src/jspsych/`

If you need a worked example, read:

- `H000006-mid/transfer_node.md`
- compare `T000006-mid/` against `H000006-mid/`

### 2. Define the alignment boundary before coding

Keep these aligned unless there is a task-specific reason not to:

- task identity: same `slug`, same conceptual title, matching `T` and `H` numeric id
- task structure: `main`, `config`, `run_trial`, `controller`, `utils`
- trial procedure: same stage order and response logic
- parameters: same timing, controller rules, instructions, scoring, and condition semantics
- data meaning: exported reduced trial rows must preserve the same analysis logic

Allow these to differ only as web-specific behavior:

- EEG and other hardware layers
- deployment/runtime shell
- fullscreen, cursor hiding, force quit, browser speech synthesis
- preview length such as fewer blocks or fewer trials

Before editing files, read `references/alignment-matrix.md`.

### 3. Create or normalize the html task repo

Use a TAPS-like layout:

```text
Hxxxxxx-task/
  main.ts
  README.md
  taskbeacon.yaml
  config/
    config.yaml
  src/
    run_trial.ts
    controller.ts
    utils.ts
```

Keep the task repo source-only.
Do not add per-task `node_modules`, `vite.config`, `dist`, or app-shell files there.
Those belong in `psyflow-web`.

### 4. Port the task in this order

1. Port `taskbeacon.yaml` and keep the same `slug`. Set `variant: html`.
2. Port `config/config.yaml` and align task-facing content first.
3. Port `main.py` to `main.ts`, but keep orchestration explicit. Do not hide task flow behind a new abstraction.
4. Port `run_trial.py` to `run_trial.ts` using `TrialBuilder` and `trial.unit(...).show/captureResponse/waitAndContinue`.
5. Port pure `controller` logic and pure `utils` logic with minimal semantic change.
6. Move generic browser concerns into `psyflow-web`, not into the individual `H` repo.

Keep the web signature shaped like:

```ts
run_trial(trial, condition, { settings, stimBank, controller, utils })
```

Do not import `jsPsych` directly from task files.

### 5. Keep `main.ts` readable like `main.py`

`main.ts` should still visibly orchestrate:

- config loading
- settings and subinfo setup
- `StimBank` creation
- block generation
- instruction screens
- block countdown and block break screens
- `run_trial(...)` calls
- mounting the task app

Keep reusable helpers in `psyflow-web`, but keep the task flow itself in `main.ts`.

### 6. Keep generic browser behaviors inside `psyflow-web`

Move these into framework code whenever they are not task-specific:

- fullscreen entry and guarding
- cursor hiding for keyboard tasks
- generic start screen and export screen
- force-quit shortcut
- countdown helper
- browser speech synthesis for instruction audio

Only leave task logic and task-specific content inside the `H` repo.

### 7. Validate alignment at the correct granularity

Use the checklist in `references/validation-checklist.md`.

At minimum verify:

- same condition set and block logic
- same stage order within a logical trial
- same response windows and hit/miss logic
- same controller update rule
- same instruction meaning and voice behavior when relevant
- same score semantics
- same reduced data meaning

For preview builds, shorten counts only after single-trial semantics match the local task.

Good preview differences:

- fewer blocks
- fewer trials

Bad preview differences:

- different timing model
- different controller rule
- different response semantics
- different feedback or scoring meaning

### 8. Validate the data contract

Preserve the TaskBeacon data contract:

- raw output can stay stage-level
- reduced output must be one logical trial per row

Prefer current `psyflow` vocabulary for exported fields.
Keep `unit_label`-prefixed reduced columns aligned with how the local task is analyzed.

### 9. Finish the web integration

When the task is runnable:

- ensure the shared runner can load the `H` repo
- ensure `taskbeacon.github.io` can pair the html variant to the local task
- ensure the live run URL uses the shared runner, not a per-task frontend app

## Deliverable Standard

A successful port should leave:

- a small, auditable `Hxxxxxx-*` task repo
- a `main.ts` that still reads like the local `main.py`
- a `run_trial.ts` that expresses the same trial contract through `psyflow-web`
- browser-only concerns absorbed by `psyflow-web`
- parameter and procedure alignment explicit and reviewable

## Output Expectations

When using this skill, report:

- what local task was treated as canonical
- what files were created or updated in the `H` repo
- which parts were aligned exactly
- which parts intentionally differ for web or preview reasons
- what was verified and what still needs validation
