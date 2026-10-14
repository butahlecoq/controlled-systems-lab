"""Typed publication adapter for registered SYN-04 Strategy B records."""
from __future__ import annotations
import csv,hashlib,io,json
from html import escape
from pathlib import Path
import sys

import registered_reports as common
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports/algorithm-results/tooling/syn04"))
import report

KIND="syn04-strategy-b-ts01"
FILES={"README.md","build-provenance.json","commands.json","environment.json","index.html","measurement-events.jsonl","measurement.json","process-stderr.txt","profile.json","records.json","scenarios.json","trials.csv"}

def _json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def _canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def _pretty(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode("utf-8")

def adapt(bundle):
    bundle=Path(bundle)
    if bundle.is_symlink(): raise ValueError("SYN-04 report directory cannot be a symlink")
    record=_json(bundle/"records.json")
    errors=report.validate(record)
    if errors: raise ValueError("invalid SYN-04 Strategy B record: "+", ".join(errors))
    if bundle.name!=record["report_id"]: raise ValueError("SYN-04 source identity differs from directory")
    manifest=_json(bundle/"manifest.json")
    if manifest.get("schema")!="csl.syn04-strategy-b-ts01-manifest/1" or manifest.get("report_id")!=bundle.name or manifest.get("source_commit")!=record["source_commit"] or manifest.get("harness_commit")!=record["harness_commit"]:
        raise ValueError("SYN-04 manifest identity mismatch")
    actual={p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file() and not p.is_symlink()}
    if actual!=FILES|{"manifest.json"} or set(manifest.get("files",{}))!=FILES: raise ValueError("SYN-04 bundle inventory mismatch")
    for name,expected in manifest["files"].items():
        if hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=expected: raise ValueError("SYN-04 bundle hash mismatch: "+name)
    if (bundle/"index.html").read_text(encoding="utf-8")!=report.render_html(record): raise ValueError("SYN-04 HTML differs from typed record")
    if _json(bundle/"measurement.json")!=record["measurement"]: raise ValueError("SYN-04 measurement sidecar differs from typed record")
    if _json(bundle/"scenarios.json")!=record["scenario"]: raise ValueError("SYN-04 scenario sidecar differs from typed record")
    if _json(bundle/"environment.json")!=record["environment"] or _json(bundle/"build-provenance.json")!=record["build"]: raise ValueError("SYN-04 environment/build sidecar differs")
    if _json(bundle/"profile.json")!=record["measurement"]["profile_attempt"]: raise ValueError("SYN-04 separate profile sidecar differs")
    try: raw_events=[json.loads(line) for line in (bundle/"measurement-events.jsonl").read_text(encoding="utf-8").splitlines()]
    except (UnicodeError,json.JSONDecodeError) as error: raise ValueError("SYN-04 raw event file is malformed") from error
    if raw_events!=record["measurement"]["events"]: raise ValueError("SYN-04 raw event file differs")
    stream=io.StringIO(newline="");fields=("repetition","warmup","elapsed_ns","termination","outcome","result_disposition","registry_verified","assurance","canonical_relation_checked","completeness_verifier","completeness_verifier_version","status","consumed_result_marker","trajectory_objective","trajectory_max_residual","absolute_tolerance","relative_tolerance","residual_verifier","error")
    writer=csv.DictWriter(stream,fieldnames=fields,lineterminator="\n");writer.writeheader()
    for event in record["measurement"]["events"]: writer.writerow({key:event[key] for key in fields})
    if (bundle/"trials.csv").read_bytes()!=stream.getvalue().encode("utf-8"): raise ValueError("SYN-04 CSV differs from typed timing events")
    source_hashes={name:hashlib.sha256((bundle/name).read_bytes()).hexdigest() for name in sorted(actual)}
    identity={"schema":"csl.registered-publication-identity/1","source_report_id":bundle.name,"source_files":source_hashes,
        "publisher_sha256":hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest()}
    public_id="syn04-strategy-b-ts01-"+hashlib.sha256(_canonical(identity)).hexdigest()
    payload_hash=hashlib.sha256(_canonical(record)).hexdigest()
    limits="; ".join(record["evidence_limits"])
    scope="Exact T-S01 profile; one registered Strategy B; seven validated measured trials; performance conclusion inconclusive"
    return common.PublicationRecord(KIND,public_id,payload_hash,record["source_commit"],scope,limits,tuple(sorted(FILES)),record["schema"],payload_hash,bundle.name)

def render_page(bundle,publication):
    record=_json(Path(bundle)/"records.json");page=report.render_html(record)
    links=('<p>Publication <code>'+escape(publication.report_id)+'</code>; source report <code>'+escape(publication.source_report_id)+
      '</code>. <a href="report-envelope.json">Versioned envelope</a> · <a href="publication-manifest.json">Publication manifest</a></p>')
    return page.replace("</body>",links+"</body>")

def publication_artifacts(bundle,publication):
    bundle=Path(bundle)
    files={name:(bundle/name).read_bytes() for name in publication.files if name!="index.html"}
    files["index.html"]=render_page(bundle,publication).encode("utf-8")
    record=_json(bundle/"records.json")
    files["report-envelope.json"]=_pretty({"schema":"csl.algorithm-report-envelope/1","report_id":publication.report_id,"report_kind":publication.kind,
      "payload_schema":publication.payload_schema,"payload_sha256":publication.payload_sha256,"native_payload_sha256":publication.native_payload_sha256,
      "source_commit":publication.source_commit,"measured_scope":publication.measured_scope,"evidence_limits":publication.evidence_limits,
      "source_report_id":publication.source_report_id,"payload":record})
    files["publication-manifest.json"]=_pretty({"schema":"csl.algorithm-report-publication-manifest/1","report_id":publication.report_id,
      "report_kind":publication.kind,"files":{name:hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files

def offline_zip(bundle,publication): return common.publication_zip(publication.report_id,publication_artifacts(bundle,publication))
def validate_publication_manifest(report_dir,expected): return common.validate_publication_manifest(report_dir,expected)
