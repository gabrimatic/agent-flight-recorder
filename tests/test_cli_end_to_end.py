from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


class CliEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test User")
        (self.repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "initial")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_wrapped_command_creates_manifest_and_report(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        script = "from pathlib import Path; Path('auth_service.py').write_text('def login(): return True\\n')"
        proc = run([sys.executable, str(AFR), "start", "--capture-output", "--", sys.executable, "-c", script], self.repo, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest_path = self.repo / ".agent-flight" / "manifest.json"
        report_path = self.repo / ".agent-flight" / "pr-report.md"
        self.assertTrue(manifest_path.exists())
        self.assertTrue(report_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["commands"]), 1)
        self.assertTrue(any(item["path"] == "auth_service.py" for item in manifest["files"]["changed"]))
        self.assertIn("Risk:", report_path.read_text(encoding="utf-8"))

    def test_manual_session_run_stop(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        run([sys.executable, str(AFR), "start", "--session-id", "manual-test"], self.repo)
        script = "from pathlib import Path; Path('tests').mkdir(exist_ok=True); Path('tests/test_app.py').write_text('import unittest\\n')"
        run([sys.executable, str(AFR), "run", "--", sys.executable, "-c", script], self.repo)
        run([sys.executable, str(AFR), "stop"], self.repo)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["session_id"], "manual-test")
        self.assertIsNotNone(manifest["ended_at"])

    def test_session_id_cannot_escape_sessions_directory(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        proc = run([sys.executable, str(AFR), "start", "--session-id", "../../escaped"], self.repo, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Invalid session id", proc.stderr)
        self.assertFalse((self.repo / "escaped").exists())

    def test_manual_session_keeps_distinct_command_logs(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        run([sys.executable, str(AFR), "start", "--session-id", "multi-command"], self.repo)
        run([sys.executable, str(AFR), "run", "--", sys.executable, "-c", "print('one')"], self.repo)
        run([sys.executable, str(AFR), "run", "--", sys.executable, "-c", "print('two')"], self.repo)
        run([sys.executable, str(AFR), "stop"], self.repo)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        command_ids = [item["id"] for item in manifest["commands"]]
        self.assertEqual(command_ids, ["cmd-0001", "cmd-0002"])
        stdout_paths = [self.repo / ".agent-flight" / "sessions" / "multi-command" / item["stdout_path"] for item in manifest["commands"]]
        self.assertEqual(stdout_paths[0].read_text(encoding="utf-8").strip(), "one")
        self.assertEqual(stdout_paths[1].read_text(encoding="utf-8").strip(), "two")

    def test_missing_wrapped_command_writes_manifest(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        proc = run([sys.executable, str(AFR), "start", "--", "afr-definitely-missing-command"], self.repo, check=False)
        self.assertEqual(proc.returncode, 127)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["commands"][0]["exit_code"], 127)
        stderr_path = self.repo / ".agent-flight" / "sessions" / manifest["session_id"] / manifest["commands"][0]["stderr_path"]
        self.assertIn("command not found", stderr_path.read_text(encoding="utf-8"))

    def test_command_metadata_redacts_secret_arguments(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        secret = "sk" + "-" + ("a" * 30)
        proc = run(
            [
                sys.executable,
                str(AFR),
                "start",
                "--",
                sys.executable,
                "-c",
                "print('ok')",
                "--api-key",
                secret,
            ],
            self.repo,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        manifest_text = json.dumps(manifest)
        self.assertNotIn(secret, manifest_text)
        self.assertIn("[REDACTED]", manifest_text)
        self.assertIn("--api-key", manifest["commands"][0]["argv"])

    def test_captured_output_is_bounded_and_marked_when_truncated(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        config_path = self.repo / ".agent-flight" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["max_command_output_bytes"] = 32
        config_path.write_text(json.dumps(config), encoding="utf-8")
        script = "import sys; sys.stdout.write('x' * 100); sys.stderr.write('y' * 100)"
        proc = run([sys.executable, str(AFR), "start", "--", sys.executable, "-c", script], self.repo, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        command = manifest["commands"][0]
        self.assertTrue(command["stdout_truncated"])
        self.assertTrue(command["stderr_truncated"])
        session_dir = self.repo / ".agent-flight" / "sessions" / manifest["session_id"]
        stdout = (session_dir / command["stdout_path"]).read_text(encoding="utf-8")
        stderr = (session_dir / command["stderr_path"]).read_text(encoding="utf-8")
        self.assertIn("[afr: stdout truncated after 32 bytes]", stdout)
        self.assertIn("[afr: stderr truncated after 32 bytes]", stderr)
        self.assertNotIn("x" * 40, stdout)
        self.assertNotIn("y" * 40, stderr)

    def test_analyze_and_verify(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        (self.repo / "package.json").write_text('{"dependencies":{"left-pad":"1.3.0"}}\n', encoding="utf-8")
        proc = run([sys.executable, str(AFR), "analyze", "--base-ref", "HEAD"], self.repo, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verify = run([sys.executable, str(AFR), "verify", "--max-score", "100"], self.repo, check=False)
        self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_analyze_invalid_base_ref_fails_instead_of_falling_back(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        proc = run([sys.executable, str(AFR), "analyze", "--base-ref", "missing/ref"], self.repo, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Unable to diff against base ref missing/ref", proc.stderr)

    def test_analyze_json_output_labels_json_as_output(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        output_path = self.repo / "manifest-out.json"
        proc = run([sys.executable, str(AFR), "analyze", "--base-ref", "HEAD", "--json", "--output", str(output_path)], self.repo)
        self.assertTrue(output_path.exists())
        data = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(data["mode"], "analysis")
        self.assertIn(f"Output: {output_path}", proc.stdout)
        self.assertIn("Report:", proc.stdout)

    def test_analyze_base_ref_includes_worktree_diff_text(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        (self.repo / "app.py").write_text("import os\nos.system('rm -rf /')\n", encoding="utf-8")
        proc = run([sys.executable, str(AFR), "analyze", "--base-ref", "HEAD"], self.repo, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        ids = {item["id"] for item in manifest["risk"]["findings"]}
        self.assertIn("dangerous-added-lines", ids)

    def test_analyze_base_ref_scans_untracked_added_files_for_dangerous_lines(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        (self.repo / "migration.sql").write_text("DROP TABLE users;\n", encoding="utf-8")
        proc = run([sys.executable, str(AFR), "analyze", "--base-ref", "HEAD"], self.repo, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest = json.loads((self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8"))
        findings = manifest["risk"]["findings"]
        dangerous = [item for item in findings if item["id"] == "dangerous-added-lines"]
        self.assertTrue(dangerous)
        self.assertIn("migration.sql", "\n".join(dangerous[0]["evidence"]))

    def test_analyze_scans_utf8_text_with_non_ascii_content(self) -> None:
        run([sys.executable, str(AFR), "init"], self.repo)
        secret = "sk-" + ("a" * 32)
        (self.repo / "localized.py").write_text(("\u00fc" * 200) + f"\nAPI_KEY='{secret}'\n", encoding="utf-8")
        proc = run([sys.executable, str(AFR), "analyze", "--base-ref", "HEAD"], self.repo, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        manifest_text = (self.repo / ".agent-flight" / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn(secret, manifest_text)
        manifest = json.loads(manifest_text)
        changed = {item["path"]: item for item in manifest["files"]["changed"]}
        self.assertFalse(changed["localized.py"]["binary"])
        ids = {item["id"] for item in manifest["risk"]["findings"]}
        self.assertIn("possible-secret-leak", ids)


if __name__ == "__main__":
    unittest.main()
