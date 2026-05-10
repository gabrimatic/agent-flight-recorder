from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable


UTC = _dt.timezone.utc


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=UTC)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def parse_iso(value: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def json_dump(path: Path, value: Any) -> None:
    ensure_dir(path.parent)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def json_load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_text_lossy(path: Path, max_bytes: int = 2_000_000) -> str:
    with path.open("rb") as handle:
        data = handle.read(max_bytes)
    return data.decode("utf-8", errors="replace")


def sha256_file(path: Path, max_bytes: int) -> tuple[str | None, bool]:
    """Return (hex_digest, truncated).

    Large files are intentionally not fully hashed by default because the CLI is
    expected to run inside huge repositories. For files above max_bytes, we hash
    the first max_bytes and mark the result as truncated.
    """
    h = hashlib.sha256()
    total = 0
    truncated = False
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            if total + len(chunk) > max_bytes:
                remaining = max_bytes - total
                if remaining > 0:
                    h.update(chunk[:remaining])
                    total += remaining
                truncated = True
                break
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), truncated


def is_binary_file(path: Path, sample_size: int = 8192) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(sample_size)
    except OSError:
        return False
    if b"\0" in sample:
        return True
    if not sample:
        return False
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(32, 127)))
    non_text = sample.translate(None, text_chars)
    return len(non_text) / max(1, len(sample)) > 0.30


def relpath(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def normalize_command(command: Iterable[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def shell_quote(value: str) -> str:
    if not value:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def plural(count: int, singular: str, plural_value: str | None = None) -> str:
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural_value or singular + 's'}"


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def stable_session_id(prefix: str = "afr") -> str:
    now = utc_now().strftime("%Y%m%d-%H%M%S")
    random_part = hashlib.sha256(os.urandom(16)).hexdigest()[:8]
    return f"{prefix}-{now}-{random_part}"
