#!/usr/bin/env python3
"""Validate the published GEO-03 saved-data bundle without running native code."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path

SCHEMA="csl.geo03-hv-report/1"

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(root:Path)->None:
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"]=="csl.geo03-report-manifest/1"
    assert manifest["report_id"]==json.loads((root/"records.json").read_text(encoding="utf-8"))["report_id"]
    for name,expected in manifest["files"].items():
        path=root/name
        assert path.is_file(),f"missing manifested file {name}"
        assert digest(path)==expected,f"hash mismatch: {name}"
    wrapper=json.loads((root/"records.json").read_text(encoding="utf-8"))
    assert wrapper["schema"]==SCHEMA
    payload=wrapper["payload"]
    assert payload["schema"]==SCHEMA
    actual=hashlib.sha256(canonical(payload)).hexdigest()
    assert wrapper["payload_sha256"]==actual
    expected_id=f"geo03-{payload['created_utc'][:10].replace('-','')}-{actual[:12]}"
    assert wrapper["report_id"]==expected_id
    trials=payload["trials"]
    measure=payload["measurement"]
    assert measure["repetitions"]>=5 and measure["warmups"]>=1
    assert len(trials)==measure["repetitions"]*8==measure["emitted_trials"]
    assert measure["expected_trials"]==len(trials)
    assert measure["failures"]==0 and measure["process_return_code"]==0
    keys={(x["fixture"],x["direction"]) for x in trials}
    assert len(keys)==8
    assert all(x["oracle_passed"]=="true" and x["oracle_checks"]>0 for x in trials)
    assert all(x["run_ns"]>0 and x["total_ns"]>=x["run_ns"] for x in trials)
    raw=[json.loads(line) for line in (root/"raw-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert raw==trials
    with (root/"trials.csv").open(newline="",encoding="utf-8") as stream: csv_rows=list(csv.DictReader(stream))
    assert len(csv_rows)==len(trials)
    summary=payload["summary"]
    assert len(summary)==8
    for group in summary:
        rows=[r for r in trials if (r["fixture"],r["direction"])==(group["fixture"],group["direction"])]
        assert len(rows)==measure["repetitions"]==group["trials"]
        values=sorted(int(r["run_ns"]) for r in rows)
        median=values[len(values)//2] if len(values)%2 else (values[len(values)//2-1]+values[len(values)//2])//2
        assert group["run_ns"]["median"]==median
        assert group["run_ns"]["min"]==values[0] and group["run_ns"]["max"]==values[-1]
        assert group["all_oracles_passed"]
    html=(root/"index.html").read_text(encoding="utf-8")
    assert "<svg" in html and "<!doctype html>" in html.lower()
    assert not re.search(r'(?:href|src)=["\']https?://',html,re.I)
    assert payload["limiter_profile"]["profiled_operations"]>0
    assert (root/"profile.txt").stat().st_size>0
    assert "no accepted workload-size baseline" in " ".join(payload["scope_limitations"])

    archive=root.parent/(wrapper["report_id"]+".zip")
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist())==set(manifest["files"])|{"manifest.json"}
        assert zf.testzip() is None
        for name,expected in manifest["files"].items():
            assert hashlib.sha256(zf.read(name)).hexdigest()==expected,f"ZIP hash mismatch: {name}"
    print(f"VALID {wrapper['report_id']}: {len(trials)} trials, 8 independent-oracle groups, {len(manifest['files'])} hashed bundle files")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("report_dir",type=Path);args=parser.parse_args();validate(args.report_dir)
