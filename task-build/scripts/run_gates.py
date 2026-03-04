#!/usr/bin/env python3
"""Run validate/qa/sim gates with a deterministic retry loop."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


def _latest_contract_version(repo_root: Path) -> str:
    contracts_root = repo_root / "psyflow" / "contracts"
    versions = [p.name for p in contracts_root.glob("v*") if p.is_dir()]
    if not versions:
        return "v0.1.0"

    def key(v: str) -> tuple[int, ...]:
        raw = v.lstrip("v")
        try:
            return tuple(int(x) for x in raw.split("."))
        except ValueError:
            return (0,)

    return sorted(versions, key=key)[-1]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _ensure_configs(task_path: Path) -> list[str]:
    changed: list[str] = []
    cfg_dir = task_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    base_path = cfg_dir / "config.yaml"
    base_cfg = _read_yaml(base_path)

    if base_cfg:
        if "qa" in base_cfg or "sim" in base_cfg:
            base_cfg.pop("qa", None)
            base_cfg.pop("sim", None)
            _write_yaml(base_path, base_cfg)
            changed.append("normalized config/config.yaml (removed qa/sim sections)")

    qa_path = cfg_dir / "config_qa.yaml"
    if not qa_path.exists() and base_cfg:
        qa_cfg = dict(base_cfg)
        qa_cfg.pop("sim", None)
        qa_cfg["qa"] = {
            "output_dir": "outputs/qa",
            "enable_scaling": True,
            "timing_scale": 0.2,
            "min_frames": 1,
            "strict": False,
            "max_wait_s": 10.0,
            "acceptance_criteria": {
                "required_columns": ["condition"],
                "expected_trial_count": 1,
                "allowed_keys": ["space"],
                "triggers_required": True,
            },
        }
        _write_yaml(qa_path, qa_cfg)
        changed.append("created config/config_qa.yaml")

    scripted_path = cfg_dir / "config_scripted_sim.yaml"
    if not scripted_path.exists() and base_cfg:
        scripted = dict(base_cfg)
        scripted.pop("qa", None)
        scripted["sim"] = {
            "output_dir": "outputs/sim",
            "seed": 0,
            "participant_id": "sim001",
            "session_id": "sub-sim001",
            "log_path": "outputs/sim/sub-sim001_sim_events.jsonl",
            "policy": "warn",
            "default_rt_s": 0.2,
            "clamp_rt": False,
            "responder": {"type": "scripted", "kwargs": {"key": "space", "rt_s": 0.25}},
        }
        _write_yaml(scripted_path, scripted)
        changed.append("created config/config_scripted_sim.yaml")

    sampler_path = cfg_dir / "config_sampler_sim.yaml"
    if not sampler_path.exists() and base_cfg:
        sampler = dict(base_cfg)
        sampler.pop("qa", None)
        sampler["sim"] = {
            "output_dir": "outputs/sim_sampler",
            "seed": 0,
            "participant_id": "sim001",
            "session_id": "sub-sim001-sampler",
            "log_path": "outputs/sim_sampler/sub-sim001_sim_events.jsonl",
            "policy": "warn",
            "default_rt_s": 0.2,
            "clamp_rt": False,
            "responder": {
                "type": "responders.task_sampler:TaskSamplerResponder",
                "kwargs": {"continue_key": "space", "rt_continue_s": 0.25},
            },
        }
        _write_yaml(sampler_path, sampler)
        changed.append("created config/config_sampler_sim.yaml")

    return changed


def _ensure_taskbeacon_contract(task_path: Path, version: str) -> list[str]:
    changed: list[str] = []
    tb_path = task_path / "taskbeacon.yaml"
    if not tb_path.exists():
        return changed
    payload = _read_yaml(tb_path)
    contracts = payload.get("contracts")
    if not isinstance(contracts, dict):
        contracts = {}
        payload["contracts"] = contracts
    if contracts.get("psyflow_taps") != version:
        contracts["psyflow_taps"] = version
        changed.append(f"updated taskbeacon contracts.psyflow_taps -> {version}")
    if changed:
        _write_yaml(tb_path, payload)
    return changed


def _ensure_gitignore(task_path: Path) -> list[str]:
    changed: list[str] = []
    p = task_path / ".gitignore"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    lines = text.splitlines()
    required = ["/outputs/*", "!/outputs/.gitkeep"]
    for rule in required:
        if rule not in lines:
            lines.append(rule)
            changed.append(f"appended {rule} to .gitignore")
    if changed:
        p.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return changed


def _ensure_outputs(task_path: Path) -> list[str]:
    p = task_path / "outputs" / ".gitkeep"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        return ["created outputs/.gitkeep"]
    return []


def _ensure_responders(task_path: Path) -> list[str]:
    changed: list[str] = []
    responders = task_path / "responders"
    responders.mkdir(parents=True, exist_ok=True)

    init_py = responders / "__init__.py"
    if not init_py.exists():
        init_py.write_text('"""Task-specific responder plugins."""\n', encoding="utf-8")
        changed.append("created responders/__init__.py")

    sampler = responders / "task_sampler.py"
    if not sampler.exists():
        sampler.write_text(
            "from __future__ import annotations\n\n"
            "from psyflow.sim import Action, Observation, ResponderProtocol\n\n"
            "class TaskSamplerResponder(ResponderProtocol):\n"
            "    def __init__(self, continue_key: str = \"space\", rt_continue_s: float = 0.25):\n"
            "        self.continue_key = continue_key\n"
            "        self.rt_continue_s = float(rt_continue_s)\n\n"
            "    def act(self, obs: Observation) -> Action:\n"
            "        valid = list(obs.valid_keys or [])\n"
            "        if valid and self.continue_key in valid:\n"
            "            return Action(key=self.continue_key, rt_s=self.rt_continue_s)\n"
            "        return Action(key=None, rt_s=None)\n",
            encoding="utf-8",
        )
        changed.append("created responders/task_sampler.py")

    return changed


def _apply_basic_fixes(task_path: Path, contracts_version: str) -> list[str]:
    changes: list[str] = []
    changes.extend(_ensure_outputs(task_path))
    changes.extend(_ensure_responders(task_path))
    changes.extend(_ensure_configs(task_path))
    changes.extend(_ensure_taskbeacon_contract(task_path, contracts_version))
    changes.extend(_ensure_gitignore(task_path))
    return changes


def _run(cmd: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "returncode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _qa_command(python_exe: str, task_path: Path) -> list[str]:
    if shutil.which("psyflow-qa"):
        return ["psyflow-qa", str(task_path), "--config", "config/config_qa.yaml", "--no-maturity-update"]
    return [
        python_exe,
        "-c",
        (
            "from psyflow.task_launcher import run_qa_shortcut; "
            "import sys; "
            "raise SystemExit(run_qa_shortcut(sys.argv[1:]))"
        ),
        str(task_path),
        "--config",
        "config/config_qa.yaml",
        "--no-maturity-update",
    ]


def _validate_command(python_exe: str, task_path: Path, contracts_version: str) -> list[str]:
    if shutil.which("psyflow-validate"):
        return ["psyflow-validate", str(task_path), "--contracts-version", contracts_version]
    return [python_exe, "-m", "psyflow.validate", str(task_path), "--contracts-version", contracts_version]


def _standard_command(python_exe: str, task_path: Path) -> list[str]:
    checker = Path(__file__).resolve().parent / "check_task_standard.py"
    return [python_exe, str(checker), "--task-path", str(task_path)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PsyFlow gates with deterministic retry logic.")
    parser.add_argument("--task-path", required=True)
    parser.add_argument("--python", default=sys.executable, help="Python executable for task runs")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retry count after failures")
    parser.add_argument("--contracts-version", default=None, help="Override contracts version")
    parser.add_argument(
        "--fix-command",
        default=None,
        help="Optional shell command executed after a failed attempt. Supports {task_path} and {attempt} placeholders.",
    )
    parser.add_argument("--report", default=None, help="Path to JSON gate report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_path).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    contracts_version = args.contracts_version or _latest_contract_version(repo_root)

    report_path = Path(args.report).resolve() if args.report else (task_path / "outputs" / "qa" / "gate_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    attempts: list[dict[str, Any]] = []
    status = "fail"

    total_attempts = args.max_retries + 1
    for attempt in range(1, total_attempts + 1):
        attempt_record: dict[str, Any] = {
            "attempt": attempt,
            "timestamp": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "contracts_version": contracts_version,
            "gates": [],
            "fixes": [],
        }

        gates = [
            ("standard", _standard_command(args.python, task_path), task_path),
            ("qa", _qa_command(args.python, task_path), repo_root),
            (
                "scripted_sim",
                [args.python, "main.py", "sim", "--config", "config/config_scripted_sim.yaml"],
                task_path,
            ),
            (
                "sampler_sim",
                [args.python, "main.py", "sim", "--config", "config/config_sampler_sim.yaml"],
                task_path,
            ),
            ("validate", _validate_command(args.python, task_path, contracts_version), repo_root),
        ]

        failed_gate: str | None = None
        for gate_name, cmd, cwd in gates:
            result = _run(cmd, cwd)
            result["gate"] = gate_name
            attempt_record["gates"].append(result)
            if result["returncode"] != 0:
                failed_gate = gate_name
                break

        if failed_gate is None:
            status = "pass"
            attempts.append(attempt_record)
            break

        if attempt < total_attempts:
            fixes = _apply_basic_fixes(task_path, contracts_version)
            attempt_record["fixes"].extend(fixes)

            if args.fix_command:
                cmd = args.fix_command.format(task_path=str(task_path), attempt=attempt)
                proc = subprocess.run(cmd, shell=True, cwd=str(task_path), capture_output=True, text=True)
                attempt_record["fixes"].append(
                    {
                        "custom_fix_command": cmd,
                        "returncode": int(proc.returncode),
                        "stdout": proc.stdout,
                        "stderr": proc.stderr,
                    }
                )

        attempts.append(attempt_record)

    report = {
        "task_path": str(task_path),
        "status": status,
        "max_retries": args.max_retries,
        "contracts_version": contracts_version,
        "attempts": attempts,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[task-build] status={status}")
    print(f"[task-build] report={report_path}")

    if status != "pass":
        last = attempts[-1] if attempts else {}
        print("[task-build] FAIL: at least one gate still failing after retries", file=sys.stderr)
        if last:
            for gate in last.get("gates", []):
                if gate.get("returncode", 0) != 0:
                    print(f"[task-build] failing_gate={gate.get('gate')} rc={gate.get('returncode')}", file=sys.stderr)
                    break
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
