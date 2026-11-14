"""Check the authored discrete-MPC lesson against its native saved output."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
stage_discrete_mpc_2d = importlib.import_module("stage_discrete_mpc_2d")


class DiscreteMpc2dStagerTests(unittest.TestCase):
    def test_stager_uses_actual_capture_and_declares_feedback_limits(self):
        files, entries, card = stage_discrete_mpc_2d.build(ROOT)
        page = files[stage_discrete_mpc_2d.PAGE].decode("utf-8")
        record = json.loads(files[stage_discrete_mpc_2d.RECORD])
        figure = ET.fromstring(files[stage_discrete_mpc_2d.FIGURE])

        self.assertIn('href="examples.css"', page)
        self.assertNotIn("<style", page)
        self.assertIn("The same compiled running-state, control and terminal costs", page)
        self.assertIn("does not establish robustness", page)
        self.assertIn("nominal-quadratic-history-2d.html", page)
        self.assertEqual(record["answer"]["first_disturbed_replay_action_divergence_stage"], 4)
        self.assertEqual(record["answer"]["open_loop_first_control_coordinate"], 0.0)
        self.assertAlmostEqual(
            record["answer"]["observed_mpc_first_control_coordinate"],
            1.050202086852605,
        )
        self.assertTrue(record["evidence"]["actual_replay_csv_is_solver_output"])
        self.assertTrue(
            record["evidence"][
                "realized_objectives_independently_recomputed_from_executed_states_and_actions"
            ]
        )
        self.assertIn(
            "not a fresh full-SDK install qualification", record["evidence"]["build_scope"]
        )
        self.assertEqual(entries[0]["status"], "educational-example")
        self.assertIn(stage_discrete_mpc_2d.PAGE, card)
        self.assertEqual(figure.tag, "{http://www.w3.org/2000/svg}svg")
        description = figure.find("{http://www.w3.org/2000/svg}desc")
        self.assertIsNotNone(description)
        assert description is not None
        self.assertTrue(description.text)
        self.assertEqual(
            files[stage_discrete_mpc_2d.CSV],
            (ROOT / "examples/discrete_mpc_2d-output.csv").read_bytes(),
        )

        with tempfile.TemporaryDirectory() as temporary:
            copied_root = Path(temporary)
            (copied_root / "examples").mkdir()
            for relative in (
                "examples/discrete_mpc_2d-output.csv",
                "examples/discrete_mpc_2d-output.txt",
            ):
                shutil.copyfile(ROOT / relative, copied_root / relative)
            tampered = copied_root / "examples/discrete_mpc_2d-output.csv"
            tampered.write_bytes(tampered.read_bytes() + b"tampered\n")
            with self.assertRaisesRegex(ValueError, "capture differs"):
                stage_discrete_mpc_2d.build(copied_root)

    def test_stdout_provenance_uses_the_explicit_repository_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            checked_root = Path(temporary) / "checked-root"
            module_checkout = Path(temporary) / "other-module-checkout"
            for relative in (
                "examples/discrete_mpc_2d-output.csv",
                "examples/discrete_mpc_2d-output.txt",
            ):
                target = checked_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            other_stdout = module_checkout / "examples/discrete_mpc_2d-output.txt"
            other_stdout.parent.mkdir(parents=True)
            other_stdout.write_text("unverified module-checkout stdout\n", encoding="ascii")
            module_path = module_checkout / "scripts/reports/stage_discrete_mpc_2d.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("test placeholder\n", encoding="ascii")

            with patch.object(stage_discrete_mpc_2d, "__file__", str(module_path)):
                files, _, _ = stage_discrete_mpc_2d.build(checked_root)

            record = json.loads(files[stage_discrete_mpc_2d.RECORD])
            self.assertEqual(
                record["evidence"]["native_example_stdout"],
                (checked_root / "examples/discrete_mpc_2d-output.txt")
                .read_text(encoding="ascii")
                .rstrip("\n"),
            )
            self.assertNotIn(
                "unverified module-checkout",
                record["evidence"]["native_example_stdout"],
            )


if __name__ == "__main__":
    unittest.main()
