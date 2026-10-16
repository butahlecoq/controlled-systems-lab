"""Authenticate and capture a fixed-head finite-action minimax measurement.

Run only after independent review of the exact harness head. Preflight-only is
available for functional review and never executes --measure.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "994f3ee4310b4087d289e2eb02adbdb9dfd97827"
TARGET = "csl_issue3_finite_action_report"
ALLOWED_DELTA = {
    "CMakeLists.txt", "cmake/OptionalReports.cmake",
    "benchmarks/reporting/issue3/finite_catalogue_driver.cpp",
    "scripts/reports/issue3/README.md", "scripts/reports/issue3/check_smoke.py",
    "scripts/reports/issue3/collect.py",
    "scripts/reports/issue3/test_capture.py",
}
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import collector_common as common


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: dict) -> None:
    common.durable_text(path, json.dumps(value, indent=2, sort_keys=True,
                                         ensure_ascii=False, allow_nan=False) + "\n")


def durable_bytes(path: Path, value: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def capture(command: list[str], out: Path, name: str,
            timeout_seconds: int) -> tuple[bytes, bytes, int, bool]:
    """Retain complete or partial process bytes and status before interpreting them."""
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   timeout=timeout_seconds, check=False)
        stdout, stderr, code, timed_out = (completed.stdout, completed.stderr,
                                           completed.returncode, False)
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        code, timed_out = 124, True
    except OSError as error:
        stdout, stderr, code, timed_out = b"", str(error).encode(), 127, False
    durable_bytes(out / f"{name}.stdout", stdout)
    durable_bytes(out / f"{name}.stderr", stderr)
    save(out / f"{name}.process.json", {
        "schema": "csl.issue3-process-capture/1", "command": command,
        "return_code": code, "timed_out": timed_out,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest()})
    return stdout, stderr, code, timed_out


def admission(args: argparse.Namespace) -> tuple[str, Path, Path]:
    head = run("git", "rev-parse", "HEAD")
    if head != args.reviewed_head or len(head) != 40:
        raise ValueError("checkout differs from independently reviewed harness head")
    if run("git", "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("reviewed source tree is dirty")
    if subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, head],
                      cwd=ROOT, check=False).returncode:
        raise ValueError("frozen source commit is not an ancestor")
    delta = set(run("git", "diff", "--name-only", SOURCE, head).splitlines())
    if delta != ALLOWED_DELTA:
        raise ValueError(f"source-to-harness delta differs: {sorted(delta ^ ALLOWED_DELTA)}")
    build = args.build.resolve(strict=True)
    if not build.is_relative_to(ROOT / "build") or build.is_symlink():
        raise ValueError("build must be a real project-local build directory")
    exe = build / "Release" / (TARGET + (".exe" if platform.system() == "Windows" else ""))
    if args.exe.resolve(strict=True) != exe.resolve(strict=True):
        raise ValueError("executable differs from configured Release target path")
    if not args.exe.samefile(exe):
        raise ValueError("executable physical identity differs")
    return head, build, exe


def authenticate_build(args: argparse.Namespace, head: str, build: Path, exe: Path,
                       out: Path) -> dict:
    query = build / ".cmake" / "api" / "v1" / "query"
    query.mkdir(parents=True, exist_ok=True)
    (query / "codemodel-v2").touch()
    (query / "toolchains-v1").touch()
    configure = [str(args.cmake), "-S", str(ROOT), "-B", str(build),
                 "-DCSL_BUILD_ISSUE3_REPORT=ON", "-DCSL_ENABLE_HIGHS=OFF",
                 "-DCSL_ENABLE_QHULL=OFF"]
    _, _, configure_code, configure_timeout = capture(configure, out, "configure", 600)
    if configure_code or configure_timeout:
        raise ValueError("fresh CMake configure failed; output retained")

    def build_command(command: list[str]) -> tuple[str, str, int, bool]:
        stdout, stderr, code, timed_out = capture(
            [str(args.cmake), *command[1:]], out, "fresh-build", 600)
        return (stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"), code, timed_out)

    common.fresh_release_build(build, TARGET, out / "fresh-build.json", ROOT,
                               source_commit=SOURCE, harness_commit=head,
                               run=build_command,
                               validate_log=lambda: common.validate_build_log(
                                   out / "fresh-build.json", build, exe, ROOT))
    graph = common.release_graph(build, exe, ROOT, target_name=TARGET,
        required={TARGET, "csl_finite_action_minimax", "csl_fixed_plan_disturbance",
                  "csl_worst_case_vertex", "csl_objectives", "csl_sets",
                  "csl_model", "csl_resolved_core"})
    save(out / "build-graph.json", graph)
    smoke_stdout, smoke_stderr, smoke_code, smoke_timeout = capture(
        [str(exe), "--smoke"], out, "smoke", 60)
    if smoke_code or smoke_timeout or smoke_stderr:
        raise ValueError("fresh executable smoke failed; raw output retained")
    rows = [json.loads(line) for line in smoke_stdout.splitlines()]
    if len(rows) != 8 or any(row.get("source_commit") != SOURCE or
                             row.get("harness_commit") != head for row in rows):
        raise ValueError("fresh executable embedded source/harness IDs differ")
    fixture_hash = digest(ROOT / "benchmarks/reporting/issue3/finite_catalogue_driver.cpp")
    if any(row.get("fixture_sha256") != fixture_hash for row in rows):
        raise ValueError("embedded fixture SHA-256 differs from actual driver source")
    checked_stdout, checked_stderr, checked_code, checked_timeout = capture([sys.executable,
        str(ROOT / "scripts/reports/issue3/check_smoke.py"), str(exe)],
        out, "smoke-check", 60)
    if checked_code or checked_timeout or checked_stderr:
        raise ValueError("independent literal smoke check failed")
    return {"schema": "csl.issue3-preflight/1", "source_commit": SOURCE,
            "harness_commit": head,
            "source_tree": run("git", "rev-parse", f"{SOURCE}^{{tree}}"),
            "harness_tree": run("git", "rev-parse", "HEAD^{tree}"),
            "fixture_sha256": fixture_hash, "binary_sha256": digest(exe),
            "build_graph_sha256": digest(out / "build-graph.json"),
            "fresh_build_sha256": digest(out / "fresh-build.json"),
            "build_configuration": "Release", "compiler": graph["compiler"],
            "cmake": graph["cmake"], "os": platform.platform(),
            "processor": platform.processor(), "logical_processors": __import__("os").cpu_count(),
            "requested_driver_workers": 1, "actual_native_threads": None,
            "actual_native_threads_reason": "No native thread count counter exposed by this public path.",
            "arithmetic": "binary64; absolute B08 tie tolerance 1e-8; numerical assurance"}


def validate_rows(raw: bytes, head: str, fixture_hash: str,
                  smoke_rows: list[dict]) -> list[dict]:
    rows = [json.loads(line) for line in raw.splitlines()]
    names = ["l19", "integrator", "all_infeasible", "empty_catalogue",
             "no_scenarios", "unsupported", "cancelled", "b08_rounded"]
    smoke_by_fixture = {row["fixture"]: row for row in smoke_rows}
    if set(smoke_by_fixture) != set(names) or len(smoke_rows) != len(names):
        raise ValueError("authenticated smoke catalogue differs")
    if len(rows) != 64:
        raise ValueError(f"expected 64 warmup/measured rows, got {len(rows)}")
    for round_number in range(8):
        expected_order = names if round_number % 2 == 0 else list(reversed(names))
        group = rows[8 * round_number:8 * (round_number + 1)]
        if [row.get("fixture") for row in group] != expected_order:
            raise ValueError("alternating fixture order differs")
        for row in group:
            fixture = row["fixture"]
            batch = 1 if fixture == "b08_rounded" else 10000 if fixture == "l19" else 5000
            if (row.get("schema") != "csl.issue3-raw-trial/1" or
                row.get("source_commit") != SOURCE or row.get("harness_commit") != head or
                row.get("fixture_sha256") != fixture_hash or
                row.get("round") != round_number or
                row.get("warmup") is not (round_number == 0) or
                row.get("batch") != batch or row.get("checked_calls") != batch or
                type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] < 20_000_000 or
                row.get("checks", {}).get("passed") is not True or
                row["checks"].get("observed") != row.get("result") or
                hashlib.sha256(row["input_canonical"].encode()).hexdigest() !=
                    row.get("input_sha256")):
                raise ValueError("raw trial identity, work count, duration or check differs")
            reference = smoke_by_fixture[fixture]
            retained = ("input_canonical", "input_sha256", "problem_id", "request_id",
                        "limits", "objective_convention", "assurance", "plan_count",
                        "evaluated_terminal_rows")
            if any(row.get(field) != reference.get(field) for field in retained):
                raise ValueError("raw trial mathematical identity differs from authenticated smoke")
            result = row["result"]
            expected = row["checks"]["expected"]
            if fixture == "b08_rounded":
                if (result.get("status") != "numerical_optimal" or
                    result.get("plan_count") != 625 or
                    result.get("evaluated_vertices") != 160000 or
                    result.get("minimizing_plan_indices") != [17, 33, 129] or
                    abs(result.get("value", float("inf")) - 67.150601101407) > 1e-8):
                    raise ValueError("B08 public numerical oracle differs")
            elif result != expected:
                raise ValueError(f"{fixture} public literal oracle differs")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    parser.add_argument("--reviewed-head", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--review-evidence", type=Path,
                        help="JSON with reviewed_head and two independent review URLs")
    args = parser.parse_args()
    if Path.cwd().resolve() != ROOT:
        raise ValueError("collector must run from its source root")
    head, build, exe = admission(args)
    if not args.cmake.is_file():
        raise ValueError("selected CMake executable absent")
    if not args.preflight_only:
        if args.review_evidence is None:
            raise ValueError("accepted collection requires independent review evidence")
        evidence = json.loads(args.review_evidence.read_text(encoding="utf-8"))
        if (evidence.get("reviewed_head") != head or
            len(set(evidence.get("review_urls", []))) < 2 or
            any(not url.startswith("https://github.com/butahlecoq/controlled-systems-lab/")
                for url in evidence["review_urls"])):
            raise ValueError("review evidence differs from fixed harness head")
    out = args.out.resolve()
    if not out.is_relative_to(build) or out == build or out.exists():
        raise ValueError("new output directory must be inside build")
    out.mkdir(parents=True)
    try:
        provenance = authenticate_build(args, head, build, exe, out)
        save(out / "preflight.json", provenance)
        if args.preflight_only:
            print("preflight only; no measured calls", out)
            return
        raw, errors, return_code, timed_out = capture(
            [str(exe), "--measure", "7"], out, "accepted", 1800)
        capture = {"schema": "csl.issue3-process-capture/1", "return_code": return_code,
                   "timed_out": timed_out, "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                   "stderr_sha256": hashlib.sha256(errors).hexdigest(),
                   "attempted_utc": datetime.now(timezone.utc).isoformat()}
        save(out / "process-capture.json", capture)
        if return_code or timed_out or errors:
            raise ValueError("measured child failed; raw stdout/stderr retained")
        smoke_rows = [json.loads(line) for line in
                      (out / "smoke.stdout").read_bytes().splitlines()]
        rows = validate_rows(raw, head, provenance["fixture_sha256"], smoke_rows)
        if run("git", "rev-parse", "HEAD") != head or run("git", "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("source changed during collection")
        save(out / "collection-status.json", {"schema": "csl.issue3-collection-status/1",
             "status": "complete", "trial_count": len(rows), "warmup_count": 8,
             "measured_count": 56, "raw_sha256": capture["stdout_sha256"]})
        print("saved 64 validated raw trial rows at", out)
    except Exception as error:
        save(out / "collection-error.json", {"error_type": type(error).__name__,
             "error": str(error)})
        raise


if __name__ == "__main__":
    main()
