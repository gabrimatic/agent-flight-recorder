from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ActionManifestTests(unittest.TestCase):
    def test_action_manifest_does_not_use_github_context_expressions(self) -> None:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertNotIn("${{ github.", action)

    def test_action_can_verify_existing_manifest_without_reanalyzing(self) -> None:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertIn("manifest:", action)
        self.assertIn('MANIFEST_INPUT="${{ inputs.manifest }}"', action)
        self.assertIn('report --manifest "$MANIFEST_INPUT"', action)
        self.assertIn('VERIFY_ARGS=(--manifest "$MANIFEST_INPUT"', action)

    def test_action_does_not_ignore_init_failures(self) -> None:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertIn('python "$AFR_BIN" init', action)
        self.assertNotIn('python "$AFR_BIN" init || true', action)


if __name__ == "__main__":
    unittest.main()
