from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .secrets import redact_text
from .utils import atomic_write_text, iso_now, normalize_command


def _prepare_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("AFR", "1")
    return env


def _next_command_id(commands_dir: Path) -> str:
    commands_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    for path in commands_dir.glob("cmd-*.*"):
        prefix = path.name.split(".", 1)[0]
        if prefix.startswith("cmd-"):
            used.add(prefix)
    index = 1
    while True:
        candidate = f"cmd-{index:04d}"
        if candidate not in used:
            return candidate
        index += 1


def _spawn_error_message(argv: list[str], exc: OSError) -> tuple[int, str]:
    command = argv[0] if argv else "<empty>"
    if isinstance(exc, FileNotFoundError):
        return 127, f"afr: command not found: {command}\n"
    if isinstance(exc, PermissionError):
        return 126, f"afr: permission denied: {command}\n"
    return 1, f"afr: could not start command {command}: {exc}\n"


def run_command(
    *,
    root: Path,
    session_dir: Path,
    argv: list[str],
    capture_output: bool,
    redact_output: bool,
) -> dict[str, Any]:
    if not argv:
        raise ValueError("argv must not be empty")
    commands_dir = session_dir / "commands"
    command_id = _next_command_id(commands_dir)
    stdout_path = commands_dir / f"{command_id}.stdout.log"
    stderr_path = commands_dir / f"{command_id}.stderr.log"
    started_at = iso_now()
    record: dict[str, Any] = {
        "id": command_id,
        "argv": argv,
        "command": normalize_command(argv),
        "cwd": str(root),
        "started_at": started_at,
        "ended_at": None,
        "exit_code": None,
        "capture_output": capture_output,
        "stdout_path": stdout_path.relative_to(session_dir).as_posix(),
        "stderr_path": stderr_path.relative_to(session_dir).as_posix(),
    }

    if capture_output:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(root),
                env=_prepare_env(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            stdout = redact_text(proc.stdout) if redact_output else proc.stdout
            stderr = redact_text(proc.stderr) if redact_output else proc.stderr
            record["exit_code"] = proc.returncode
        except OSError as exc:
            exit_code, stderr = _spawn_error_message(argv, exc)
            stdout = ""
            record["exit_code"] = exit_code
        atomic_write_text(stdout_path, stdout)
        atomic_write_text(stderr_path, stderr)
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
    else:
        with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
            out.write("[afr: output capture disabled; child inherited terminal stdout]\n")
            err.write("[afr: output capture disabled; child inherited terminal stderr]\n")
        try:
            proc = subprocess.run(argv, cwd=str(root), env=_prepare_env(), check=False)
            record["exit_code"] = proc.returncode
        except OSError as exc:
            exit_code, stderr = _spawn_error_message(argv, exc)
            with stderr_path.open("a", encoding="utf-8") as err:
                err.write(stderr)
            sys.stderr.write(stderr)
            record["exit_code"] = exit_code

    record["ended_at"] = iso_now()
    return record


def command_looks_like_test(command: dict[str, Any], patterns: list[str]) -> bool:
    text = str(command.get("command", "")).lower()
    argv = [str(part).lower() for part in command.get("argv", [])]
    joined = " ".join(argv)
    for pattern in patterns:
        p = str(pattern).lower()
        if p in text or p in joined:
            return True
    # Lightweight fallback: commands such as `pytest tests/foo.py` or `npm run test:unit`.
    if "test" in joined and any(token in joined for token in ["pytest", "npm", "yarn", "pnpm", "bun", "go", "cargo", "flutter", "dart", "gradle", "mvn", "dotnet"]):
        return True
    return False
