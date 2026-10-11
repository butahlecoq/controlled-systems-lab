"""Offline HTML/CSV export from a saved, validated report view."""
from __future__ import annotations
import argparse
import csv
from html import escape
import json
from pathlib import Path
import shutil
import time

import report_data as data


def csv_text(value):
    text = str(value)
    return "'"+text if text.lstrip().startswith(("=","+","-","@","\t","\r")) else text


def _csv(path, fields, rows):
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


DOCUMENT_POLICY="csl.report-document/1"


def csv_projection(view):
    """Pure complete CSV projection of the saved view, shared with consumers."""
    p=view["payload"];groups=data.aggregate(view)
    trial_rows=[]
    for trial in p["trials"]:
        result=trial["result"]
        row={"case_id":csv_text(trial["case_id"]),"round":trial["round"],"sequence":trial["sequence"],
             "harness":trial["harness"]["status"],"termination":result["termination"] if result else "unavailable",
             "outcome":result["outcome"] if result else "unavailable","support":"unestablished" if result else "unavailable",
             "original_objective":result["original_objective"] if result and result["original_objective"] is not None else "",
             "validation_passed":trial["validation"]["passed"],
             "end_to_end_scope":trial["timings"]["end_to_end"].get("scope","unavailable"),
             "row_residual":result["primal_residuals"]["rows"]["violation"] if result and result["primal_residuals"] else "",
             "variable_residual":result["primal_residuals"]["variables"]["violation"] if result and result["primal_residuals"] else "",
             "diagnostics":csv_text(result["raw_diagnostics"] if result else trial["harness"]["error"] or "")}
        for phase in data.PHASES:
            interval=trial["timings"][phase]
            row[phase+"_ns"]=interval["duration_ns"] if interval["available"] else ""
        trial_rows.append(row)
    fields=["case_id","round","sequence","harness","termination","outcome","support","original_objective","validation_passed","end_to_end_scope","row_residual","variable_residual","diagnostics"]+[x+"_ns" for x in data.PHASES]
    summary=[]
    for group in groups:
        for phase in data.PHASES:
            stat=group["phases"][phase]
            summary.append({**{k:group[k] for k in ("case_id","expected","attempts","matched","failed","missing","unsupported","cancelled","valid")},
                            "phase":phase,"unit":"ns","median":stat["median"] if stat else "","min":stat["min"] if stat else "","max":stat["max"] if stat else ""})
    return fields,trial_rows,list(summary[0]),summary


def document(view,svg="",artifact_ref="main"):
    """Deterministic offline document; performs no I/O and executes no solver."""
    p=view["payload"];groups=data.aggregate(view);summary=csv_projection(view)[3]
    e=lambda value:escape(str(value),quote=True)
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>Reference LP algorithm report</title><style>body{max-width:1100px;margin:auto;padding:1.2rem;font:16px/1.5 system-ui;color:#172235;background:#fafbfd}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:.45rem;border:1px solid #ccd4de;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f6;padding:1rem}.scroll{overflow:auto}svg{max-width:100%;height:auto}.bad{color:#9b1928;font-weight:bold}a{color:#174d8c}</style></head><body>',
           '<h1>Registered HiGHS reference LP</h1>',
           '<p><strong>'+('TEST DATA — functional or literal fixture, not benchmark evidence.' if p["purpose"]=='test' else 'Single-adapter Release latency report; no competitor or speedup claim.')+'</strong></p>',
           '<p>Report '+e(view["report_id"])+'. Source <code>'+e(p["provenance"]["source_commit"])+'</code>. Outcome support: unestablished. Numerical matches to analytic references are not validated arithmetic certificates or a complete optimizer family.</p>',
           '<p><a href="https://github.com/butahlecoq/controlled-systems-lab/tree/'+p["provenance"]["source_commit"]+'">Measured/test source (external)</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/123">Report specification (external)</a></p>',
           '<h2>Numerical cases</h2><p>All authored coefficients and bounds are saved in scenarios.json. The returned-result column identifies the first trial; every trial, including failures, appears below and in CSV. Complementarity, certificates and complete minimizer families are unavailable.</p><div class="scroll"><table><thead><tr><th>Case</th><th>Analytic reference</th><th>Reference objective</th><th>First returned trial</th><th>Matched / expected</th><th>Failed / missing</th><th>Validity</th></tr></thead><tbody>']
    for scenario,group in zip(p["scenarios"],groups):
        ref=scenario["reference"]
        first=next((t for t in p["trials"] if t["case_id"]==scenario["case_id"]),None)
        observed=first["result"] if first else None
        displayed={k:observed[k] for k in ("termination","outcome","primal","original_objective")} if observed else {"status":"unavailable"}
        if observed and observed["primal_residuals"]:
            displayed["row_violation"]=observed["primal_residuals"]["rows"]["violation"]
            displayed["variable_violation"]=observed["primal_residuals"]["variables"]["violation"]
        parts.append('<tr><td>'+e(scenario["case_id"])+'</td><td>'+e(ref["outcome"])+': '+e(ref["derivation"])+'</td><td>'+e(ref["objective"] if ref["objective"] is not None else 'unavailable — '+ref["outcome"] )+'</td><td>'+e(json.dumps(displayed,ensure_ascii=False))+'</td><td>'+e(f'{group["matched"]}/{group["expected"]}')+'</td><td>'+e(f'{group["failed"]}/{group["missing"]}')+'</td><td>'+('matches analytic reference' if group["valid"] else '<span class="bad">INVALID FOR BENCHMARK</span>')+'</td></tr>')
    parts += ['</tbody></table></div><h2>Inclusive latency (ns)</h2><p>Successful input-to-verified-result latency excludes object destruction, serialization, process startup and application orchestration. Exceptional intervals labelled end_to_end_including_unwind include owned cleanup and remain excluded from successful summaries. Nested phases are not added to end-to-end. Range means minimum to maximum; it is not a confidence interval. Fewer than five or failed/incomplete trials have no successful latency summary.</p>',
              '<div class="scroll"><table><tr><th>Case</th><th>Phase</th><th>Median (ns)</th><th>Min (ns)</th><th>Max (ns)</th></tr>']
    for row in summary:
        parts.append('<tr>'+''.join('<td>'+e(row[k] if row[k]!='' else 'unavailable')+'</td>' for k in ("case_id","phase","median","min","max"))+'</tr>')
    parts.append('</table></div>')
    definitions={"input_publication":"Copy authored input and validate/deep-copy the immutable program.","registration_preparation":"Register the actual backend, select and snapshot the prepared pipeline.","workspace_creation":"Create the exclusive bound workspace.","public_run":"Run the public operation and consume status/witness bits/residual presence/diagnostic length. Includes native translation, solve, logging and in-run checks.","independent_verification":"Check literal answers, original constraints, identities and numerical evidence after the public call.","end_to_end":"Input-to-verified-result interval including the preceding phases and intervening harness work, before destruction.","record_serialization":"Build trial JSON after numerical timing; separate following event excludes write/flush."}
    parts.append('<details><summary>Exact phase boundaries</summary><dl>'+''.join('<dt>'+e(k)+'</dt><dd>'+e(v)+'</dd>' for k,v in definitions.items())+'</dl></details>')
    if svg:
        parts += ['<figure aria-label="Raw trial durations and median/min-max ranges in separate inclusive panels">',svg,'<figcaption>Analytic LP microfixtures, numerical output with unestablished support. Separate public_run and input-to-verified-result panels; no additive stack.</figcaption></figure>']
    else: parts.append('<p>Figure unavailable in this bounded functional export.</p>')
    parts.append('<h2>Returned results, residuals and diagnostics</h2>')
    for trial in p["trials"]:
        parts.append('<details><summary>'+e(trial["case_id"])+', round '+e(trial["round"])+': '+e(trial["harness"]["status"])+(' — matched' if trial["validation"]["passed"] else ' — FAILED')+'</summary><pre>'+e(json.dumps({"result":trial["result"],"validation":trial["validation"],"harness":trial["harness"],"timings":trial["timings"]},indent=2,ensure_ascii=False))+'</pre></details>')
    parts += ['<h2>Environment and separate profile</h2><p>Fresh workspace per trial; process/TLS may be warm. Native-only time, exclusive native/adapter split and per-trial CPU/peak memory are unavailable. Process counters apply only to the separate profile. Limiter: unresolved unless the saved profile supports a broad phase attribution; no inner-kernel claim.</p>',
              '<pre>'+e(json.dumps({k:p[k] for k in ("provenance","environment","process","profile")},indent=2,ensure_ascii=False))+'</pre>',
              '<h2>Raw downloads</h2><ul>']
    files=["records.json","scenarios.json","raw-events.jsonl","profile.json","build-provenance.txt","process-stderr.txt","trials.csv","summary.csv","export.json","manifest.json"]+(["latency.svg","latency.png"] if svg else [])
    parts += ['<li><a href="'+name+'">'+name+'</a></li>' for name in files]
    tree,archive,label=data.artifact_links(view["report_id"],artifact_ref)
    parts += ['</ul><p><a href="'+tree+'">Repository artifact fallback ('+label+')</a> · <a href="'+archive+'">Repository ZIP fallback</a>. This artifact reference is separate from the measured source commit; availability follows artifact publication.</p>']
    parts += ['<p>Export timing is recorded separately in export.json, excluding its own serialization, final manifest and ZIP packaging. The renderer reads saved records and never starts a solver.</p></body></html>']
    return ''.join(parts)


def render(view, out, figures=None, raw_dir=None, artifact_ref="main"):
    data.validate_view(view)
    data.artifact_reference(artifact_ref)
    started = time.monotonic_ns()
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    p = view["payload"]
    groups = data.aggregate(view)
    svg = ""
    figure_hashes = {}
    metadata = {"available":False,"reason":"no plot requested for functional export"}
    if figures is not None:
        figures = Path(figures)
        metadata = data.parse_json(data.local_file(figures,"export.json").read_text(encoding="utf-8"))
        data.validate_figure_metadata(view,metadata)
        data.require(metadata["payload_sha256"] == view["payload_sha256"], "figure subject mismatch")
        for name in ("latency.svg","latency.png"):
            source = data.local_file(figures,name)
            sha = data.file_digest(source)
            data.require(sha == metadata["files"][name], "figure hash mismatch")
            if name.endswith(".svg"): svg = data.validate_svg(source.read_bytes())
            shutil.copyfile(source,out/name)
            figure_hashes[name] = sha
    elif p["purpose"] == "measurement":
        raise ValueError("measurement export requires reviewed figure files")
    _json(out/"records.json",view)
    _json(out/"scenarios.json",p["scenarios"])
    for name in ("raw-events.jsonl","profile.json","build-provenance.txt","process-stderr.txt"):
        if raw_dir is not None:
            shutil.copyfile(data.local_file(raw_dir,name),out/name)
        elif p["purpose"] == "test":
            (out/name).write_text(json.dumps({"purpose":"test","available":False,"reason":"synthetic saved fixture; no executed process"})+"\n",encoding="utf-8")
        else:
            raise ValueError("measurement raw sidecars required")
    fields,trial_rows,summary_fields,summary=csv_projection(view)
    _csv(out/"trials.csv",fields,trial_rows)
    _csv(out/"summary.csv",summary_fields,summary)
    (out/"index.html").write_text(document(view,svg,artifact_ref),encoding="utf-8")
    ended=time.monotonic_ns()
    _json(out/"export.json",{"schema":"csl.report-export/1","document_policy":DOCUMENT_POLICY,"artifact_ref":artifact_ref,"payload_sha256":view["payload_sha256"],"render_ns":ended-started,
          "scope":"validation-complete through saved-data HTML/CSV/raw-file export; excludes this metadata, manifest and ZIP", "figure_files":figure_hashes,
          "svg_policy":"csl.report.svg.mpl-3.11.2/1" if figures else None,"plot":metadata,
          "packaging":{"available":False,"reason":"not timed by renderer"}})
    _json(out/"manifest.json",{"schema":"csl.report-manifest/1","report_id":view["report_id"],
          "files":{path.name:data.file_digest(path) for path in sorted(out.iterdir())}})
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--figures",type=Path)
    parser.add_argument("--artifact-ref",default="main")
    args=parser.parse_args()
    render(data.load_view(args.records),args.out,args.figures,args.records.parent,args.artifact_ref)


if __name__ == "__main__": main()
