# Inference Rules (v0.2)

## Existing-task mode

Primary extraction source order:

1. `src/run_trial.py` for phase sequence and branch condition logic.
2. `config/config.yaml` for durations, conditions, key mappings, and stimuli examples.
3. `README.md` for supporting flow descriptions and audit evidence.

Condition timelines:

- One timeline per condition from `task.conditions`.
- If conditions exceed `max_conditions`, truncate and record in audit.

Phase extraction:

- Parse `set_trial_context(...)` calls in `run_trial.py` in execution order.
- Respect `if/else` branch predicates where parsable.
- Match `capture_response(...)` windows to phase units.

Duration extraction:

- Prefer `deadline_s` and `capture_response(duration=...)` expressions.
- Resolve from `settings.<key>`, local variables, and config values.
- Handle SSD-like adaptive windows as ranges when needed.

Stimulus examples:

- Prefer `stim_id` from `set_trial_context`.
- Fallback to `add_stim(...)` calls on the same unit.
- Resolve from `stimuli` config where possible.
- If non-visual or dynamic/unresolved, annotate textually.

## Source mode

- PDF via PyMuPDF text extraction.
- URL via requests + BeautifulSoup text extraction.
- Methods file/text via direct read.

- Parse condition keywords and phase keywords.
- Parse nearby timing units into duration/response windows.
- Build one timeline per selected condition.

## Plot constraints

- Timeline collection only.
- Wide screens only (aspect > 1.2).
- Overlap screens by `screen_overlap_ratio` (default 5%).
- Use sloped timeline baseline plus parallel line under screens.
- Screen labels include phase, duration, and response window.
- Output file must be `<task>/task_flow.png`.
