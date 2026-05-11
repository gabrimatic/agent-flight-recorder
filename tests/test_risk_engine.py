from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_flight_recorder.config import default_config
from agent_flight_recorder.risk import analyze_manifest


class RiskEngineTests(unittest.TestCase):
    def test_secret_detection_is_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.py").write_text("EXAMPLE_API_KEY='abcd1234abcd1234abcd1234'\n", encoding="utf-8")
            manifest = {
                "commands": [],
                "files": {"changed": [{"path": "config.py", "status": "M", "size": 64, "binary": False}]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            self.assertEqual(risk["level"], "critical")
            self.assertTrue(any(item["id"] == "possible-secret-leak" for item in risk["findings"]))

    def test_auth_change_without_tests_is_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "auth_service.py").write_text("def login(): return True\n", encoding="utf-8")
            manifest = {
                "commands": [{"command": "python -m compileall .", "argv": ["python", "-m", "compileall", "."], "exit_code": 0}],
                "files": {"changed": [{"path": "auth_service.py", "status": "M", "size": 24, "binary": False}]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            self.assertIn(risk["level"], {"high", "critical"})
            ids = {item["id"] for item in risk["findings"]}
            self.assertIn("risk-zone-auth", ids)
            self.assertIn("source-without-recorded-tests", ids)

    def test_successful_test_command_reduces_missing_test_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print('x')\n", encoding="utf-8")
            manifest = {
                "commands": [{"command": "python -m unittest", "argv": ["python", "-m", "unittest"], "exit_code": 0}],
                "files": {"changed": [
                    {"path": "app.py", "status": "M", "size": 11, "binary": False},
                    {"path": "tests/test_app.py", "status": "M", "size": 11, "binary": False},
                ]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            ids = {item["id"] for item in risk["findings"]}
            self.assertNotIn("source-without-recorded-tests", ids)

    def test_make_test_counts_as_successful_test_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print('x')\n", encoding="utf-8")
            manifest = {
                "commands": [{"command": "make test", "argv": ["make", "test"], "exit_code": 0}],
                "files": {"changed": [{"path": "app.py", "status": "M", "size": 11, "binary": False}]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            ids = {item["id"] for item in risk["findings"]}
            self.assertNotIn("source-without-recorded-tests", ids)

    def test_make_test_with_directory_option_counts_as_successful_test_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print('x')\n", encoding="utf-8")
            manifest = {
                "commands": [{"command": "make -C app test", "argv": ["make", "-C", "app", "test"], "exit_code": 0}],
                "files": {"changed": [{"path": "app.py", "status": "M", "size": 11, "binary": False}]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            ids = {item["id"] for item in risk["findings"]}
            self.assertNotIn("source-without-recorded-tests", ids)

    def test_make_build_does_not_count_as_successful_test_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print('x')\n", encoding="utf-8")
            manifest = {
                "commands": [{"command": "make build", "argv": ["make", "build"], "exit_code": 0}],
                "files": {"changed": [{"path": "app.py", "status": "M", "size": 11, "binary": False}]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            ids = {item["id"] for item in risk["findings"]}
            self.assertIn("source-without-recorded-tests", ids)

    def test_failed_command_sets_high_risk_even_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {
                "commands": [{"command": "agent run", "argv": ["agent", "run"], "exit_code": 1}],
                "files": {"changed": []},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            ids = {item["id"] for item in risk["findings"]}
            self.assertIn("command-failed", ids)
            self.assertEqual(risk["level"], "high")
            self.assertGreaterEqual(risk["score"], 51)

    def test_medium_severity_finding_sets_medium_risk_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "blob.bin").write_bytes(b"\0binary")
            manifest = {
                "commands": [],
                "files": {"changed": [{"path": "blob.bin", "status": "A", "size": 7, "binary": True}]},
            }
            risk = analyze_manifest(root, manifest, default_config(), diff_text="")
            ids = {item["id"] for item in risk["findings"]}
            self.assertIn("binary-file-change", ids)
            self.assertEqual(risk["level"], "medium")
            self.assertGreaterEqual(risk["score"], 21)


if __name__ == "__main__":
    unittest.main()
