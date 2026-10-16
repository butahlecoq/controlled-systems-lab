"""Exercise measured-branch orchestration with a failing test child, not a benchmark."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import patch

import collect


def main(out: Path) -> None:
    build = collect.ROOT / "build" / "issue3-report"
    assert out.parent.resolve() == build.resolve()
    review = build / "test-measured-path-review.json"
    review.write_text(json.dumps({
        "reviewed_head": "994f3ee4310b4087d289e2eb02adbdb9dfd97827",
        "review_urls": [
            "https://github.com/butahlecoq/controlled-systems-lab/pull/354#test-one",
            "https://github.com/butahlecoq/controlled-systems-lab/pull/354#test-two",
        ],
        "purpose": "test-only; not review evidence",
    }), encoding="utf-8")

    def failing_child(_command: list[str], target: Path, name: str,
                      timeout_seconds: int) -> tuple[bytes, bytes, int, bool]:
        assert name == "accepted" and timeout_seconds == 1800
        script = ("import sys;sys.stdout.buffer.write(b'test-attempt\\n');"
                  "sys.stderr.buffer.write(b'deliberate-failure\\n');sys.exit(9)")
        return real_capture([sys.executable, "-c", script], target, name, 5)

    real_capture = collect.capture
    argv = ["collect.py", "--build", str(build), "--exe", sys.executable,
            "--cmake", sys.executable,
            "--reviewed-head", "994f3ee4310b4087d289e2eb02adbdb9dfd97827",
            "--out", str(out), "--review-evidence", str(review)]
    with patch.object(sys, "argv", argv), \
         patch.object(collect, "admission", return_value=(
             argv[8], build, Path(sys.executable))), \
         patch.object(collect, "authenticate_build", return_value={
             "schema": "test-only-preflight", "fixture_sha256": "a" * 64}), \
         patch.object(collect, "capture", side_effect=failing_child):
        try:
            collect.main()
        except ValueError as error:
            assert "measured child failed" in str(error)
        else:
            raise AssertionError("failing measured child was admitted")
    assert (out / "accepted.stdout").read_bytes() == b"test-attempt\n"
    assert (out / "accepted.stderr").read_bytes() == b"deliberate-failure\n"
    process = json.loads((out / "process-capture.json").read_text(encoding="utf-8"))
    assert process["return_code"] == 9
    assert process["timed_out"] is False
    error = json.loads((out / "collection-error.json").read_text(encoding="utf-8"))
    assert error == {"error_type": "ValueError",
                     "error": "measured child failed; raw stdout/stderr retained"}
    assert not (out / "collection-status.json").exists()
    print("measured path retained failed test child; no benchmark launched")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_measured_path.py BUILD_OUTPUT_DIR")
    main(Path(sys.argv[1]))
