from __future__ import annotations

from typing import Any

from .utils import plural


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4}


def _clean_text(value: object) -> str:
    text = str(value)
    return text.replace("\r", "\\r").replace("\n", "\\n").replace("`", "'")


def _inline_code(value: object) -> str:
    return f"`{_clean_text(value)}`"


def _risk_badge(level: str, score: int) -> str:
    return f"{level.upper()} ({score}/100)"


def render_markdown(manifest: dict[str, Any]) -> str:
    risk = manifest.get("risk") or {}
    summary = risk.get("summary") or {}
    repo = manifest.get("repository") or {}
    findings = sorted(risk.get("findings") or [], key=lambda x: (SEVERITY_ORDER.get(str(x.get("severity")), 9), -int(x.get("score") or 0)))
    commands = manifest.get("commands") or []
    changes = (manifest.get("files") or {}).get("changed") or []

    lines: list[str] = []
    lines.append("# Agent Flight Report")
    lines.append("")
    lines.append(f"**Risk:** {_risk_badge(str(risk.get('level', 'unknown')), int(risk.get('score') or 0))}")
    lines.append(f"**Session:** `{manifest.get('session_id', 'unknown')}`")
    lines.append(f"**Mode:** `{manifest.get('mode', 'unknown')}`")
    if manifest.get("note"):
        lines.append(f"**Note:** {_clean_text(manifest.get('note'))}")
    lines.append(f"**Started:** {manifest.get('started_at')}")
    lines.append(f"**Ended:** {manifest.get('ended_at') or 'not ended'}")
    lines.append("")

    lines.append("## Repository")
    lines.append("")
    lines.append(f"- Branch: `{repo.get('branch', 'unknown')}`")
    lines.append(f"- Head: `{repo.get('head', '') or 'unborn/unknown'}`")
    if manifest.get("analysis", {}).get("base_ref"):
        lines.append(f"- Analysis base ref: `{manifest['analysis']['base_ref']}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- {plural(int(summary.get('changed_files') or len(changes)), 'file')} changed")
    lines.append(f"- {plural(int(summary.get('source_files') or 0), 'source file')} changed")
    lines.append(f"- {plural(int(summary.get('test_files') or 0), 'test file')} changed")
    lines.append(f"- {plural(int(summary.get('dependency_files') or 0), 'dependency file')} changed")
    lines.append(f"- {plural(int(summary.get('commands') or len(commands)), 'command')} recorded")
    lines.append(f"- Successful test command recorded: `{bool(summary.get('successful_tests_recorded'))}`")
    lines.append("")

    lines.append("## Risk findings")
    lines.append("")
    if findings:
        for item in findings:
            severity = str(item.get("severity", "info")).upper()
            lines.append(f"### {severity}: {_clean_text(item.get('title', 'Finding'))}")
            lines.append("")
            lines.append(f"- Rule: `{item.get('id', 'unknown')}`")
            lines.append(f"- Score impact: `{item.get('score', 0)}`")
            evidence = item.get("evidence") or []
            if evidence:
                lines.append("- Evidence:")
                for ev in evidence[:20]:
                    lines.append(f"  - {_inline_code(ev)}")
            lines.append(f"- Recommendation: {_clean_text(item.get('recommendation', 'Review manually.'))}")
            lines.append("")
    else:
        lines.append("No risk findings were produced.")
        lines.append("")

    lines.append("## Recorded commands")
    lines.append("")
    if commands:
        for command in commands:
            lines.append(f"- {_inline_code(command.get('command', ''))}")
            lines.append(f"  - Exit code: `{command.get('exit_code')}`")
            lines.append(f"  - Started: {command.get('started_at')}")
            lines.append(f"  - Ended: {command.get('ended_at')}")
            if command.get("capture_output"):
                lines.append(f"  - Stdout: `{command.get('stdout_path')}`")
                lines.append(f"  - Stderr: `{command.get('stderr_path')}`")
    else:
        lines.append("No commands were recorded.")
    lines.append("")

    lines.append("## Changed files")
    lines.append("")
    if changes:
        for item in changes[:200]:
            status = item.get("status", "?")
            path = item.get("path", "")
            size = item.get("size")
            binary = " binary" if item.get("binary") else ""
            size_part = f", {size} bytes" if size is not None else ""
            lines.append(f"- `{status}` {_inline_code(path)}{size_part}{binary}")
        if len(changes) > 200:
            lines.append(f"- ... {len(changes) - 200} more files omitted from markdown report")
    else:
        lines.append("No changed files detected.")
    lines.append("")

    lines.append("## Suggested merge gate")
    lines.append("")
    level = str(risk.get("level", "low"))
    if level in {"critical", "high"}:
        lines.append("Do not merge until the high-risk findings are explained, tests are recorded, and a human reviewer signs off.")
    elif level == "medium":
        lines.append("Review findings and confirm the change is covered by tests or an explicit manual check.")
    else:
        lines.append("No blocking risk was detected. This does not replace human review.")
    return "\n".join(lines) + "\n"
