from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent_flight_recorder.config import load_config
from agent_flight_recorder.exceptions import ConfigError
from agent_flight_recorder.report import render_markdown
from agent_flight_recorder.secrets import find_secrets_in_text, redact_text


ROOT = Path(__file__).resolve().parents[1]
AFR = ROOT / "afr.py"


def run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(f"Command failed: {cmd}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def git(cwd: Path, *args: str) -> None:
    run(["git", *args], cwd)


class SecurityAndVerifyTests(unittest.TestCase):
    def test_redaction_masks_secret_values(self) -> None:
        text = "token = 'abcd1234abcd1234abcd1234'"
        redacted = redact_text(text)
        self.assertNotIn("abcd1234abcd1234abcd1234", redacted)
        self.assertTrue(find_secrets_in_text(text))

    def test_report_sanitizes_markdown_and_has_no_tool_footer(self) -> None:
        manifest = {
            "session_id": "session-1",
            "mode": "analysis",
            "note": "line one\nline `two`",
            "started_at": "2026-05-10T00:00:00+00:00",
            "ended_at": "2026-05-10T00:01:00+00:00",
            "repository": {"branch": "main", "head": "abc"},
            "commands": [{"command": "python -c `x`", "exit_code": 0, "started_at": "a", "ended_at": "b", "capture_output": False}],
            "files": {"changed": [{"path": "src/`bad`.py", "status": "M", "size": 1}]},
            "risk": {
                "score": 0,
                "level": "low",
                "findings": [],
                "summary": {"changed_files": 1, "source_files": 1, "test_files": 0, "dependency_files": 0, "commands": 1},
            },
        }
        report = render_markdown(manifest)
        self.assertIn("line one\\nline 'two'", report)
        self.assertIn("`python -c 'x'`", report)
        self.assertNotIn("tool footer", report.lower())

    def test_doctor_does_not_create_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.com")
            git(repo, "config", "user.name", "Test User")
            (repo / "app.py").write_text("print(1)\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "initial")
            proc = run([sys.executable, str(AFR), "doctor", "--json"], repo)
            data = json.loads(proc.stdout)
            self.assertFalse(data["config_exists"])
            self.assertFalse((repo / ".agent-flight" / "config.json").exists())

    def test_invalid_config_reports_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "max_text_scan_bytes": 0,
                        "risk_zones": [
                            {
                                "id": "broken",
                                "patterns": "not-a-list",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "max_text_scan_bytes"):
                load_config(config_path)

    def test_invalid_risk_zone_patterns_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "risk_zones": [
                            {
                                "id": "broken",
                                "severity": "high",
                                "score": 10,
                                "patterns": "not-a-list",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "risk_zones\\[0\\]\\.patterns"):
                load_config(config_path)

    def test_invalid_risk_zone_severity_type_is_rejected_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "risk_zones": [
                            {
                                "id": "broken",
                                "severity": ["high"],
                                "score": 10,
                                "patterns": ["**/auth/**"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "risk_zones\\[0\\]\\.severity"):
                load_config(config_path)

    def test_verify_fails_when_threshold_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.com")
            git(repo, "config", "user.name", "Test User")
            (repo / "app.py").write_text("print(1)\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "initial")
            run([sys.executable, str(AFR), "init"], repo)
            (repo / "secrets.py").write_text("EXAMPLE_API_KEY='abcd1234abcd1234abcd1234'\n", encoding="utf-8")
            run([sys.executable, str(AFR), "analyze", "--base-ref", "HEAD"], repo)
            proc = run([sys.executable, str(AFR), "verify", "--max-score", "50"], repo, check=False)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("verification failed", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
