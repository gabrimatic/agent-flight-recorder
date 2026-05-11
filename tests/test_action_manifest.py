from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ActionManifestTests(unittest.TestCase):
    def test_action_manifest_does_not_use_github_context_expressions(self) -> None:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertNotIn("${{ github.", action)


if __name__ == "__main__":
    unittest.main()
