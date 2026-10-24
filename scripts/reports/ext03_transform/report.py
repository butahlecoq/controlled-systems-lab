"""Validation and saved-record HTML rendering for EXT-03 transform measurements."""
from __future__ import annotations
import hashlib
import json
import math
import statistics

SCHEMA = "csl.ext03-transform-record/1"

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def validate(record):
    errors=[]
    if not isinstance(record,dict) or record.get("schema")!=SCHEMA: return ["schema"]
    m=record.get("measurement",{})
    if not isinstance(m,dict): return ["measurement"]
    if m.get("measured_batches")!=7 or m.get("calls_per_batch")!=10 or m.get("checked_calls")!=70: errors.append("measurement_counts")
    if any(m.get(key)!=0 for key in ("failed_calls","missing_calls")): errors.append("incomplete_calls")
    values=m.get("microseconds_per_call",[])
    elapsed=m.get("batch_elapsed_ns",[])
    if not isinstance(values,list) or len(values)!=7 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in values): errors.append("trial_count_or_value")
    if not isinstance(elapsed,list) or len(elapsed)!=7 or any(not isinstance(v,int) or v<=0 for v in elapsed): errors.append("elapsed_count_or_value")
    if "trial_count_or_value" not in errors and "elapsed_count_or_value" not in errors:
        if statistics.median(values)!=m.get("median_microseconds_per_call"): errors.append("median")
        if min(values)!=m.get("min_microseconds_per_call") or max(values)!=m.get("max_microseconds_per_call"): errors.append("range")
    env=record.get("environment",{})
    if not isinstance(env,dict): errors.append("environment")
    elif env.get("source_commit")!=record.get("source_commit") or env.get("harness_sha256")!=record.get("harness_sha256"): errors.append("provenance")
    if record.get("limiter",{}).get("available") is not False: errors.append("limiter_claim")
    return errors

def render_html(record):
    m=record["measurement"]
    rows="".join(f"<tr><td>{i+1}</td><td>{value:.2f}</td><td>{m['batch_elapsed_ns'][i]}</td><td>10</td></tr>" for i,value in enumerate(m["microseconds_per_call"]))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>EXT-03 lift transform microbenchmark</title>"
      "<style>body{font:16px system-ui,sans-serif;max-width:900px;margin:3rem auto;padding:0 1rem;color:#18212b}table{border-collapse:collapse}td,th{padding:.5rem 1rem;border:1px solid #ccd2d8;text-align:right}td:first-child,th:first-child{text-align:left}.callout{padding:1rem;background:#edf5ff}</style></head><body>"
      "<h1>EXT-03 temporal-memory transform</h1><p class=\"callout\">Exploratory microbenchmark: transform and history recovery only. This is not a solver timing or comparison.</p>"
      "<figure><img src=\"visual.svg\" alt=\"Feasible two-control set under absolute and slew bounds, with the unique terminal-cost minimum at u0 zero and u1 minus one quarter\"><figcaption>Analytic illustration of the fixture constraints and terminal objective; this plot is derived from the saved fixture and is not a solver trace.</figcaption></figure>"
      f"<p>Median <strong>{m['median_microseconds_per_call']:.2f} μs per call</strong>; range <strong>{m['min_microseconds_per_call']:.2f}–{m['max_microseconds_per_call']:.2f} μs</strong>. Seven measured batches of ten calls followed one excluded warmup batch. All 70 calls passed.</p>"
      "<p>The limiter was not source-profiled. No speedup, application-scale or scalability claim is made.</p>"
      f"<table><thead><tr><th>Batch</th><th>μs/call</th><th>Elapsed ns</th><th>Checked calls</th></tr></thead><tbody>{rows}</tbody></table>"
      "<p><a href=\"raw-events.jsonl\">Raw events</a> · <a href=\"records.json\">Record</a> · <a href=\"environment.json\">Environment</a> · <a href=\"manifest.json\">Manifest</a> · <a href=\"README.md\">README</a> · <a href=\"trials.csv\">Batch table</a></p></body></html>")
