from __future__ import annotations

import re
from pathlib import Path

from .exceptions import SessionError
from .git import git_root


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


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


def validate_session_id(session_id: str) -> str:
    if not SESSION_ID_RE.fullmatch(session_id):
        raise SessionError(
            "Invalid session id. Use 1-120 letters, numbers, dots, underscores, or hyphens; start with a letter or number."
        )
    return session_id


def session_dir(root: Path, session_id: str) -> Path:
    return sessions_dir(root) / validate_session_id(session_id)


def session_manifest_path(root: Path, session_id: str) -> Path:
    return session_dir(root, session_id) / "manifest.json"
