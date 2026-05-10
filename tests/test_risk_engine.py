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


if __name__ == "__main__":
    unittest.main()
