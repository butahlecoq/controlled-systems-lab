#!/usr/bin/env python3
"""Capture matched fixed-dimension state-constraint-row runs."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, platform, shutil, subprocess, time
from pathlib import Path

STRATEGIES = ("csl.synthesis.reach-back", "csl.synthesis.strategy-b")
CASES = (2, 4, 8)
FIXTURE = "CONSTRAINT-01-redundant-state-H-rows"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def limit_process() -> None:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    cap = 8 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--scenarios", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    driver = args.driver.resolve(strict=True)
    scenarios = args.scenarios.resolve(strict=True)
    source = Path(__file__).resolve().parent
    repo = scenarios.parents[3]
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir()
    (output / "inputs").mkdir()
    paths = {f"r{rows}": scenarios / f"constraint01-n1-t2-r{rows}.json" for rows in CASES}
    for path in paths.values():
        if not path.is_file():
            parser.error(f"missing fixture: {path}")
        shutil.copyfile(path, output / "inputs" / path.name)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                cwd=repo, check=True, capture_output=True, text=True).stdout)
    try:
        load = list(os.getloadavg())
    except (AttributeError, OSError):
        load = None
    source_files = ("CMakeLists.txt", "dimension_ladder.cpp", "run_constraint_ladder.py",
                    "check_constraint_ladder.py", "summarize_constraint_ladder.py",
                    "render_constraint_ladder.py")
    manifest = {
        "schema": "csl.review05.constraint-manifest/1", "track": "new-comparison",
        "fixture": FIXTURE,
        "fixed_problem": {"state_dimension": 1, "control_dimension": 1, "horizon": 2,
                          "model": "x[k+1]=x[k]+u[k]", "initial_state": 0,
                          "control_bounds": [0, 1], "state_set": [-2, 2],
                          "objective": "minimize x[2]"},
        "cases": {key: {"state_rows_per_stage": rows, "stages": 3,
                         "authored_state_rows_total": rows * 3,
                         "scenario_sha256": sha(path)}
                  for rows, (key, path) in zip(CASES, paths.items())},
        "environment": {
            "source_revision": revision, "source_worktree_dirty": dirty,
            "measurement_source_sha256": {name: sha(source / name) for name in source_files},
            "host": platform.node(), "platform": platform.platform(), "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "physical_memory_bytes": int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE")),
            "python": platform.python_version(), "load_average_at_start": load,
            "binary_sha256": sha(driver), "requested_threads_per_strategy": 1,
            "requested_driver_workers": 1,
            "limits": {"cpu_seconds": 300, "address_space_bytes": 8 * 1024**3,
                       "process_timeout_seconds": 300, "scope": "one strategy process",
                       "enforced": True, "mechanism": "POSIX RLIMIT_CPU and RLIMIT_AS"}},
        "schedule": {"warmup_pairs_per_case": 1, "measured_pairs_per_case": 6,
                     "order": "alternating AB/BA; case order rotates by repetition",
                     "timed_region": "steady_clock around SynthesisWorkspace::run only",
                     "process_wall_ns": "launch through process exit; diagnostic only",
                     "startup_setup": "excluded from strategy_run_ns"}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    attempts_path = output / "attempts.jsonl"
    attempts_path.touch(exist_ok=False)
    number = 0
    for repetition in range(7):
        keys = list(paths)
        shift = repetition % len(keys)
        keys = keys[shift:] + keys[:shift]
        for key in keys:
            rows = int(key[1:])
            warmup = repetition == 0
            first = (repetition + rows // 2) % 2
            order = (STRATEGIES[first], STRATEGIES[1 - first])
            for position, strategy in enumerate(order):
                number += 1
                attempt_id = f"{key}-r{repetition:02d}-p{position}-{number:03d}"
                command = [str(driver), str(paths[key]), strategy, FIXTURE]
                start = time.monotonic_ns()
                try:
                    process = subprocess.run(command, check=False, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, timeout=300,
                                             preexec_fn=limit_process)
                    wall = time.monotonic_ns() - start
                    stdout, stderr, code = process.stdout, process.stderr, process.returncode
                    status = "completed" if code == 0 else "failed"
                except subprocess.TimeoutExpired as error:
                    wall = time.monotonic_ns() - start
                    stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
                    status = "timed_out"
                except Exception as error:
                    wall = time.monotonic_ns() - start
                    stdout, stderr, code = b"", str(error).encode(), None
                    status = "failed_to_launch"
                stdout_path = output / "raw" / f"{attempt_id}.stdout"
                stderr_path = output / "raw" / f"{attempt_id}.stderr"
                stdout_path.write_bytes(stdout)
                stderr_path.write_bytes(stderr)
                try:
                    result = json.loads(stdout.decode()) if status == "completed" else None
                    parse_error = None
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    result, parse_error, status = None, str(error), "invalid_output"
                row = {"attempt_id": attempt_id, "case": key, "state_rows_per_stage": rows,
                       "authored_state_rows_total": rows * 3, "repetition": repetition,
                       "warmup": warmup, "order_position": position, "strategy": strategy,
                       "process_status": status, "return_code": code, "process_wall_ns": wall,
                       "scenario_sha256": manifest["cases"][key]["scenario_sha256"],
                       "command": command,
                       "stdout_path": str(stdout_path.relative_to(output)),
                       "stdout_sha256": sha(stdout_path),
                       "stderr_path": str(stderr_path.relative_to(output)),
                       "stderr_sha256": sha(stderr_path), "parse_error": parse_error,
                       "result": result}
                with attempts_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
    try:
        manifest["environment"]["load_average_at_end"] = list(os.getloadavg())
    except (AttributeError, OSError):
        manifest["environment"]["load_average_at_end"] = None
    manifest["environment"]["capture_completed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
