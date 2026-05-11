from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import load_config, write_default_config
from .exceptions import SessionError
from .git import changed_files_from_git, current_branch, diff_text, fallback_base_ref, head_sha, status_porcelain
from .paths import (
    active_session_path,
    afr_dir,
    config_path,
    latest_manifest_path,
    latest_report_path,
    session_dir,
    session_manifest_path,
    sessions_dir,
)
from .process_recorder import run_command
from .report import render_markdown
from .risk import analyze_manifest
from .snapshot import compare_inventories, enrich_git_changes, inventory
from .utils import ensure_dir, iso_now, json_dump, json_load, stable_session_id


SCHEMA_VERSION = "1.0"


def init_project(root: Path, *, force: bool = False) -> None:
    ensure_dir(afr_dir(root))
    ensure_dir(sessions_dir(root))
    cfg = config_path(root)
    if force or not cfg.exists():
        write_default_config(cfg, force=True)
    gitignore = afr_dir(root) / ".gitignore"
    if force or not gitignore.exists():
        gitignore.write_text(
            "sessions/\n"
            "tmp/\n"
            "active-session.json\n"
            "manifest.json\n"
            "*.log\n"
            "!config.json\n"
            "!pr-report.md\n",
            encoding="utf-8",
        )


def ensure_project(root: Path) -> dict[str, Any]:
    ensure_dir(afr_dir(root))
    ensure_dir(sessions_dir(root))
    if not config_path(root).exists():
        write_default_config(config_path(root), force=False)
    if not (afr_dir(root) / ".gitignore").exists():
        (afr_dir(root) / ".gitignore").write_text(
            "sessions/\n"
            "tmp/\n"
            "active-session.json\n"
            "manifest.json\n"
            "*.log\n"
            "!config.json\n"
            "!pr-report.md\n",
            encoding="utf-8",
        )
    return load_config(config_path(root))


def base_manifest(root: Path, session_id: str, *, note: str | None = None, mode: str = "manual") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "agent-flight-recorder",
        "session_id": session_id,
        "mode": mode,
        "note": note or "",
        "started_at": iso_now(),
        "ended_at": None,
        "repository": {
            "root": str(root),
            "branch": current_branch(root),
            "head": head_sha(root),
            "status_before": status_porcelain(root),
            "status_after": None,
        },
        "commands": [],
        "files": {
            "before_inventory_path": "before-inventory.json",
            "after_inventory_path": None,
            "changed": [],
        },
        "risk": None,
        "reports": {},
    }


def save_manifest(root: Path, manifest: dict[str, Any], *, update_latest: bool = True) -> Path:
    sid = str(manifest.get("session_id"))
    path = session_manifest_path(root, sid)
    json_dump(path, manifest)
    if update_latest:
        json_dump(latest_manifest_path(root), manifest)
    return path


def load_manifest(root: Path, session_id: str | None = None, manifest_path: Path | None = None) -> dict[str, Any]:
    if manifest_path:
        if not manifest_path.exists():
            raise SessionError(f"Manifest not found: {manifest_path}")
        return json_load(manifest_path)
    if session_id:
        path = session_manifest_path(root, session_id)
        if not path.exists():
            raise SessionError(f"Session manifest not found: {session_id}")
        return json_load(path)
    path = latest_manifest_path(root)
    if not path.exists():
        raise SessionError("No latest manifest found. Run `afr start`, `afr stop`, or `afr analyze` first.")
    return json_load(path)


def active_session(root: Path) -> dict[str, Any] | None:
    path = active_session_path(root)
    if not path.exists():
        return None
    return json_load(path)


def set_active_session(root: Path, manifest: dict[str, Any]) -> None:
    json_dump(active_session_path(root), {"session_id": manifest["session_id"], "started_at": manifest["started_at"]})


def clear_active_session(root: Path) -> None:
    try:
        active_session_path(root).unlink()
    except FileNotFoundError:
        pass


def start_manual_session(root: Path, *, session_id: str | None = None, note: str | None = None) -> dict[str, Any]:
    config = ensure_project(root)
    if active_session(root):
        raise SessionError("A session is already active. Run `afr stop` first.")
    sid = session_id or stable_session_id()
    sdir = session_dir(root, sid)
    ensure_dir(sdir)
    manifest = base_manifest(root, sid, note=note, mode="manual")
    before = inventory(root, config)
    json_dump(sdir / "before-inventory.json", before)
    save_manifest(root, manifest, update_latest=True)
    set_active_session(root, manifest)
    return manifest


def stop_session(root: Path, *, session_id: str | None = None) -> dict[str, Any]:
    config = ensure_project(root)
    active = active_session(root)
    sid = session_id or (active or {}).get("session_id")
    if not sid:
        raise SessionError("No active session found. Run `afr start` first or pass --session-id.")
    manifest = load_manifest(root, str(sid))
    sdir = session_dir(root, str(sid))
    before_path = sdir / str(manifest.get("files", {}).get("before_inventory_path", "before-inventory.json"))
    before = json_load(before_path) if before_path.exists() else {}
    after = inventory(root, config)
    json_dump(sdir / "after-inventory.json", after)
    changes = compare_inventories(before, after)
    manifest["ended_at"] = iso_now()
    manifest["repository"]["status_after"] = status_porcelain(root)
    manifest["files"]["after_inventory_path"] = "after-inventory.json"
    manifest["files"]["changed"] = changes
    dt = diff_text(root, max_bytes=int(config.get("max_text_scan_bytes", 2_000_000)))
    manifest["risk"] = analyze_manifest(root, manifest, config, diff_text=dt)
    manifest["reports"]["markdown"] = "pr-report.md"
    markdown = render_markdown(manifest)
    (sdir / "pr-report.md").write_text(markdown, encoding="utf-8")
    latest_report_path(root).write_text(markdown, encoding="utf-8")
    save_manifest(root, manifest, update_latest=True)
    if active and active.get("session_id") == sid:
        clear_active_session(root)
    return manifest


def run_wrapped_session(
    root: Path,
    *,
    argv: list[str],
    session_id: str | None = None,
    note: str | None = None,
    capture_output: bool = True,
) -> dict[str, Any]:
    config = ensure_project(root)
    if active_session(root):
        raise SessionError("A session is already active. Run `afr stop` first or use `afr run -- ...` inside it.")
    sid = session_id or stable_session_id()
    sdir = session_dir(root, sid)
    ensure_dir(sdir)
    manifest = base_manifest(root, sid, note=note, mode="wrapped-command")
    before = inventory(root, config)
    json_dump(sdir / "before-inventory.json", before)
    save_manifest(root, manifest, update_latest=True)
    command_record = run_command(
        root=root,
        session_dir=sdir,
        argv=argv,
        capture_output=capture_output,
        redact_output=bool(config.get("redact_command_output", True)),
        max_output_bytes=int(config.get("max_command_output_bytes", 1_000_000)),
    )
    manifest["commands"].append(command_record)
    after = inventory(root, config)
    json_dump(sdir / "after-inventory.json", after)
    manifest["ended_at"] = iso_now()
    manifest["repository"]["status_after"] = status_porcelain(root)
    manifest["files"]["after_inventory_path"] = "after-inventory.json"
    manifest["files"]["changed"] = compare_inventories(before, after)
    dt = diff_text(root, max_bytes=int(config.get("max_text_scan_bytes", 2_000_000)))
    manifest["risk"] = analyze_manifest(root, manifest, config, diff_text=dt)
    manifest["reports"]["markdown"] = "pr-report.md"
    markdown = render_markdown(manifest)
    (sdir / "pr-report.md").write_text(markdown, encoding="utf-8")
    latest_report_path(root).write_text(markdown, encoding="utf-8")
    save_manifest(root, manifest, update_latest=True)
    return manifest


def run_command_in_active_session(root: Path, *, argv: list[str], capture_output: bool = True) -> dict[str, Any]:
    config = ensure_project(root)
    active = active_session(root)
    if not active:
        raise SessionError("No active session found. Run `afr start` first or use `afr start -- <command>`.")
    sid = str(active["session_id"])
    manifest = load_manifest(root, sid)
    sdir = session_dir(root, sid)
    record = run_command(
        root=root,
        session_dir=sdir,
        argv=argv,
        capture_output=capture_output,
        redact_output=bool(config.get("redact_command_output", True)),
        max_output_bytes=int(config.get("max_command_output_bytes", 1_000_000)),
    )
    manifest.setdefault("commands", []).append(record)
    save_manifest(root, manifest, update_latest=True)
    return manifest


def analyze_repository(root: Path, *, base_ref: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    config = ensure_project(root)
    sid = session_id or stable_session_id("afr-ci")
    sdir = session_dir(root, sid)
    ensure_dir(sdir)
    if base_ref is None:
        base_ref = os.environ.get("AFR_BASE_REF") or fallback_base_ref(root)
    manifest = base_manifest(root, sid, note=f"analysis against {base_ref or 'working tree'}", mode="analysis")
    manifest["analysis"] = {"base_ref": base_ref}
    changes = changed_files_from_git(root, base_ref=base_ref)
    changes = enrich_git_changes(root, changes, config)
    manifest["ended_at"] = iso_now()
    manifest["repository"]["status_after"] = status_porcelain(root)
    manifest["files"]["before_inventory_path"] = None
    manifest["files"]["after_inventory_path"] = None
    manifest["files"]["changed"] = changes
    dt = diff_text(root, base_ref=base_ref, max_bytes=int(config.get("max_text_scan_bytes", 2_000_000)))
    manifest["risk"] = analyze_manifest(root, manifest, config, diff_text=dt)
    manifest["reports"]["markdown"] = "pr-report.md"
    markdown = render_markdown(manifest)
    (sdir / "pr-report.md").write_text(markdown, encoding="utf-8")
    latest_report_path(root).write_text(markdown, encoding="utf-8")
    save_manifest(root, manifest, update_latest=True)
    return manifest


def session_status(root: Path) -> dict[str, Any]:
    active = active_session(root)
    latest_exists = latest_manifest_path(root).exists()
    return {
        "active": active,
        "latest_manifest": str(latest_manifest_path(root)) if latest_exists else None,
        "agent_flight_dir": str(afr_dir(root)),
    }
