import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "reports" / "algorithm-results" / "mpc02-four-track-direct-v1"


class Mpc02FourTrackDirectMeasurementTest(unittest.TestCase):
    def test_bundle_has_four_checked_tracks(self):
        events = [json.loads(line) for line in (BUNDLE / "events.jsonl").read_text().splitlines()]
        attempts = [event for event in events if event["event"] == "attempt"]
        self.assertEqual(len(attempts), 32)
        expected = {
            "mpc02-unconstrained-2d-v1": (8, 6, [0.5, 0.0], 0.0),
            "mpc02-stage-box-2d-v1": (8, 10, [0.5, 0.0], 0.0),
            "mpc02-slew-2d-v1": (8, 11, [0.375, 0.125], 1.0 / 32.0),
            "mpc02-l1-budget-2d-v1": (8, 14, [0.25, 0.0], 1.0 / 16.0),
        }
        for case, (variables, rows, controls, objective) in expected.items():
            case_attempts = [event for event in attempts if event["case"] == case]
            self.assertEqual(len(case_attempts), 8)
            self.assertEqual(sum(event["status"] == "passed" for event in case_attempts), 8)
            self.assertEqual({event["variables"] for event in case_attempts}, {variables})
            self.assertEqual({event["rows"] for event in case_attempts}, {rows})
            self.assertEqual({event["max_residual"] for event in case_attempts}, {0})
            for event in case_attempts:
                self.assertEqual(len(event["controls"]), len(controls))
                for actual, expected_control in zip(event["controls"], controls):
                    self.assertAlmostEqual(actual, expected_control)
                self.assertAlmostEqual(event["objective"], objective)
        summary = next(event for event in events if event["event"] == "summary")
        self.assertEqual(summary, {
            "schema": "csl.mpc02-four-track-direct-measurement/1",
            "event": "summary",
            "tracks": 4,
            "attempts_per_track": 8,
            "failures": 0,
        })


if __name__ == "__main__":
    unittest.main()
