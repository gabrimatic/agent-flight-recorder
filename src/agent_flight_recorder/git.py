from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from .exceptions import GitError


def run_git(root: Path | None, args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *list(args)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root) if root else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable was not found on PATH") from exc
    if check and proc.returncode != 0:
        joined = " ".join(cmd)
        raise GitError(f"{joined} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def git_root(cwd: Path) -> Path:
    proc = run_git(cwd, ["rev-parse", "--show-toplevel"], check=False)
    if proc.returncode != 0:
        raise GitError("Agent Flight Recorder must run inside a git repository")
    return Path(proc.stdout.strip()).resolve()


def is_git_repo(cwd: Path) -> bool:
    proc = run_git(cwd, ["rev-parse", "--is-inside-work-tree"], check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def head_sha(root: Path) -> str:
    proc = run_git(root, ["rev-parse", "--verify", "HEAD"], check=False)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def current_branch(root: Path) -> str:
    proc = run_git(root, ["branch", "--show-current"], check=False)
    branch = proc.stdout.strip()
    if branch:
        return branch
    proc = run_git(root, ["rev-parse", "--short", "HEAD"], check=False)
    return f"detached@{proc.stdout.strip()}" if proc.returncode == 0 else "unknown"


def status_porcelain(root: Path) -> str:
    proc = run_git(root, ["status", "--porcelain=v1"], check=False)
    return proc.stdout if proc.returncode == 0 else ""


def has_ref(root: Path, ref: str) -> bool:
    proc = run_git(root, ["rev-parse", "--verify", ref], check=False)
    return proc.returncode == 0


def fallback_base_ref(root: Path) -> str | None:
    candidates = ["origin/main", "origin/master", "main", "master", "HEAD~1"]
    for candidate in candidates:
        if has_ref(root, candidate):
            return candidate
    return None


def _worktree_diff_text(root: Path) -> str:
    text = ""
    proc = run_git(root, ["diff", "--unified=0", "--no-ext-diff"], check=False)
    if proc.returncode == 0:
        text = proc.stdout
    cached = run_git(root, ["diff", "--cached", "--unified=0", "--no-ext-diff"], check=False)
    if cached.returncode == 0 and cached.stdout:
        text = text + "\n" + cached.stdout
    return text


def diff_text(root: Path, base_ref: str | None = None, max_bytes: int = 2_000_000) -> str:
    text = ""
    if base_ref:
        proc = run_git(root, ["diff", "--unified=0", "--no-ext-diff", f"{base_ref}...HEAD"], check=False)
        if proc.returncode == 0:
            text = proc.stdout
        worktree = _worktree_diff_text(root)
        if worktree:
            text = text + "\n" + worktree
    else:
        text = _worktree_diff_text(root)
    if len(text.encode("utf-8", errors="replace")) > max_bytes:
        encoded = text.encode("utf-8", errors="replace")[:max_bytes]
        text = encoded.decode("utf-8", errors="replace") + "\n[afr: diff truncated]\n"
    return text


def parse_name_status_z(raw: str) -> list[dict[str, str]]:
    if not raw:
        return []
    tokens = raw.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    result: list[dict[str, str]] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        i += 1
        if not status:
            continue
        code = status[0]
        if code in {"R", "C"} and i + 1 < len(tokens):
            old_path = tokens[i]
            new_path = tokens[i + 1]
            i += 2
            result.append({"path": new_path, "old_path": old_path, "status": code, "raw_status": status})
        elif i < len(tokens):
            path = tokens[i]
            i += 1
            result.append({"path": path, "status": code, "raw_status": status})
        else:
            break
    return result


def changed_files_from_git(root: Path, base_ref: str | None = None) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    if base_ref:
        proc = run_git(root, ["diff", "--name-status", "--find-renames", "-z", f"{base_ref}...HEAD"], check=False)
        if proc.returncode == 0:
            parsed.extend(parse_name_status_z(proc.stdout))
    proc = run_git(root, ["diff", "--name-status", "--find-renames", "-z"], check=False)
    parsed.extend(parse_name_status_z(proc.stdout if proc.returncode == 0 else ""))
    proc_cached = run_git(root, ["diff", "--cached", "--name-status", "--find-renames", "-z"], check=False)
    parsed.extend(parse_name_status_z(proc_cached.stdout if proc_cached.returncode == 0 else ""))
    proc_status = run_git(root, ["status", "--porcelain=v1", "-z"], check=False)
    if proc_status.returncode == 0:
        parsed.extend(parse_status_porcelain_z(proc_status.stdout))
    dedup: dict[str, dict[str, str]] = {}
    for item in parsed:
        dedup[item["path"]] = item
    return sorted(dedup.values(), key=lambda x: x["path"])


def parse_status_porcelain_z(raw: str) -> list[dict[str, str]]:
    tokens = raw.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    result: list[dict[str, str]] = []
    i = 0
    while i < len(tokens):
        entry = tokens[i]
        i += 1
        if not entry or len(entry) < 4:
            continue
        status = entry[:2]
        path = entry[3:]
        code = status.strip()[:1] or "?"
        if status.startswith("R") or status.startswith("C"):
            if i < len(tokens):
                old_path = tokens[i]
                i += 1
                result.append({"path": path, "old_path": old_path, "status": code, "raw_status": status})
        else:
            result.append({"path": path, "status": code, "raw_status": status})
    return result
