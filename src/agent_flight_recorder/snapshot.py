from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from .utils import is_binary_file, relpath, sha256_file


def path_matches_any(rel: str, patterns: list[str]) -> bool:
    rel = rel.replace(os.sep, "/")
    for pattern in patterns:
        pattern = pattern.replace(os.sep, "/")
        if fnmatch.fnmatch(rel, pattern):
            return True
        if pattern.endswith("/**") and rel == pattern[:-3]:
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(Path(rel).name, pattern[3:]):
            return True
        if "/" not in pattern and fnmatch.fnmatch(Path(rel).name, pattern):
            return True
    return False


def should_exclude(rel: str, config: dict[str, Any]) -> bool:
    return path_matches_any(rel, list(config.get("exclude_globs", [])))


def inventory(root: Path, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    max_hash_bytes = int(config.get("max_hash_bytes", 10_485_760))
    result: dict[str, dict[str, Any]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        filtered_dirs: list[str] = []
        for dirname in dirnames:
            child = current / dirname
            child_rel = relpath(root, child)
            if should_exclude(child_rel + "/", config) or should_exclude(child_rel, config):
                continue
            filtered_dirs.append(dirname)
        dirnames[:] = filtered_dirs
        for filename in filenames:
            path = current / filename
            try:
                file_rel = relpath(root, path)
            except ValueError:
                continue
            if should_exclude(file_rel, config):
                continue
            try:
                stat = path.lstat()
            except OSError:
                continue
            item: dict[str, Any] = {
                "path": file_rel,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "mode": stat.st_mode,
            }
            if path.is_symlink():
                item["type"] = "symlink"
                try:
                    item["target"] = os.readlink(path)
                except OSError:
                    item["target"] = ""
            elif path.is_file():
                item["type"] = "file"
                item["binary"] = is_binary_file(path)
                try:
                    digest, truncated = sha256_file(path, max_hash_bytes)
                    item["sha256"] = digest
                    item["hash_truncated"] = truncated
                except OSError:
                    item["sha256"] = None
                    item["hash_truncated"] = True
            else:
                item["type"] = "special"
            result[file_rel] = item
    return result


def compare_inventories(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def change_record(path: str, status: str, item: dict[str, Any]) -> dict[str, Any]:
        record = {"path": path, "status": status, "size": item.get("size", 0), "binary": item.get("binary", False)}
        if item.get("hash_truncated"):
            record["hash_truncated"] = True
        return record

    def signature(item: dict[str, Any]) -> tuple[Any, ...]:
        parts: list[Any] = [item.get("sha256"), item.get("size"), item.get("target"), item.get("type"), item.get("mode")]
        if item.get("hash_truncated"):
            parts.append(item.get("mtime_ns"))
        return tuple(parts)

    paths = sorted(set(before) | set(after))
    changes: list[dict[str, Any]] = []
    for path in paths:
        b = before.get(path)
        a = after.get(path)
        if b is None and a is not None:
            changes.append(change_record(path, "A", a))
        elif b is not None and a is None:
            changes.append(change_record(path, "D", b))
        elif b is not None and a is not None:
            if signature(b) != signature(a):
                changes.append(change_record(path, "M", a))
    return changes


def enrich_git_changes(root: Path, changes: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for change in changes:
        path = change.get("path", "")
        if not isinstance(path, str) or not path:
            continue
        if should_exclude(path, config):
            continue
        full_path = root / path
        item = dict(change)
        if full_path.exists() and full_path.is_file() and not full_path.is_symlink():
            try:
                item["size"] = full_path.stat().st_size
                item["binary"] = is_binary_file(full_path)
            except OSError:
                pass
        enriched.append(item)
    return sorted(enriched, key=lambda x: str(x.get("path", "")))
