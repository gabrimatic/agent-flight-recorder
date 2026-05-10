from __future__ import annotations

from pathlib import Path

from .git import git_root


def repo_root(cwd: Path | None = None) -> Path:
    return git_root((cwd or Path.cwd()).resolve())


def afr_dir(root: Path) -> Path:
    return root / ".agent-flight"


def config_path(root: Path) -> Path:
    return afr_dir(root) / "config.json"


def sessions_dir(root: Path) -> Path:
    return afr_dir(root) / "sessions"


def tmp_dir(root: Path) -> Path:
    return afr_dir(root) / "tmp"


def active_session_path(root: Path) -> Path:
    return afr_dir(root) / "active-session.json"


def latest_manifest_path(root: Path) -> Path:
    return afr_dir(root) / "manifest.json"


def latest_report_path(root: Path) -> Path:
    return afr_dir(root) / "pr-report.md"


def session_dir(root: Path, session_id: str) -> Path:
    return sessions_dir(root) / session_id


def session_manifest_path(root: Path, session_id: str) -> Path:
    return session_dir(root, session_id) / "manifest.json"
