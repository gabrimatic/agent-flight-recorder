from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .exceptions import ConfigError
from .utils import json_dump, json_load


VALID_SEVERITIES = {"info", "low", "medium", "warning", "high", "critical"}


DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": "1.0",
    "max_hash_bytes": 10_485_760,
    "max_text_scan_bytes": 2_000_000,
    "redact_command_output": True,
    "exclude_globs": [
        ".git/**",
        ".agent-flight/**",
        "node_modules/**",
        ".dart_tool/**",
        ".gradle/**",
        ".idea/**",
        ".vscode/**",
        ".venv/**",
        "venv/**",
        "env/**",
        "build/**",
        "dist/**",
        "target/**",
        "coverage/**",
        ".next/**",
        ".nuxt/**",
        ".turbo/**",
        ".pytest_cache/**",
        "__pycache__/**",
        "*.pyc",
        "*.pyo",
        "*.log",
    ],
    "test_command_patterns": [
        "pytest",
        "unittest",
        "python -m test",
        "npm test",
        "yarn test",
        "pnpm test",
        "bun test",
        "go test",
        "cargo test",
        "flutter test",
        "dart test",
        "make test",
        "make check",
        "just test",
        "task test",
        "tox",
        "nox",
        "mvn test",
        "gradle test",
        "./gradlew test",
        "xcodebuild test",
        "swift test",
        "dotnet test",
        "composer test",
        "rspec",
    ],
    "test_file_globs": [
        "test/**",
        "tests/**",
        "spec/**",
        "**/test/**",
        "**/tests/**",
        "**/spec/**",
        "**/*.test.*",
        "**/*.spec.*",
        "**/*_test.*",
        "**/*Test.*",
        "**/*Tests.*",
    ],
    "source_extensions": [
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".dart",
        ".go",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".kts",
        ".m",
        ".mm",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".sh",
        ".sql",
        ".swift",
        ".ts",
        ".tsx",
    ],
    "dependency_files": [
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "poetry.lock",
        "Pipfile",
        "Pipfile.lock",
        "pubspec.yaml",
        "pubspec.lock",
        "go.mod",
        "go.sum",
        "Cargo.toml",
        "Cargo.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Gemfile",
        "Gemfile.lock",
        "composer.json",
        "composer.lock",
        "Package.swift",
    ],
    "risk_thresholds": {
        "medium": 21,
        "high": 51,
        "critical": 80,
        "large_file_count": 20,
        "very_large_file_count": 50,
        "large_total_bytes": 2_000_000,
    },
    "risk_zones": [
        {
            "id": "auth",
            "title": "Authentication or authorization code changed",
            "severity": "high",
            "score": 22,
            "patterns": [
                "**/auth/**",
                "**/*auth*",
                "**/*login*",
                "**/*logout*",
                "**/*session*",
                "**/*jwt*",
                "**/*oauth*",
                "**/*permission*",
                "**/*rbac*",
                "**/*acl*",
                "**/*policy*",
            ],
            "recommendation": "Require focused auth tests and a human review of access-control behavior.",
        },
        {
            "id": "payments",
            "title": "Payment, billing, or subscription code changed",
            "severity": "high",
            "score": 22,
            "patterns": [
                "**/billing/**",
                "**/payments/**",
                "**/*billing*",
                "**/*payment*",
                "**/*stripe*",
                "**/*paypal*",
                "**/*checkout*",
                "**/*invoice*",
                "**/*subscription*",
                "**/*pricing*",
            ],
            "recommendation": "Verify idempotency, retry behavior, webhook signatures, invoice math, and refund paths.",
        },
        {
            "id": "database",
            "title": "Database schema or migration changed",
            "severity": "high",
            "score": 20,
            "patterns": [
                "**/migrations/**",
                "**/migration/**",
                "**/db/migrate/**",
                "**/*migration*",
                "**/schema.sql",
                "**/schema.prisma",
                "**/alembic/**",
                "**/liquibase/**",
            ],
            "recommendation": "Run migration, rollback, and data-preservation tests before merging.",
        },
        {
            "id": "crypto-secrets",
            "title": "Cryptography, secret, or key-management code changed",
            "severity": "high",
            "score": 22,
            "patterns": [
                "**/crypto/**",
                "**/*crypto*",
                "**/*encrypt*",
                "**/*decrypt*",
                "**/*cipher*",
                "**/*secret*",
                "**/*token*",
                "**/*keychain*",
                "**/*keystore*",
                "**/*vault*",
            ],
            "recommendation": "Require security review and avoid changing cryptographic behavior without tests.",
        },
        {
            "id": "infrastructure",
            "title": "Infrastructure, deployment, or CI configuration changed",
            "severity": "medium",
            "score": 10,
            "patterns": [
                "Dockerfile",
                "**/Dockerfile",
                "docker-compose*.yml",
                "docker-compose*.yaml",
                ".github/workflows/**",
                ".gitlab-ci.yml",
                "**/*.tf",
                "**/terraform/**",
                "**/k8s/**",
                "**/kubernetes/**",
                "**/*.yaml",
                "**/*.yml",
            ],
            "recommendation": "Review deployment, permissions, environment variables, and CI secret exposure.",
        },
    ],
}


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> dict[str, Any]:
    config = default_config()
    if not path.exists():
        return config
    loaded = json_load(path)
    if not isinstance(loaded, dict):
        raise ConfigError(f"Config file is not a JSON object: {path}")
    merged = merge_config(config, loaded)
    validate_config(merged)
    return merged


def write_default_config(path: Path, force: bool = False) -> None:
    if path.exists() and not force:
        raise ConfigError(f"Config already exists: {path}")
    json_dump(path, default_config())


def _require_int(config: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Config key must be an integer: {key}")
    if value < minimum:
        raise ConfigError(f"Config key must be >= {minimum}: {key}")
    return value


def _require_string_list(config: dict[str, Any], key: str) -> None:
    value = config.get(key)
    if not isinstance(value, list):
        raise ConfigError(f"Config key must be a list: {key}")
    if not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"Config list must contain non-empty strings: {key}")


def validate_config(config: dict[str, Any]) -> None:
    required_string_lists = [
        "exclude_globs",
        "test_command_patterns",
        "test_file_globs",
        "source_extensions",
        "dependency_files",
    ]
    for key in required_string_lists:
        _require_string_list(config, key)
    if not isinstance(config.get("risk_thresholds"), dict):
        raise ConfigError("Config key must be an object: risk_thresholds")
    _require_int(config, "max_hash_bytes", minimum=1)
    _require_int(config, "max_text_scan_bytes", minimum=1)
    for key, value in config["risk_thresholds"].items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigError(f"Risk threshold must be a non-negative integer: {key}")
    zones = config.get("risk_zones")
    if not isinstance(zones, list):
        raise ConfigError("Config key must be a list: risk_zones")
    for index, zone in enumerate(zones):
        if not isinstance(zone, dict):
            raise ConfigError(f"Risk zone must be an object: risk_zones[{index}]")
        zid = zone.get("id")
        if not isinstance(zid, str) or not zid:
            raise ConfigError(f"Risk zone id must be a non-empty string: risk_zones[{index}].id")
        title = zone.get("title")
        if title is not None and not isinstance(title, str):
            raise ConfigError(f"Risk zone title must be a string: risk_zones[{index}].title")
        severity = zone.get("severity", "medium")
        if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
            raise ConfigError(f"Risk zone severity is invalid: risk_zones[{index}].severity")
        score = zone.get("score", 10)
        if isinstance(score, bool) or not isinstance(score, int) or score < 0:
            raise ConfigError(f"Risk zone score must be a non-negative integer: risk_zones[{index}].score")
        patterns = zone.get("patterns")
        if not isinstance(patterns, list) or not all(isinstance(item, str) and item for item in patterns):
            raise ConfigError(f"Risk zone patterns must contain non-empty strings: risk_zones[{index}].patterns")
        recommendation = zone.get("recommendation")
        if recommendation is not None and not isinstance(recommendation, str):
            raise ConfigError(f"Risk zone recommendation must be a string: risk_zones[{index}].recommendation")
