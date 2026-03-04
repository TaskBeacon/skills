# Task Plot Audit

- generated_at: <ISO timestamp>
- mode: <existing|source>
- task_path: <absolute task path>

## 1. Inputs and provenance

- <README/config/run_trial path OR source path/url/text>

## 2. Evidence extracted from README

- <trial-flow table rows or fallback note>

## 3. Evidence extracted from config/source

- <phase extraction evidence>
- <duration/response window extraction evidence>
- <stimulus mapping evidence>

## 4. Mapping to task_plot_spec

- root_key: task_plot_spec
- spec_version: 0.2
- one timeline per condition
- one phase screen per timeline step

## 5. Style decision and rationale

- timeline collection fixed by policy

## 6. Rendering parameters and constraints

- output_file: task_flow.png
- dpi: <number>
- max_conditions: <number>
- screens_per_timeline: <number>
- screen_overlap_ratio: <number>
- screen_slope: <number>
- validator_warnings: <optional list>

## 7. Output files and checksums

- <path>: sha256=<digest>

## 8. Inferred/uncertain items

- <item list or none>
