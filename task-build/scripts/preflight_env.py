#!/usr/bin/env python3
"""Preflight environment checks for task-build workflows."""

from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
REQUIRED_MODULES = ("yaml", "psychopy", "psyflow")
REQUIRED_COMMANDS = ("git",)
OPTIONAL_COMMANDS = ("psyflow-qa", "psyflow-validate")
MODULE_TO_PACKAGE = {
    "yaml": "PyYAML",
    "psychopy": "psychopy",
    "psyflow": "psyflow",
}


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    combined = (proc.stdout or "") + (proc.stderr or "")
    return int(proc.returncode), combined.strip()


def _module_present(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def _install_module(
    python_exe: str,
    module_name: str,
    psyflow_source: Path | None,
) -> tuple[int, str]:
    if module_name == "psyflow" and psyflow_source is not None:
        if not psyflow_source.exists():
            return 1, f"psyflow source path does not exist: {psyflow_source}"
        return _run([python_exe, "-m", "pip", "install", "-e", str(psyflow_source)])

    package_name = MODULE_TO_PACKAGE[module_name]
    return _run([python_exe, "-m", "pip", "install", package_name])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check and optionally install task-build runtime dependencies.")
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Install missing required Python modules with pip.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for install commands (default: current interpreter).",
    )
    parser.add_argument(
        "--psyflow-source",
        default=None,
        help="Optional local psyflow source path used when psyflow is missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    py_version = sys.version_info
    if (py_version.major, py_version.minor) < MIN_PYTHON:
        print(
            f"[task-build] FAIL: Python>={MIN_PYTHON[0]}.{MIN_PYTHON[1]} required, "
            f"found {py_version.major}.{py_version.minor}.{py_version.micro}"
        )
        return 1

    missing_required_cmds = [cmd for cmd in REQUIRED_COMMANDS if shutil.which(cmd) is None]
    if missing_required_cmds:
        print(f"[task-build] FAIL: missing required system commands: {missing_required_cmds}")
        return 1

    missing_modules = [m for m in REQUIRED_MODULES if not _module_present(m)]
    install_logs: list[str] = []

    psyflow_source = Path(args.psyflow_source).resolve() if args.psyflow_source else None
    if missing_modules and args.install_missing:
        pip_check_rc, pip_check_out = _run([args.python, "-m", "pip", "--version"])
        if pip_check_rc != 0:
            print("[task-build] FAIL: pip is not available for dependency installation.")
            if pip_check_out:
                print(pip_check_out)
            return 1

        for module_name in list(missing_modules):
            rc, out = _install_module(args.python, module_name, psyflow_source)
            install_logs.append(f"[{module_name}] rc={rc}")
            if out:
                install_logs.append(out)
        missing_modules = [m for m in REQUIRED_MODULES if not _module_present(m)]

    missing_optional_cmds = [cmd for cmd in OPTIONAL_COMMANDS if shutil.which(cmd) is None]

    print(
        f"[task-build] python={py_version.major}.{py_version.minor}.{py_version.micro} "
        f"required>={MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    )
    if install_logs:
        print("[task-build] install-log-start")
        for line in install_logs:
            print(line)
        print("[task-build] install-log-end")

    if missing_optional_cmds:
        print(
            "[task-build] WARN: optional CLI shortcuts not found: "
            f"{missing_optional_cmds}. fallback module invocations will be used."
        )

    if missing_modules:
        printable = ", ".join(missing_modules)
        print(f"[task-build] FAIL: missing required Python modules: {printable}")
        print(
            "[task-build] hint: run "
            "`python scripts/preflight_env.py --install-missing --psyflow-source <path-to-psyflow>`"
        )
        return 1

    print("[task-build] PASS: environment preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
