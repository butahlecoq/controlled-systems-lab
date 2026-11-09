import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks" / "reporting" / "review05"))
from highs_clock_events import parse_stderr, parse_result_stdout


def group(index=0):
    return {
        "schema": "csl.highs-clock-group/1",
        "provider_call_index": index,
        "capture_status": "captured",
        "highs_version": "1.11.0",
        "highs_archive_sha256": "2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275",
        "clock_patch_sha256": "9e6849f8933e3e434c5964f78f2c7229537a9398f1d6ded35a2cd2c5d1839501",
        "native_call_status": 0,
        "clocks": [
            {"id": 0, "name": "solve", "calls": 1, "elapsed_seconds": 0.125, "status": "observed"},
            {"id": 1, "name": "unused", "calls": 0, "elapsed_seconds": 0.0, "status": "uncalled"},
        ],
    }


class HighsClockEventTests(unittest.TestCase):
    def test_parses_multiple_hash_bound_stderr_events_and_ignores_other_stderr(self):
        first, second = group(0), group(1)
        raw = (b"solver diagnostic\nCSL_HIGHS_CLOCK/1 " + json.dumps(first).encode() +
               b"\nCSL_HIGHS_CLOCK/1 " + json.dumps(second).encode() + b"\n")
        self.assertEqual(parse_stderr(raw, enabled=True), [first, second])

    def test_diagnostic_stdout_requires_one_versioned_result(self):
        result = {"schema": "csl.review05.horizon-attempt/1", "horizon": 2}
        line = json.dumps(result, separators=(",", ":")).encode()
        self.assertEqual(parse_result_stdout(b"native timer table\n" + line + b"\n", True), result)
        for raw in (b"no result emitted\n", line + b"\n" + line):
            with self.assertRaisesRegex(ValueError, "exactly one"):
                parse_result_stdout(raw, True)
        with self.assertRaises(ValueError):
            parse_result_stdout(b"native timer table\n" + line, False)

    def test_empty_capture_requires_explicit_unavailable_status(self):
        value = group()
        value["clocks"] = []
        raw = b"CSL_HIGHS_CLOCK/1 " + json.dumps(value).encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            parse_stderr(raw, enabled=True)
        value["capture_status"] = "unavailable"
        raw = b"CSL_HIGHS_CLOCK/1 " + json.dumps(value).encode() + b"\n"
        self.assertEqual(parse_stderr(raw, enabled=True), [value])

    def test_rejects_different_pinned_source(self):
        value = group()
        value["clock_patch_sha256"] = "0" * 64
        raw = b"CSL_HIGHS_CLOCK/1 " + json.dumps(value).encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "unexpected pinned"):
            parse_stderr(raw, enabled=True)

    def test_rejects_nonfinite_elapsed_seconds(self):
        for seconds in (float("nan"), float("inf"), -float("inf")):
            value = group()
            value["clocks"][0]["elapsed_seconds"] = seconds
            raw = b"CSL_HIGHS_CLOCK/1 " + json.dumps(value).encode() + b"\n"
            with self.assertRaises(ValueError):
                parse_stderr(raw, enabled=True)

    def test_rejects_event_when_clock_capture_was_not_enabled(self):
        raw = b"CSL_HIGHS_CLOCK/1 " + json.dumps(group()).encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "uninstrumented"):
            parse_stderr(raw, enabled=False)

    def test_rejects_noncontiguous_provider_call_indices(self):
        raw = b"\n".join(b"CSL_HIGHS_CLOCK/1 " + json.dumps(group(i)).encode() for i in (0, 2))
        with self.assertRaisesRegex(ValueError, "contiguous"):
            parse_stderr(raw, enabled=True)

    def test_rejects_unavailable_sample_that_claims_numeric_values(self):
        value = group()
        value["clocks"][0] = {"id": 0, "name": "solve", "calls": 1,
                              "elapsed_seconds": None, "status": "unavailable"}
        raw = b"CSL_HIGHS_CLOCK/1 " + json.dumps(value).encode() + b"\n"
        with self.assertRaisesRegex(ValueError, "must not claim numeric"):
            parse_stderr(raw, enabled=True)


if __name__ == "__main__":
    unittest.main()
