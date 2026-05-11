from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from .process_recorder import command_looks_like_test
from .secrets import find_secrets_in_text
from .snapshot import path_matches_any
from .utils import clamp, read_text_lossy


SEVERITY_SCORE_FLOOR = {
    "info": 1,
    "low": 4,
    "medium": 8,
    "warning": 8,
    "high": 15,
    "critical": 25,
}


DESTRUCTIVE_PATTERNS = [
    ("sql-drop", re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA|COLUMN)\b", re.IGNORECASE), "Destructive SQL DROP detected"),
    ("sql-truncate", re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE), "SQL TRUNCATE detected"),
    ("sql-delete-without-where", re.compile(r"\bDELETE\s+FROM\s+\S+\s*(?:;|$)", re.IGNORECASE), "DELETE statement may be missing WHERE"),
    ("chmod-777", re.compile(r"\bchmod\s+777\b"), "World-writable chmod 777 detected"),
    ("shell-curl-pipe", re.compile(r"\b(curl|wget)\b[^\n|;]*\|\s*(sh|bash)\b"), "curl/wget piped directly to shell"),
    ("dangerous-rm", re.compile(r"\brm\s+-rf\s+(/|\$\{?\w+\}?|\*)"), "Dangerous rm -rf pattern detected"),
]


def finding(
    id: str,
    title: str,
    severity: str,
    score: int,
    evidence: list[str] | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "severity": severity,
        "score": max(score, SEVERITY_SCORE_FLOOR.get(severity, 1)),
        "evidence": evidence or [],
        "recommendation": recommendation or "Review manually before merge.",
    }


def risk_level(score: int, thresholds: dict[str, Any]) -> str:
    if score >= int(thresholds.get("critical", 80)):
        return "critical"
    if score >= int(thresholds.get("high", 51)):
        return "high"
    if score >= int(thresholds.get("medium", 21)):
        return "medium"
    return "low"


def severity_score_floor(findings: list[dict[str, Any]], thresholds: dict[str, Any]) -> int:
    floor = 0
    for item in findings:
        severity = str(item.get("severity", "info"))
        if severity == "critical":
            floor = max(floor, int(thresholds.get("critical", 80)))
        elif severity == "high":
            floor = max(floor, int(thresholds.get("high", 51)))
        elif severity in {"medium", "warning"}:
            floor = max(floor, int(thresholds.get("medium", 21)))
    return floor


def is_test_file(path: str, config: dict[str, Any]) -> bool:
    return path_matches_any(path, list(config.get("test_file_globs", [])))


def is_source_file(path: str, config: dict[str, Any]) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {str(ext).lower() for ext in config.get("source_extensions", [])}


def is_dependency_file(path: str, config: dict[str, Any]) -> bool:
    name = Path(path).name
    return name in set(config.get("dependency_files", []))


def matching_zone(path: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for zone in config.get("risk_zones", []):
        patterns = list(zone.get("patterns", []))
        if path_matches_any(path, patterns) or any(fnmatch.fnmatch(Path(path).name, p) for p in patterns):
            zones.append(zone)
    return zones


def added_diff_lines(diff_text: str) -> list[tuple[str | None, str]]:
    result: list[tuple[str | None, str]] = []
    current_path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current_path = path[2:] if path.startswith("b/") else path
            continue
        if line.startswith("+"):
            result.append((current_path, line[1:]))
    return result


def tests_ran_successfully(commands: list[dict[str, Any]], config: dict[str, Any]) -> bool:
    patterns = list(config.get("test_command_patterns", []))
    for command in commands:
        if command_looks_like_test(command, patterns) and int(command.get("exit_code") or 0) == 0:
            return True
    return False


def analyze_manifest(root: Path, manifest: dict[str, Any], config: dict[str, Any], diff_text: str = "") -> dict[str, Any]:
    changes = list(manifest.get("files", {}).get("changed", []))
    commands = list(manifest.get("commands", []))
    thresholds = dict(config.get("risk_thresholds", {}))
    findings: list[dict[str, Any]] = []

    changed_paths = [str(item.get("path", "")) for item in changes if item.get("path")]
    source_paths = [p for p in changed_paths if is_source_file(p, config)]
    test_paths = [p for p in changed_paths if is_test_file(p, config)]
    dependency_paths = [p for p in changed_paths if is_dependency_file(p, config)]
    binary_paths = [str(item.get("path", "")) for item in changes if item.get("binary")]

    if not changes:
        findings.append(finding("no-changes", "No repository changes were detected", "info", 1, [], "No action needed."))

    if len(changes) >= int(thresholds.get("very_large_file_count", 50)):
        findings.append(
            finding(
                "very-large-change-set",
                "Very large change set",
                "critical",
                28,
                [f"{len(changes)} files changed"],
                "Split the work or require a deeper human review before merging.",
            )
        )
    elif len(changes) >= int(thresholds.get("large_file_count", 20)):
        findings.append(
            finding(
                "large-change-set",
                "Large change set",
                "high",
                16,
                [f"{len(changes)} files changed"],
                "Review high-risk areas manually and confirm test coverage before merging.",
            )
        )

    total_bytes = sum(int(item.get("size") or 0) for item in changes)
    if total_bytes >= int(thresholds.get("large_total_bytes", 2_000_000)):
        findings.append(
            finding(
                "large-byte-change",
                "Large files or generated content changed",
                "medium",
                10,
                [f"Changed file sizes total approximately {total_bytes} bytes"],
                "Check whether generated or binary artifacts should be committed.",
            )
        )

    for path in binary_paths[:10]:
        findings.append(
            finding(
                "binary-file-change",
                "Binary file changed",
                "medium",
                8,
                [path],
                "Verify binary artifacts are expected and reproducible.",
            )
        )

    if dependency_paths:
        findings.append(
            finding(
                "dependency-file-changed",
                "Dependency manifest or lockfile changed",
                "high",
                15,
                dependency_paths[:12],
                "Review dependency provenance, license impact, lockfile changes, and vulnerability scan results.",
            )
        )

    zone_hits: dict[str, dict[str, Any]] = {}
    for path in changed_paths:
        for zone in matching_zone(path, config):
            zid = str(zone.get("id", "zone"))
            entry = zone_hits.setdefault(
                zid,
                {
                    "zone": zone,
                    "paths": [],
                },
            )
            entry["paths"].append(path)
    for zid, zone_hit in zone_hits.items():
        zone = zone_hit["zone"]
        paths = sorted(set(zone_hit["paths"]))[:12]
        findings.append(
            finding(
                f"risk-zone-{zid}",
                str(zone.get("title", "Sensitive code area changed")),
                str(zone.get("severity", "medium")),
                int(zone.get("score", 10)),
                paths,
                str(zone.get("recommendation", "Review this sensitive area manually.")),
            )
        )

    successful_tests = tests_ran_successfully(commands, config)
    if source_paths and not successful_tests:
        evidence = [f"{len(source_paths)} source files changed"]
        if commands:
            evidence.append("No successful test command detected in the recorded commands")
        else:
            evidence.append("No commands were recorded")
        findings.append(
            finding(
                "source-without-recorded-tests",
                "Source changed without a recorded successful test run",
                "high",
                22,
                evidence,
                "Run and record the relevant tests before merging.",
            )
        )

    if source_paths and not test_paths:
        findings.append(
            finding(
                "source-without-test-file-change",
                "Source changed without test files changing",
                "medium",
                8,
                source_paths[:12],
                "This may be fine, but verify existing tests cover the changed behavior.",
            )
        )

    failed_commands = [cmd for cmd in commands if cmd.get("exit_code") not in (0, None)]
    for cmd in failed_commands[:8]:
        findings.append(
            finding(
                "command-failed",
                "Recorded command failed",
                "high",
                15,
                [f"{cmd.get('command')} exited with {cmd.get('exit_code')}"] ,
                "Do not merge until failed commands are understood or resolved.",
            )
        )

    if not commands and changes:
        findings.append(
            finding(
                "no-command-log",
                "No command log was recorded",
                "medium",
                8,
                ["The manifest has repository changes but no recorded command execution"],
                "Run the coding agent or validation commands through `afr start -- ...` or `afr run -- ...`.",
            )
        )

    # Scan changed files for secrets. Deleted files are skipped.
    max_scan_bytes = int(config.get("max_text_scan_bytes", 2_000_000))
    secret_evidence: list[str] = []
    for path in changed_paths:
        full_path = root / path
        if not full_path.exists() or not full_path.is_file() or full_path.is_symlink():
            continue
        if any(str(item.get("path")) == path and item.get("binary") for item in changes):
            continue
        try:
            text = read_text_lossy(full_path, max_bytes=max_scan_bytes)
        except OSError:
            continue
        secrets = find_secrets_in_text(text, max_findings=5)
        for secret in secrets:
            secret_evidence.append(f"{path}:{secret['line']} {secret['title']} {secret['preview']}")
    if secret_evidence:
        findings.append(
            finding(
                "possible-secret-leak",
                "Possible secret material detected in changed files",
                "critical",
                80,
                secret_evidence[:15],
                "Remove the secret, rotate it if it was real, and add a regression check.",
            )
        )

    diff_lines = added_diff_lines(diff_text)
    added_paths = [
        str(item.get("path", ""))
        for item in changes
        if item.get("status") == "A" and item.get("path") and not item.get("binary")
    ]
    for path in added_paths:
        full_path = root / path
        if not full_path.exists() or not full_path.is_file() or full_path.is_symlink():
            continue
        try:
            text = read_text_lossy(full_path, max_bytes=max_scan_bytes)
        except OSError:
            continue
        for line in text.splitlines():
            diff_lines.append((path, line))
    destructive_hits: list[str] = []
    for diff_path, line in diff_lines:
        for pid, pattern, title in DESTRUCTIVE_PATTERNS:
            if pattern.search(line):
                snippet = line.strip()
                if len(snippet) > 160:
                    snippet = snippet[:157] + "..."
                location = f"{diff_path}: " if diff_path else ""
                dangerous_hit = f"{location}{title}: `{snippet}`"
                if dangerous_hit not in destructive_hits:
                    destructive_hits.append(dangerous_hit)
    if destructive_hits:
        findings.append(
            finding(
                "dangerous-added-lines",
                "Dangerous-looking added lines detected",
                "critical",
                28,
                destructive_hits[:12],
                "Review these lines manually; require tests and rollback plan where relevant.",
            )
        )

    # Deduplicate by id+evidence to avoid duplicate status/git snapshot findings.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in findings:
        key = (str(item["id"]), tuple(str(x) for x in item.get("evidence", [])))
        if key not in seen:
            deduped.append(item)
            seen.add(key)

    raw_score = sum(int(item.get("score") or 0) for item in deduped)
    score = clamp(max(raw_score, severity_score_floor(deduped, thresholds)), 0, 100)
    return {
        "score": score,
        "raw_score": raw_score,
        "level": risk_level(score, thresholds),
        "findings": deduped,
        "summary": {
            "changed_files": len(changes),
            "source_files": len(source_paths),
            "test_files": len(test_paths),
            "dependency_files": len(dependency_paths),
            "commands": len(commands),
            "successful_tests_recorded": successful_tests,
        },
    }
