from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts/reports/mpc01/build_strategy_ab_records.py"
SPEC = importlib.util.spec_from_file_location("mpc01_strategy_ab_record_builder", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

BUNDLE = ROOT / "docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts02-limited-capture"
OUTCOME_TERMINATIONS = (
    "refused",
    "unsupported",
    "timed_out",
    "resource_limited",
    "cancelled",
    "failed",
    "incomplete",
)


class Mpc01RecordBuilderTests(unittest.TestCase):
    def test_round_trip_retains_each_non_success_outcome(self) -> None:
        rows = [json.loads(line) for line in (BUNDLE / "strategy-ab-ts02-events.jsonl").read_text().splitlines()]
        trials = [row for row in rows if row.get("event") == "trial"]
        self.assertGreaterEqual(len(trials), len(OUTCOME_TERMINATIONS))
        for row, termination in zip(trials, OUTCOME_TERMINATIONS):
            row["status"] = termination
            row["termination"] = termination

        with tempfile.TemporaryDirectory() as temporary:
            events = Path(temporary) / "events.jsonl"
            events.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
            record = BUILDER.build_record(
                events,
                BUNDLE / "scenario.json",
                BUNDLE / "strategy-ab-ts02-environment.json",
                BUNDLE / "strategy-ab-ts02-csl-environment.json",
            )

        statuses = [attempt["reported_status"] for attempt in record["attempts"]]
        for termination in OUTCOME_TERMINATIONS:
            self.assertIn(termination, statuses)
        self.assertEqual(len(statuses), len(trials))

    def test_rejects_status_that_disagrees_with_termination(self) -> None:
        rows = [json.loads(line) for line in (BUNDLE / "strategy-ab-ts02-events.jsonl").read_text().splitlines()]
        trial = next(row for row in rows if row.get("event") == "trial")
        trial["status"] = "passed"
        trial["termination"] = "timed_out"

        with tempfile.TemporaryDirectory() as temporary:
            events = Path(temporary) / "events.jsonl"
            events.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))
            with self.assertRaisesRegex(ValueError, "event schema/status vocabulary"):
                BUILDER.build_record(
                    events,
                    BUNDLE / "scenario.json",
                    BUNDLE / "strategy-ab-ts02-environment.json",
                    BUNDLE / "strategy-ab-ts02-csl-environment.json",
                )


if __name__ == "__main__":
    unittest.main()
