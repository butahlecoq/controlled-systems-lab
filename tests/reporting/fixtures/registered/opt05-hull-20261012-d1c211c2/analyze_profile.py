#!/usr/bin/env python3
"""Retain only the benchmark process's symbolized sample rows from xperf output."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xperf", type=Path, required=True)
    ap.add_argument("--workload", type=Path, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    row = re.compile(r"^csl_hull_measure\.exe \(\s*\d+\),\s*(\d+),\s*([\d.]+),\s*(.+)$")
    target = Counter()
    target_percent = 0.0
    for line in args.xperf.read_text(encoding="utf-8", errors="replace").splitlines():
        match = row.match(line)
        if match:
            weight, system_percent, function = match.groups()
            target[function.strip()] += int(weight)
            target_percent += float(system_percent)
    total_match = re.search(r"Total Weight:\s*(\d+)", args.xperf.read_text(encoding="utf-8", errors="replace"))
    total_weight = int(total_match.group(1)) if total_match else None
    target_weight = sum(target.values())
    if target_weight == 0:
        raise SystemExit("xperf export contains no target-process CPU sample rows")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["function_or_module", "sample_weight", "share_of_target_process_samples_percent", "xperf_system_usage_percent"])
        for function, weight in target.most_common():
            writer.writerow([function, weight, f"{100 * weight / target_weight:.4f}", ""])
    profile_summary = {
        "schema": "csl.hull-limiter-profile/1",
        "profile_workload": [json.loads(line) for line in args.workload.read_text(encoding="utf-8").splitlines() if line.strip()],
        "sampling": {
            "method": "WPR CPU sampled profile; xperf symbol-resolved flat process/function attribution",
            "instrumentation_is_separate_from_reported_trials": True,
            "target_process_sample_weight": target_weight,
            "all_process_sample_weight": total_weight,
            "target_share_of_all_recorded_sample_weight_percent": round(100 * target_weight / total_weight, 3) if total_weight else None,
            "target_cpu_usage_percent_over_trace_from_xperf": round(target_percent, 3),
            "trace_sha256": sha256(args.trace),
            "trace_bytes": args.trace.stat().st_size,
            "function_rows": len(target),
            "attribution_limit": "Flat sampled leaf functions; no call-stack attribution or per-call phase timing. Workload includes reducer setup/output consumption; it suppresses per-call serialization and full certificate replay. Function shares guide source inspection and are not exclusive wall-time fractions.",
            "external_process_names": "excluded from exported CSV",
        },
        "top_target_functions": [{"name": name, "sample_weight": weight,
                                  "share_percent": round(100 * weight / target_weight, 3)}
                                 for name, weight in target.most_common(20)],
    }
    args.out.with_suffix(".json").write_text(json.dumps(profile_summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
