from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_flight_recorder.config import default_config
from agent_flight_recorder.snapshot import compare_inventories, inventory, path_matches_any


class SnapshotTests(unittest.TestCase):
    def test_inventory_detects_added_modified_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("1\n", encoding="utf-8")
            before = inventory(root, default_config())
            (root / "a.py").write_text("2\n", encoding="utf-8")
            (root / "b.py").write_text("3\n", encoding="utf-8")
            after = inventory(root, default_config())
            changes = compare_inventories(before, after)
            by_path = {item["path"]: item["status"] for item in changes}
            self.assertEqual(by_path["a.py"], "M")
            self.assertEqual(by_path["b.py"], "A")

    def test_exclude_glob(self) -> None:
        self.assertTrue(path_matches_any("node_modules/pkg/index.js", ["node_modules/**"]))
        self.assertTrue(path_matches_any("foo.pyc", ["*.pyc"]))
        self.assertFalse(path_matches_any("src/app.py", ["node_modules/**"]))


if __name__ == "__main__":
    unittest.main()
