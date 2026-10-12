#!/usr/bin/env python3
"""Collect and render the versioned, single-adapter GEO-03 fixture report."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import math
import os
import platform
import statistics
import subprocess
import zipfile
from pathlib import Path

SCHEMA = "csl.geo03-hv-report/1"
CONVERTER = {"id": "csl.conversion.qhull", "version": "1.0.0+qhull.8.0.2"}
LP = {"id": "csl.lp.highs", "version": "1.0.0+highs.1.11.0"}
FIXTURES = {
    "square": {"dimension": 2, "inequalities": 4, "equalities": 0, "vertices": 4, "rays": 0,
               "analytic_set": "[0,1] x [0,1]", "oracle": "vertex membership plus support in five literal directions"},
    "simplex": {"dimension": 2, "inequalities": 3, "equalities": 0, "vertices": 3, "rays": 0,
                "analytic_set": "x>=0, y>=0, x+y<=1", "oracle": "vertex membership plus support in four literal directions"},
    "embedded-segment": {"dimension": 2, "inequalities": 2, "equalities": 1, "vertices": 2, "rays": 0,
                         "analytic_set": "{(x,0): -1<=x<=2}", "oracle": "endpoint/interior/off-set membership plus support directions"},
    "singleton": {"dimension": 2, "inequalities": 0, "equalities": 2, "vertices": 1, "rays": 0,
                  "analytic_set": "{(2,-3)}", "oracle": "literal singleton/nearby-point membership plus support directions"},
}
EXPECTED_ROWS = {(name, direction) for name in FIXTURES for direction in ("H-to-V", "V-to-H")}
TIMING_FIELDS = ("preparation_ns", "workspace_creation_ns", "run_ns", "total_ns")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_text(argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return result.returncode, result.stdout, result.stderr


def ps_json(script: str) -> object:
    code, out, err = run_text(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
    if code:
        return {"unavailable": err.strip() or f"PowerShell exited {code}"}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out.strip()


def environment_snapshot(before: dict, after: dict) -> dict:
    processor = ps_json("(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name) | ConvertTo-Json -Compress")
    memory = ps_json("(Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory) | ConvertTo-Json -Compress")
    cmake_code, cmake_out, _ = run_text(["cmake", "--version"])
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "processor": processor,
        "logical_processors": os.cpu_count(),
        "physical_memory": memory,
        "total_processor_utilization_percent_snapshot_before": before["total_processor_utilization_percent"],
        "total_processor_utilization_percent_snapshot_after": after["total_processor_utilization_percent"],
        "processor_queue_length_snapshot_before": before["processor_queue_length"],
        "processor_queue_length_snapshot_after": after["processor_queue_length"],
        "top_processes_snapshot_before": before["top_processes"],
        "top_processes_snapshot_after": after["top_processes"],
        "cmake_version": cmake_out.splitlines()[0] if cmake_code == 0 and cmake_out else "unavailable",
        "build_configuration": "Release",
        "compiler": "MSVC 19.44.35215.0 (Visual Studio 17 2022 x64)",
        "native_dependencies": {"qhull": "8.0.2", "highs": "1.11.0"},
    }


def load_snapshot() -> dict:
    processor = ps_json("Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor | Where-Object Name -eq '_Total' | Select-Object -First 1 PercentProcessorTime | ConvertTo-Json -Compress")
    queue = ps_json("Get-CimInstance Win32_PerfFormattedData_PerfOS_System | Select-Object -First 1 ProcessorQueueLength | ConvertTo-Json -Compress")
    processes = ps_json("Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 ProcessName,CPU,WorkingSet64 | ConvertTo-Json -Compress")
    return {"total_processor_utilization_percent":processor,"processor_queue_length":queue,"top_processes":processes}


def summarize(rows: list[dict]) -> list[dict]:
    summary = []
    for fixture, direction in sorted(EXPECTED_ROWS):
        group = [r for r in rows if (r["fixture"], r["direction"]) == (fixture, direction)]
        entry = {"fixture": fixture, "direction": direction, "trials": len(group), "failures": 0,
                 "all_oracles_passed": all(r["oracle_passed"] == "true" for r in group)}
        for field in TIMING_FIELDS:
            values = [int(r[field]) for r in group]
            entry[field] = {"unit": "ns", "median": int(statistics.median(values)), "min": min(values), "max": max(values), "range": max(values)-min(values)}
        entry["input"] = {key: int(group[0][key]) for key in ("ambient_dimension", "input_inequalities", "input_equalities", "input_vertices", "input_rays")}
        entry["output"] = {key: int(group[0][key]) for key in ("output_inequalities", "output_equalities", "output_vertices", "output_rays")}
        entry["oracle_checks_per_trial"] = int(group[0]["oracle_checks"])
        summary.append(entry)
    return summary


def svg_chart(summary: list[dict]) -> str:
    width, height, left, right = 980, 450, 285, 920
    minimum, maximum = 1_000, 10_000_000
    def x(value: int) -> float:
        ratio=(math.log10(max(minimum,min(maximum,value)))-math.log10(minimum))/(math.log10(maximum)-math.log10(minimum))
        return left+ratio*(right-left)
    rows=[]
    for index, entry in enumerate(summary):
        y=66+index*44
        rows.append(f'<text x="8" y="{y+4:.0f}" font-size="13">{html.escape(entry["fixture"])} {html.escape(entry["direction"])}</text>')
        t=entry["run_ns"]; start=x(t["min"]); end=x(t["max"]); med=x(t["median"])
        rows.append(f'<line x1="{start:.1f}" y1="{y}" x2="{end:.1f}" y2="{y}" stroke="#64748b" stroke-width="3"/><circle cx="{med:.1f}" cy="{y}" r="6" fill="#0f766e"/><text x="{min(right-4,med+10):.1f}" y="{y+4}" font-size="12">{t["median"]/1000:.2f} µs</text>')
    ticks=[]
    for value,label in ((1_000,"1 µs"),(10_000,"10 µs"),(100_000,"100 µs"),(1_000_000,"1 ms"),(10_000_000,"10 ms")):
        xpos=x(value)
        ticks.append(f'<line x1="{xpos:.1f}" y1="35" x2="{xpos:.1f}" y2="410" stroke="#e2e8f0"/><text x="{xpos:.1f}" y="28" text-anchor="middle" font-size="12">{label}</text>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 450" role="img" aria-label="Run time medians and ranges on a logarithmic axis">'+'<rect width="100%" height="100%" fill="white"/>'+''.join(ticks)+''.join(rows)+'<text x="285" y="438" font-size="12">workspace->run elapsed time (logarithmic axis; whisker=min to max; marker=median; 7 trials)</text></svg>'


def render_html(report: dict, summary: list[dict], svg: str) -> str:
    p=report["payload"]
    rows=[]
    for item in summary:
        rows.append("<tr>"+"".join(f"<td>{html.escape(str(value))}</td>" for value in (
            item["fixture"],item["direction"],item["trials"],f'{item["run_ns"]["median"]/1000:.2f} µs',
            f'{item["run_ns"]["min"]/1000:.2f}–{item["run_ns"]["max"]/1000:.2f} µs',
            f'{item["total_ns"]["median"]/1000:.2f} µs',"pass" if item["all_oracles_passed"] else "FAIL"))+"</tr>")
    fixture_rows="".join(f"<tr><td>{html.escape(name)}</td><td>R^{meta['dimension']}</td><td>{meta['inequalities']} / {meta['equalities']}</td><td>{meta['vertices']} / {meta['rays']}</td><td>{html.escape(meta['analytic_set'])}</td></tr>" for name,meta in FIXTURES.items())
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GEO-03 H/V contract-fixture conversion report</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}h1,h2{{line-height:1.2}}.note{{background:#f1f5f9;padding:1rem;border-left:4px solid #0f766e}}table{{border-collapse:collapse;width:100%;font-size:.92rem}}th,td{{border-bottom:1px solid #cbd5e1;padding:.45rem;text-align:left}}th{{background:#f8fafc}}code{{overflow-wrap:anywhere}}svg{{width:100%;height:auto;border:1px solid #e2e8f0}}a{{color:#075985}}</style></head>
<body><h1>GEO-03: H/V conversion contract-fixture report</h1>
<p><strong>Scope:</strong> one native C++20 adapter, four tiny 2D contract fixtures, both conversion directions. No competitor comparison or speedup claim.</p>
<div class="note"><strong>Interpretation:</strong> descriptive microbenchmark only. These fixtures exercise the current contract; no accepted workload-size baseline exists, so these measurements do not predict representative user workloads, scaling, or application-level latency. Floating-point membership/support checks are numerical oracles, not validated global certificates.</div>
<p>Report <code>{html.escape(report['report_id'])}</code>; schema <code>{SCHEMA}</code>; generated {html.escape(p['created_utc'])}. Runtime base commit <code>{html.escape(p['runtime_source_commit'])}</code>; report/harness commit <code>{html.escape(p['report_source_commit'])}</code>.</p>
<h2>Measured adapter</h2><p><code>{CONVERTER['id']}@{CONVERTER['version']}</code>; selected LP backend <code>{LP['id']}@{LP['version']}</code>. Native Qhull {p['environment']['native_dependencies']['qhull']}; HiGHS {p['environment']['native_dependencies']['highs']}.</p>
<h2>Workload</h2><p>{p['measurement']['repetitions']} measured trials per case, {p['measurement']['warmups']} excluded warmup per case, eight cases interleaved forward/reverse by round; all {p['measurement']['expected_trials']} measured conversions completed and passed their independent checks.</p>
<table><thead><tr><th>Fixture</th><th>Space</th><th>Input inequalities/equalities</th><th>Vertices/rays</th><th>Analytic set</th></tr></thead><tbody>{fixture_rows}</tbody></table>
<h2>Conversion time</h2><p>Timed region: <code>RepresentationConverterWorkspace::run</code>, after input creation, selection/preparation and worker creation; those stages are reported separately in raw trials. End-to-end below is the measured harness pipeline from registration/input creation through conversion return, before independent verification and destruction.</p>{svg}
<table><thead><tr><th>Fixture</th><th>Direction</th><th>Trials</th><th>Run median</th><th>Run min–max</th><th>Pipeline median</th><th>Independent checks</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>All timings use a steady clock and are reported as descriptive samples. Range is min–max, not a confidence interval. Setup phases are nested/exclusive only as defined in raw timing boundaries; they must not be summed to infer a different boundary.</p>
<h2>Limiter evidence</h2><p>{html.escape(p['limiter_profile']['finding'])} Profile duration and profiled operations are separate from the reported trials. The bundle contains the sanitized target-process module summary; the host-wide ETW trace is retained locally and is not redistributed.</p>
<h2>Environment and build</h2><pre>{html.escape(json.dumps(p['environment'],indent=2,ensure_ascii=False))}</pre><p>Build log, source/dependency hashes, exact commands, environment snapshots, raw JSONL, full CSV trials, summary and profile evidence are linked in the bundle.</p>
<h2>Limitations</h2><ul><li>Only 2D square, simplex, embedded segment and singleton contract fixtures are measured; all have at most four vertices.</li><li>Ray-bearing V inputs, unbounded sets, empty sets, higher-dimensional sets and large facet counts are unsupported by the selected bounded-only adapter and were excluded from timing.</li><li>No comparison adapter is available in this report; no speedup or rank claim is made.</li><li>The selected implementation uses binary64 reductions, LP prerequisite checks and Qhull 8.0.2. Support/equivalence evidence remains numerical and non-certified.</li><li>No conversion decomposition into LP, affine reduction and Qhull substage timings is exposed. ETW was resolved to modules but not functions, so it cannot identify a per-stage algorithmic limiter.</li><li>Historical A17/A18 lineage and executable equivalence are not audited here.</li></ul>
<h2>Raw data and offline bundle</h2><ul><li><a href="records.json">Versioned report records</a></li><li><a href="raw-events.jsonl">Raw trial records</a></li><li><a href="trials.csv">Trial table</a></li><li><a href="summary.csv">Summary table</a></li><li><a href="scenarios.json">Analytic fixture definitions</a></li><li><a href="profile.txt">External CPU sample profile notes</a></li></ul>
</body></html>'''


def write_artifacts(out: Path, rows: list[dict], args: argparse.Namespace, env: dict, stdout: str, stderr: str) -> str:
    out.mkdir(parents=True, exist_ok=False)
    created=utc_now()
    for row in rows:
        row["oracle_passed"] = row["oracle_passed"].lower()
        for key in ("round","ambient_dimension","input_inequalities","input_equalities","input_vertices","input_rays",
                    "preparation_ns","workspace_creation_ns","run_ns","total_ns","output_inequalities","output_equalities",
                    "output_vertices","output_rays","oracle_checks"):
            row[key]=int(row[key])
    summaries=summarize(rows)
    payload={
        "schema":SCHEMA,"created_utc":created,"runtime_source_commit":args.runtime_commit,
        "report_source_commit":args.report_commit,"converter":CONVERTER,"lp_backend":LP,
        "environment":env,
        "measurement":{"repetitions":args.repetitions,"warmups":args.warmups,"expected_trials":args.repetitions*len(EXPECTED_ROWS),
                        "emitted_trials":len(rows),"process_return_code":0,"failures":0,
                        "order":"fixtures/directions forward on even rounds and reverse on odd rounds",
                        "timed_region":"RepresentationConverterWorkspace::run", "oracle_outside_timing":True},
        "scenarios":FIXTURES,"trials":rows,"summary":summaries,
        "limiter_profile":{"profiled_operations":args.profile_operations,"method":"Windows Performance Recorder CPU ETW sampling; separate untimed executable mode; independent oracle omitted, output representation/status consumed",
                           "finding":args.profile_finding,"trace_redistributed":False,"profile_summary_file":"profile.txt"},
        "scope_limitations":["contract fixtures only; no accepted workload-size baseline","bounded H/V cases only","no available competing adapter","numerical checks are not validated global certificates","no inner conversion phase timing","A17/A18 lineage not audited"]
    }
    digest=hashlib.sha256(canonical(payload)).hexdigest()
    report_id=f"geo03-{created[:10].replace('-','')}-{digest[:12]}"
    wrapper={"schema":SCHEMA,"report_id":report_id,"payload_sha256":digest,"payload":payload}
    (out/"records.json").write_text(json.dumps(wrapper,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    (out/"raw-events.jsonl").write_text("".join(json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n" for row in rows),encoding="utf-8")
    with (out/"trials.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (out/"summary.csv").open("w",newline="",encoding="utf-8") as stream:
        fields=["fixture","direction","trials","failures","all_oracles_passed"]+[f"{field}_{suffix}" for field in TIMING_FIELDS for suffix in ("median_ns","min_ns","max_ns","range_ns")]
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for item in summaries:
            row={k:item[k] for k in ("fixture","direction","trials","failures","all_oracles_passed")}
            for field in TIMING_FIELDS:
                for suffix,key in (("median_ns","median"),("min_ns","min"),("max_ns","max"),("range_ns","range")):
                    row[f"{field}_{suffix}"]=item[field][key]
            writer.writerow(row)
    (out/"scenarios.json").write_text(json.dumps(FIXTURES,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (out/"environment.json").write_text(json.dumps(env,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (out/"process-stderr.txt").write_text(stderr,encoding="utf-8")
    (out/"raw-driver-output.csv").write_text(stdout,encoding="utf-8")
    (out/"measurement-command.txt").write_text("\n".join(args.command)+"\n",encoding="utf-8")
    (out/"build-provenance.txt").write_text(args.build_provenance.read_text(encoding="utf-8",errors="replace"),encoding="utf-8")
    (out/"profile.txt").write_text(args.profile_summary.read_text(encoding="utf-8",errors="replace"),encoding="utf-8")
    svg=svg_chart(summaries)
    (out/"latency.svg").write_text(svg,encoding="utf-8")
    (out/"index.html").write_text(render_html(wrapper,summaries,svg),encoding="utf-8")
    (out/"README.md").write_text(f"# {report_id}\n\nOffline GEO-03 H/V contract-fixture report. Open `index.html`; raw numerical measurements and validation inputs are beside it.\n\nSchema: `{SCHEMA}`. Runtime base: `{args.runtime_commit}`. Report/harness source: `{args.report_commit}`. No competing adapter, speedup, production-size, or certified-global-equivalence claim is made.\n",encoding="utf-8")
    manifest={"schema":"csl.geo03-report-manifest/1","report_id":report_id,
              "files":{p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!="manifest.json"}}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    zip_path=out.parent/(report_id+".zip")
    with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(out.iterdir()): archive.write(path,path.name)
    return report_id


def collect(args: argparse.Namespace) -> None:
    if args.repetitions<5: raise SystemExit("repetitions must be >= 5")
    if args.warmups<1: raise SystemExit("warmups must be >= 1")
    before=load_snapshot()
    status,stdout,stderr=run_text([str(args.exe),"--repetitions",str(args.repetitions),"--warmups",str(args.warmups)])
    after=load_snapshot()
    args.command=[str(args.exe),"--repetitions",str(args.repetitions),"--warmups",str(args.warmups)]
    if status: raise SystemExit(f"measurement executable failed with {status}; preserve stderr and partial stdout before retry")
    rows=list(csv.DictReader(stdout.splitlines()))
    if len(rows)!=args.repetitions*len(EXPECTED_ROWS): raise SystemExit(f"expected {args.repetitions*len(EXPECTED_ROWS)} measured rows, got {len(rows)}")
    seen={(r["fixture"],r["direction"]) for r in rows}
    if seen!=EXPECTED_ROWS or any(r["oracle_passed"]!="true" for r in rows): raise SystemExit("scenario roster or independent oracle validation failed")
    for key,value in (("converter_id",CONVERTER["id"]),("converter_version",CONVERTER["version"]),("lp_backend_id",LP["id"]),("lp_backend_version",LP["version"])):
        if any(r[key]!=value for r in rows): raise SystemExit(f"unexpected measured adapter identity: {key}")
    report_id=write_artifacts(args.out,rows,args,environment_snapshot(before,after),stdout,stderr)
    print(report_id)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--repetitions",type=int,default=7)
    parser.add_argument("--warmups",type=int,default=1)
    parser.add_argument("--runtime-commit",required=True)
    parser.add_argument("--report-commit",required=True)
    parser.add_argument("--profile-operations",type=int,required=True)
    parser.add_argument("--profile-finding",required=True)
    parser.add_argument("--profile-summary",type=Path,required=True)
    parser.add_argument("--build-provenance",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    collect(args)
    return 0


if __name__=="__main__": raise SystemExit(main())
