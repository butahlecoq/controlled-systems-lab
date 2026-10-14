"""Build a separate immutable SYN-03 Strategy A T-S02 native bundle from saved measurements."""
from __future__ import annotations
import argparse,csv,hashlib,json,shutil
from pathlib import Path
import report
import provenance

def write_json(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--collection",type=Path,required=True);parser.add_argument("--out",type=Path,required=True);args=parser.parse_args()
    collection=args.collection.resolve(strict=True);out=args.out.resolve()
    if out.exists():raise SystemExit("immutable report output already exists")
    measurement=json.loads((collection/"collection.json").read_text(encoding="utf-8"))
    commands=json.loads((collection/"commands.json").read_text(encoding="utf-8"))
    evidence={name:(collection/"build-evidence"/name).read_bytes() for name in provenance.EVIDENCE_KEYS}
    measurement,commands,evidence=provenance.sanitize_collection(measurement,commands,evidence)
    measurement["build"]["sanitization"]["original_collection_sha256"]=hashlib.sha256((collection/"collection.json").read_bytes()).hexdigest()
    measurement["build"]["sanitization"]["original_commands_sha256"]=hashlib.sha256((collection/"commands.json").read_bytes()).hexdigest()
    events=[json.loads(line) for line in (collection/"events.jsonl").read_text(encoding="utf-8").splitlines()]
    record={"schema":report.SCHEMA,"report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,"harness_commit":measurement["harness_commit"],
        "algorithm":report.ALGORITHM,"scenario":{"value":report.EXPECTED_SCENARIO,"sha256":report.digest(report.EXPECTED_SCENARIO)},"canonical_relation":report.RELATION,
        "assumptions":report.EXPECTED_ASSUMPTIONS,"evidence_limits":report.EXPECTED_EVIDENCE_LIMITS,"measurement":{k:v for k,v in measurement.items() if k not in ("schema","raw_stdout_sha256","raw_stderr_sha256")}|{"events":events},
        "environment":measurement["environment"],"build":measurement["build"]}
    errors=report.validate(record)
    if errors:raise SystemExit("invalid collection: "+", ".join(errors))
    out.mkdir(parents=True)
    for name,value in {"records.json":record,"scenarios.json":record["scenario"],"measurement.json":record["measurement"],"environment.json":record["environment"],"build-provenance.json":record["build"],"profile.json":record["measurement"]["profile_attempt"]}.items():write_json(out/name,value)
    for source,dest in {"events.jsonl":"measurement-events.jsonl","process-stderr.txt":"process-stderr.txt","separate-profile-events.jsonl":"separate-profile-events.jsonl","separate-profile-stderr.txt":"separate-profile-stderr.txt"}.items():shutil.copyfile(collection/source,out/dest)
    write_json(out/"commands.json",commands)
    (out/"build-evidence").mkdir()
    for name,data in evidence.items():(out/"build-evidence"/name).write_bytes(data)
    with (out/"trials.csv").open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=report.CSV_FIELDS,lineterminator="\n");writer.writeheader();writer.writerows({key:e[key] for key in report.CSV_FIELDS} for e in events)
    (out/"index.html").write_text(report.render_html(record),encoding="utf-8",newline="\n")
    (out/"README.md").write_text(f"# SYN-03 Strategy A T-S02\n\nMeasured solver source `{report.SOURCE_COMMIT}`; harness `{record['harness_commit']}`. One excluded warmup and seven successful complete-family observations. Objective identically 3; canonical full joint-history relation and two distinct histories sharing terminal state 1 checked each time. Single-profile exploratory evidence; no speedup or native solver latency claim; #66 remains open.\n\nThe separately profiled workload is excluded. No source-mapped limiter is established. Commands and compiler/build evidence use portable root placeholders. Build provenance preserves original evidence hashes separately from sanitized-file hashes; source, executable, harness and dependency hashes are unchanged. Reproduce with tooling/syn03_ts02/collect.py then build_bundle.py; schema-3 publication uses syn03_ts02_registered_reports.py. Rendering and staging use saved records only. Publication/live verification remain pending until main-only deployment.\n",encoding="utf-8",newline="\n")
    for path in out.rglob("*"):
        if path.is_file():provenance.assert_public_bytes(path.read_bytes(),path.relative_to(out).as_posix())
    files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob("*")) if p.is_file()}
    write_json(out/"manifest.json",{"schema":"csl.syn03-strategy-a-ts02-manifest/1","report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,"harness_commit":record["harness_commit"],"files":files})
    print(report.REPORT_ID)
if __name__=="__main__":main()
