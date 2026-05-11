from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO

from .secrets import redact_argv, redact_text
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


def _read_pipe(stream: BinaryIO, limit: int, result: dict[str, Any]) -> None:
    data = bytearray()
    total = 0
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if len(data) < limit:
            remaining = limit - len(data)
            data.extend(chunk[:remaining])
    result["data"] = bytes(data)
    result["truncated"] = total > limit


def _decode_captured_output(data: bytes, *, stream_name: str, truncated: bool, limit: int, redact_output: bool) -> str:
    text = data.decode("utf-8", errors="replace")
    if redact_output:
        text = redact_text(text)
    if truncated:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"[afr: {stream_name} truncated after {limit} bytes]\n"
    return text


def run_command(
    *,
    root: Path,
    session_dir: Path,
    argv: list[str],
    capture_output: bool,
    redact_output: bool,
    max_output_bytes: int = 1_000_000,
) -> dict[str, Any]:
    if not argv:
        raise ValueError("argv must not be empty")
    commands_dir = session_dir / "commands"
    command_id = _next_command_id(commands_dir)
    stdout_path = commands_dir / f"{command_id}.stdout.log"
    stderr_path = commands_dir / f"{command_id}.stderr.log"
    started_at = iso_now()
    recorded_argv = redact_argv(argv)
    record: dict[str, Any] = {
        "id": command_id,
        "argv": recorded_argv,
        "command": normalize_command(recorded_argv),
        "cwd": str(root),
        "started_at": started_at,
        "ended_at": None,
        "exit_code": None,
        "capture_output": capture_output,
        "stdout_path": stdout_path.relative_to(session_dir).as_posix(),
        "stderr_path": stderr_path.relative_to(session_dir).as_posix(),
        "stdout_truncated": False,
        "stderr_truncated": False,
    }

    if capture_output:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(root),
                env=_prepare_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout_result: dict[str, Any] = {}
            stderr_result: dict[str, Any] = {}
            stdout_thread = threading.Thread(target=_read_pipe, args=(proc.stdout, max_output_bytes, stdout_result))
            stderr_thread = threading.Thread(target=_read_pipe, args=(proc.stderr, max_output_bytes, stderr_result))
            stdout_thread.start()
            stderr_thread.start()
            proc.wait()
            stdout_thread.join()
            stderr_thread.join()
            record["exit_code"] = proc.returncode
            record["stdout_truncated"] = bool(stdout_result.get("truncated"))
            record["stderr_truncated"] = bool(stderr_result.get("truncated"))
            stdout = _decode_captured_output(
                stdout_result.get("data", b""),
                stream_name="stdout",
                truncated=bool(stdout_result.get("truncated")),
                limit=max_output_bytes,
                redact_output=redact_output,
            )
            stderr = _decode_captured_output(
                stderr_result.get("data", b""),
                stream_name="stderr",
                truncated=bool(stderr_result.get("truncated")),
                limit=max_output_bytes,
                redact_output=redact_output,
            )
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
            run_proc = subprocess.run(argv, cwd=str(root), env=_prepare_env(), check=False)
            record["exit_code"] = run_proc.returncode
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
    if _task_runner_looks_like_test(argv):
        return True
    # Lightweight fallback: commands such as `pytest tests/foo.py` or `npm run test:unit`.
    if "test" in joined and any(token in joined for token in ["pytest", "npm", "yarn", "pnpm", "bun", "go", "cargo", "flutter", "dart", "gradle", "mvn", "dotnet"]):
        return True
    return False


def _task_runner_looks_like_test(argv: list[str]) -> bool:
    if not argv:
        return False
    executable = Path(argv[0]).name
    if executable in {"tox", "nox"}:
        return True
    if executable not in {"make", "gmake", "just", "task"}:
        return False
    options_with_values = {"-c", "-f", "--directory", "--file", "--makefile"}
    skip_next = False
    for token in argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in options_with_values:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        target = token.strip().replace("_", "-")
        if target in {"test", "tests", "check", "ci"}:
            return True
        if target.startswith(("test-", "test:", "tests-", "tests:", "check-", "check:")):
            return True
    return False
