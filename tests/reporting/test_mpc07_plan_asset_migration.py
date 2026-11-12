import hashlib
from pathlib import Path
import unittest

from benchmarks.reporting.mpc07 import joint_capture, report

ROOT = Path(__file__).resolve().parents[2]


class Mpc07PlanAssetMigrationTests(unittest.TestCase):
    def test_active_capture_consumers_use_the_sealed_capsule_and_keep_its_key(self):
        relative = "benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/PLAN.md"
        source = ROOT / relative
        self.assertTrue(source.is_file())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         "3791ccdfaa1b068cabaa474eef83263f2e0ec49bcb0e2a338cce5b6ac915b4f8")
        self.assertFalse((ROOT / "benchmarks/reporting/mpc07/PLAN.md").exists())
        self.assertFalse((ROOT / "benchmarks/reporting/mpc07/PLAN.txt").exists())
        expected = relative
        self.assertEqual(report.SOURCE_PATHS["PLAN.md"], expected)
        self.assertEqual(joint_capture.SOURCE_PATHS["PLAN.md"], expected)


if __name__ == "__main__":
    unittest.main()
