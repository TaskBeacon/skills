#!/usr/bin/env python3
"""Smoke tests for task-plot v0.2."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("[RUN] " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    # Existing tasks
    sternberg = REPO_ROOT / "T000035-sternberg-working-memory"
    sst = REPO_ROOT / "T000012-sst"

    if sternberg.exists():
        _run(
            [
                sys.executable,
                str(SCRIPT_DIR / "make_task_plot.py"),
                "--mode",
                "existing",
                "--task-path",
                str(sternberg),
                "--max-conditions",
                "4",
                "--screens-per-timeline",
                "6",
            ]
        )
    if sst.exists():
        _run(
            [
                sys.executable,
                str(SCRIPT_DIR / "make_task_plot.py"),
                "--mode",
                "existing",
                "--task-path",
                str(sst),
                "--max-conditions",
                "4",
                "--screens-per-timeline",
                "6",
            ]
        )

    # Source mode with draft auto-create
    _run(
        [
            sys.executable,
            str(SCRIPT_DIR / "make_task_plot.py"),
            "--mode",
            "source",
            "--methods-text",
            "Fixation 500 ms, cue 200 ms, delay 1000-1500 ms, target 800 ms, feedback 500 ms. Conditions: go stop.",
            "--max-conditions",
            "2",
            "--screens-per-timeline",
            "5",
        ]
    )

    # Direct validate/render from template.
    _run(
        [
            sys.executable,
            str(SCRIPT_DIR / "render_task_plot.py"),
            "--spec",
            str(SKILL_DIR / "assets" / "spec_templates" / "timeline_collection_min.yaml"),
            "--out-png",
            str(SKILL_DIR / "assets" / "spec_templates" / "timeline_collection_min.preview.png"),
        ]
    )

    print("[OK] smoke tests completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
