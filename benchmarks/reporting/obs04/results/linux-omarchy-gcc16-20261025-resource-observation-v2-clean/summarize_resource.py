#!/usr/bin/env python3
"""Validate and summarize five saved OBS-04 process resource observations."""
import importlib.util
import json
from pathlib import Path
import statistics

root = Path(__file__).resolve().parents[5]
results = Path(__file__).resolve().parent
renderer_spec = importlib.util.spec_from_file_location(
    "obs04_resource_summary_renderer", root / "scripts/reports/obs04/render_saved.py"
)
renderer = importlib.util.module_from_spec(renderer_spec)
renderer_spec.loader.exec_module(renderer)

observations = []
record_summaries = []
for run_id in ("01", "02", "03", "04", "05"):
    run_dir = results / f"run-{run_id}"
    observation = json.loads((run_dir / "resource-observation.json").read_text(encoding="utf-8"))
    record = renderer.load_record(run_dir / "comparison.json")
    if observation["exit_code"] != 0 or observation["stderr_bytes"] != 0:
        raise SystemExit(f"run {run_id} exited unsuccessfully or wrote stderr")
    manifest_binary = record["_parsed_spec"]["environment"]["runtime"]["binary_sha256"]
    if (manifest_binary.get("status") != "available" or
            observation["binary_sha256"] != manifest_binary.get("value")):
        raise SystemExit(f"run {run_id} binary hash disagrees with the comparison manifest")
    if len(record["_parsed_attempts"]) != 32 or any(
        attempt["reported_status"] != "completed" for attempt in record["_parsed_attempts"]
    ):
        raise SystemExit(f"run {run_id} did not complete all 32 attempts")
    stdout_lines = (run_dir / "driver.stdout.log").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in stdout_lines if line.startswith('{"schema":')]
    if len(events) != 32 or any(event.get("status") != "passed" for event in events):
        raise SystemExit(f"run {run_id} stdout does not confirm all 32 attempts passed")
    spec = record["_parsed_spec"]
    build = spec["environment"]["build"]
    if build["source_dirty"] or build["source_revision"] != "9994eef03eeae456a89e041b9cac6b7518ba77b4":
        raise SystemExit(f"run {run_id} did not use the expected clean source snapshot")
    observations.append(observation)
    record_summaries.append({
        "run": run_id,
        "comparison_run_id": record["comparison_run_id"],
        "attempts": len(record["_parsed_attempts"]),
        "record_bytes": observation["record_bytes"],
    })

binary_hashes = {item["binary_sha256"] for item in observations}
spec_texts = {
    json.loads((results / f"run-{run_id}" / "comparison.json").read_text(encoding="utf-8"))["spec"]
    for run_id in ("01", "02", "03", "04", "05")
}
first_spec = json.loads(next(iter(spec_texts)))
source_info = first_spec["environment"]["build"]
if len(binary_hashes) != 1 or len(spec_texts) != 1:
    raise SystemExit("resource runs do not share the same binary and comparison specification")

def stats(field):
    values = [item[field] for item in observations]
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}

summary = {
    "schema": "csl.obs04-process-resource-summary/1",
    "run_count": len(observations),
    "source_revision": source_info["source_revision"],
    "source_dirty": source_info["source_dirty"],
    "source_tree_sha256": source_info["source_tree_sha256"],
    "binary_sha256": next(iter(binary_hashes)),
    "peak_rss_kib": stats("max_rss_kib"),
    "elapsed_wall_ns": stats("elapsed_wall_ns"),
    "user_cpu_seconds": stats("user_cpu_seconds"),
    "system_cpu_seconds": stats("system_cpu_seconds"),
    "attempts_completed_per_process": 32,
    "records": record_summaries,
}
(results / "resource-summary.json").write_text(
    json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
(results / "run-01" / "comparison.report.html").write_text(
    renderer.render_html(renderer.load_record(results / "run-01" / "comparison.json")),
    encoding="utf-8",
)
print(json.dumps(summary, sort_keys=True))
