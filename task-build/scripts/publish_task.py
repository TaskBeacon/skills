#!/usr/bin/env python3
"""Commit and push a task repository after successful gates."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish task changes via git add/commit/push.")
    parser.add_argument("--task-path", required=True)
    parser.add_argument("--message", default=None, help="Commit message")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default=None, help="Branch to push; defaults to current branch")
    parser.add_argument("--no-push", action="store_true", help="Commit only, skip push")
    parser.add_argument("--allow-empty", action="store_true", help="Allow empty commits")
    return parser.parse_args()


def _current_branch(task_path: Path) -> str:
    proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], task_path, check=True)
    return proc.stdout.strip()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()

    status = _run(["git", "status", "--short"], task_path, check=True)
    if not status.stdout.strip() and not args.allow_empty:
        print("[task-build] No changes to commit.")
        return 0

    branch = args.branch or _current_branch(task_path)
    default_message = f"Align {task_path.name} with PsyFlow task-build standards"
    message = args.message or default_message

    _run(["git", "add", "."], task_path, check=True)

    commit_cmd = ["git", "commit", "-m", message]
    if args.allow_empty:
        commit_cmd.insert(2, "--allow-empty")

    commit = _run(commit_cmd, task_path)
    if commit.returncode != 0:
        print("[task-build] Commit failed", file=sys.stderr)
        print(commit.stdout)
        print(commit.stderr, file=sys.stderr)
        return 1

    print(commit.stdout.strip())

    if args.no_push:
        print("[task-build] Push skipped (--no-push).")
        return 0

    push = _run(["git", "push", args.remote, branch], task_path)
    if push.returncode != 0:
        print("[task-build] Push failed", file=sys.stderr)
        print(push.stdout)
        print(push.stderr, file=sys.stderr)
        print("[task-build] Remediation:", file=sys.stderr)
        print(f"  cd {task_path}", file=sys.stderr)
        print(f"  git push {args.remote} {branch}", file=sys.stderr)
        return 2

    print(push.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
