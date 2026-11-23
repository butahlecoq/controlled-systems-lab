"""Check the archived nominal exact example and its publication validator."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))
import stage_syn03_nominal_exact_example as nominal_exact_example

ROOT = Path(__file__).resolve().parents[2]


class NominalExactPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.site = Path(temporary.name)

    def test_nominal_exact_example_stages_its_hash_checked_bundle(self) -> None:
        source = ROOT / "reports/algorithm-results/syn03-nominal-exact-2d-8b94095"
        stage_root = self.site / "custom-stage"
        stage_root.mkdir()
        report_id = nominal_exact_example.stage(source, stage_root)
        staged = stage_root / report_id
        self.assertEqual(report_id, "syn03-nominal-exact-2d-8b94095")
        self.assertEqual(
            (staged / "records.json").read_bytes(), (source / "records.json").read_bytes()
        )
        self.assertIn("optimal-face.svg", (staged / "index.html").read_text())

    def test_nominal_exact_example_rejects_changed_bytes(self) -> None:
        source = ROOT / "reports/algorithm-results/syn03-nominal-exact-2d-8b94095"
        copied = self.site / "modified-bundle"
        shutil.copytree(source, copied)
        (copied / "optimal-face.svg").write_text("changed")
        stage_root = self.site / "modified-stage"
        stage_root.mkdir()
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            nominal_exact_example.stage(copied, stage_root)


if __name__ == "__main__":
    unittest.main()
