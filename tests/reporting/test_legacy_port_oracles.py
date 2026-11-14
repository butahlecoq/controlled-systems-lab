"""Keep the independent A29/A33 hull-oracle identities and source closure."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTS = ROOT / "tools/legacy-ports"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_collector():
    report_dir = ROOT / "scripts/reports/exp06"
    sys.path.insert(0, str(report_dir))
    try:
        return load("exp06_collector_oracle_closure_test", report_dir / "collect.py")
    finally:
        sys.path.remove(str(report_dir))


a29 = load("a29_exact_hull_oracle_test", PORTS / "A29/oracle.py")
a33 = load("a33_exact_hull_oracle_test", PORTS / "A33/oracle.py")


class LegacyPortOracleTests(unittest.TestCase):
    def test_wrappers_keep_file_identity_without_mutating_import_paths(self):
        for identity in ("A29", "A33"):
            with self.subTest(identity=identity):
                before = list(sys.path)
                module = load(f"{identity.lower()}_wrapper_import_contract_test",
                              PORTS / identity / "oracle.py")
                self.assertEqual(sys.path, before)
                self.assertEqual(Path(module.__file__).resolve(),
                                 (PORTS / identity / "oracle.py").resolve())

    def test_historical_digest_domains_and_golden_ids_remain_distinct(self):
        points = json.loads((PORTS / "A29/fixtures/square.json").read_text())["points"]
        self.assertEqual(
            a29.manifest_digest(points),
            "d3ceea7207af73a9ede56875d53cfae5eab1160c9458617cff0b4a176e53b1fe",
        )
        self.assertEqual(
            a33.manifest_digest(points),
            "d3047ccc36dbd826db6a821a59f60b1ca699e43dec03cab2abcd5ad55f52e2a9",
        )
        self.assertNotEqual(a29.manifest_digest(points), a33.manifest_digest(points))

    def test_exact_dyadic_coverage_accepts_degeneracy_and_duplicates(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        cases = (
            (square + [[0, 0], [1, 1]], square, [0, 1, 2, 3]),
            ([[0, 0], [1, 1], [2, 2], [0.5, 0.5]], [[0, 0], [2, 2]], [0, 2]),
        )
        for oracle in (a29, a33):
            for points, output, source_indices in cases:
                with self.subTest(oracle=oracle.__name__, points=points):
                    result = oracle.check(points, output)
                    self.assertEqual(result["status"], "verified")
                    self.assertEqual(result["source_indices"], source_indices)

    def test_exact_dyadic_point_just_outside_reported_square_is_rejected(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        points = square + [[1, -(2**-54)]]
        for oracle in (a29, a33):
            with self.subTest(oracle=oracle.__name__):
                result = oracle.check(points, square)
                self.assertEqual(result["status"], "incorrect")
                self.assertEqual(result["counterexample_index"], 4)

    def test_wrong_or_duplicate_output_ids_and_incomplete_hull_are_rejected(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        for oracle in (a29, a33):
            with self.subTest(oracle=oracle.__name__):
                missing_corner = oracle.check(square + [[1, 1]],
                                              [[0, 0], [2, 0], [2, 2], [1, 1]])
                self.assertEqual(missing_corner["status"], "incorrect")
                self.assertEqual(missing_corner["counterexample_index"], 3)
                absent_source_id = oracle.check(square, [[0, 0], [3, 3]])
                self.assertEqual(absent_source_id["reason"],
                                 "output point is absent from source manifest")
                duplicate_source_id = oracle.check(square + [[0, 0]], square + [[0, 0]])
                self.assertEqual(duplicate_source_id["reason"], "duplicate source index")

    def test_unsupported_inputs_and_capacity_keep_inconclusive_status(self):
        for oracle in (a29, a33):
            with self.subTest(oracle=oracle.__name__):
                self.assertEqual(oracle.check([[0, 0, 0]], [[0, 0, 0]])["status"],
                                 "inconclusive")
                self.assertEqual(oracle.check([[0, float("inf")]], [[0, 0]])["status"],
                                 "inconclusive")
                self.assertEqual(oracle.check([[i, 0] for i in range(3)], [[0, 0]],
                                             max_points=2)["reason"],
                                 "oracle point capacity exceeded")
                self.assertEqual(oracle.check([[0, 0]], None)["reason"],
                                 "algorithm did not produce a hull")

    def test_current_exp06_source_closure_adds_helper_without_rewriting_saved_record(self):
        collector = load_collector()
        sources = collector.a29_source_closure()
        self.assertEqual([item["path"] for item in sources], [
            "tools/legacy-ports/A29/port.py",
            "tools/legacy-ports/A29/oracle.py",
            "tools/legacy-ports/common/exact_binary64_hull.py",
        ])
        for item in sources:
            data = (ROOT / item["path"]).read_bytes()
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())

        historical = json.loads(
            (ROOT / "reports/algorithm-results/exp06-geometry-pilot-20261029/comparison-record.json")
            .read_text(encoding="utf-8")
        )
        first_attempt = next(json.loads(item["run"]) for item in historical["attempts"]
                             if json.loads(item["run"])["method"]["id"]
                             == "csl.geometry.a29-a30-python")
        method = first_attempt["method"]
        self.assertEqual([source["path"] for source in method["sources"]], [
            "tools/legacy-ports/A29/port.py", "tools/legacy-ports/A29/oracle.py"
        ])
        self.assertEqual(method["sources"][1]["sha256"],
                         "90d570f4fe65d15e2379999640d5ecafc8eb6643ffd092eea04de42b35e7dd6c")


if __name__ == "__main__":
    unittest.main()
