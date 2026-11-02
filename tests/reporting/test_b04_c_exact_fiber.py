"""Adversarial checks for the B04-C exact optimal-fiber record verifier."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from docs.research.tools.check_b04_c_exact_fiber import DEFAULT_RECORD, check


class B04CExactFiberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads(DEFAULT_RECORD.read_text(encoding="utf-8"))

    def verify_record(self, record: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            return check(path)

    def test_exact_kkt_and_full_fiber_record_pass(self) -> None:
        result = self.verify_record(self.record)
        self.assertEqual(result["exact_kkt_stationarity"], "passed")
        self.assertEqual(result["optimal_control_family"].split()[0], "exact")
        self.assertEqual(result["terminal_set"], "singleton")

    def test_rejects_a_perturbed_optimal_control_witness(self) -> None:
        altered = copy.deepcopy(self.record)
        altered["optimality"]["control_witness"][0] = "1"
        with self.assertRaisesRegex(ValueError, "witness|stationarity"):
            self.verify_record(altered)

    def test_rejects_a_dropped_phase_constraint(self) -> None:
        altered = copy.deepcopy(self.record)
        altered["optimal_family"]["control_polytope_rows"].pop()
        with self.assertRaisesRegex(ValueError, "H-polytope"):
            self.verify_record(altered)

    def test_rejects_a_narrowed_terminal_fiber(self) -> None:
        altered = copy.deepcopy(self.record)
        altered["optimal_family"]["terminal_equalities"][0]["value"] = "0"
        with self.assertRaisesRegex(ValueError, "terminal fiber"):
            self.verify_record(altered)

    def test_rejects_a_changed_acceptance_band(self) -> None:
        altered = copy.deepcopy(self.record)
        altered["optimality"]["pre_registered_bands_unchanged"][0] = "J* ~= 31"
        with self.assertRaisesRegex(ValueError, "acceptance bands"):
            self.verify_record(altered)

    def test_two_phase_plane_figure_is_well_formed_and_labeled(self) -> None:
        figure = DEFAULT_RECORD.parent / "trajectory.svg"
        root = ET.parse(figure).getroot()
        namespace = "{http://www.w3.org/2000/svg}"
        self.assertEqual(root.tag, namespace + "svg")
        labels = " ".join(node.text or "" for node in root.iter(namespace + "text"))
        self.assertIn("Oxidizer phase plane", labels)
        self.assertIn("Fuel phase plane", labels)
        self.assertGreaterEqual(len(list(root.iter(namespace + "path"))), 4)


if __name__ == "__main__":
    unittest.main()
