from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretPattern:
    id: str
    title: str
    regex: re.Pattern[str]


SECRET_PATTERNS: list[SecretPattern] = [
    SecretPattern("aws-access-key", "AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    SecretPattern("github-token", "GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    SecretPattern("sk-api-key", "sk-style API key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    SecretPattern("slack-token", "Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{20,}\b")),
    SecretPattern("private-key", "Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    SecretPattern(
        "jwt",
        "JWT-like token",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ),
    SecretPattern(
        "db-url-password",
        "Database URL containing a password",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb|redis)://[^\s/:]+:[^\s@]+@[^\s]+", re.IGNORECASE),
    ),
    SecretPattern(
        "generic-secret-assignment",
        "Generic secret assignment",
        re.compile(
            r"(?i)\b[A-Za-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|pwd|client[_-]?secret)\b\s*[:=]\s*[\"']?([A-Za-z0-9_./+=\-]{16,})"
        ),
    ),
]


def mask(value: str) -> str:
    if len(value) <= 8:
        return "[REDACTED]"
    return value[:4] + "..." + value[-4:]


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.regex.sub(lambda match: mask(match.group(0)), redacted)
    return redacted


def find_secrets_in_text(text: str, *, max_findings: int = 50) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    lines = text.splitlines()
    for line_no, line in enumerate(lines, start=1):
        for pattern in SECRET_PATTERNS:
            for match in pattern.regex.finditer(line):
                findings.append(
                    {
                        "kind": pattern.id,
                        "title": pattern.title,
                        "line": line_no,
                        "preview": mask(match.group(0)),
                    }
                )
                if len(findings) >= max_findings:
                    return findings
    return findings
