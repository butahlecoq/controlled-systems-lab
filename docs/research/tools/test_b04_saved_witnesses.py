"""CLI tests; numerical tests require the three explicit private-source arguments."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("check_b04_saved_witnesses.py")
PRIVATE = None


def run_check(*args):
    # Optimized Python must retain all source and numerical guards.
    return subprocess.run([sys.executable, "-O", str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


class PublicBoundaryTests(unittest.TestCase):
    def test_missing_source_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.fig"
            result = run_check("--figure", missing, "--kernel", missing, "--driver", missing)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read A39", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_changed_source_is_rejected_before_mat_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "changed.fig"
            changed.write_bytes(b"not the registered archived figure")
            result = run_check("--figure", changed, "--kernel", changed, "--driver", changed)
            self.assertEqual(changed.read_bytes(), b"not the registered archived figure")
        self.assertEqual(result.returncode, 2)
        self.assertIn("A39 SHA-256 mismatch", result.stderr)
        self.assertIn("registered original", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_output_cannot_replace_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.fig"
            source.write_bytes(b"preserve me")
            result = run_check("--figure", source, "--kernel", source,
                               "--driver", source, "--output", source)
            self.assertEqual(source.read_bytes(), b"preserve me")
        self.assertEqual(result.returncode, 2)
        self.assertIn("output must not replace an input source", result.stderr)


class PrivateNumericalTests(unittest.TestCase):
    def test_original_arrays_reproduce_audited_values_and_timing(self):
        if PRIVATE is None:
            self.skipTest("private originals not supplied; archival reproduction NOT run")
        result = run_check(*PRIVATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"]["all_passed"], True)
        self.assertEqual(report["scalar_samples_compared"], 120000)
        for witness, nominal, nonlinear in zip(report["witnesses"],
                [30.899136030045337, 30.899136030147798, 30.899136030017026],
                [41.855290738349495, 65.8744016598146, 7.921766774950679]):
            self.assertAlmostEqual(witness["nominal_objective"], nominal, delta=1e-9)
            self.assertAlmostEqual(witness["nonlinear_objective"], nonlinear, delta=1e-9)
        matrix = report["replay_pair_max_error_matrix"]
        for index in range(3):
            self.assertLessEqual(matrix[index][index], 2e-12)
        self.assertAlmostEqual(matrix[0][1], 503.173, delta=0.001)
        self.assertAlmostEqual(matrix[0][2], 1085.514, delta=0.001)
        self.assertAlmostEqual(report["frozen"]["objective"], 368.6097808680356, delta=1e-9)
        self.assertAlmostEqual(report["frozen"]["rounding_box_objective_range"][0],
                               368.54934883615726, delta=1e-9)
        self.assertAlmostEqual(report["conditional_affine_minimum"]["objective"],
                               30.899136030021875, delta=1e-9)
        self.assertEqual(report["replay_events"][-1],
                         {"matlab_sample": 10000, "time_seconds": 99.99, "increment_number": 16})
        effect = report["last_increment_effect_on_final_sample"]
        self.assertAlmostEqual(effect[0], 19.91129648549213, delta=1e-10)
        self.assertAlmostEqual(effect[2], -10.948454768662998, delta=1e-10)
        self.assertEqual([effect[1], effect[3]], [0.0, 0.0])
        self.assertNotIn("recovered_controls", result.stdout)
        self.assertNotIn(str(Path(PRIVATE[1]).resolve()), result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("figure", "kernel", "driver"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    provided = [args.figure, args.kernel, args.driver]
    if any(provided) and not all(provided):
        parser.error("supply all three private sources, or none for public boundary checks")
    if all(provided):
        PRIVATE = ["--figure", args.figure, "--kernel", args.kernel, "--driver", args.driver]
    unittest.main(argv=[sys.argv[0]])
