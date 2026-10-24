"""Publication adapter for immutable EXT-03 transform measurement bundles."""
from __future__ import annotations
import csv, hashlib, io, json
from pathlib import Path
import report_data as data
import registered_reports as common
from ext03_transform import report

KIND="ext03-temporal-transform"
FILES={"README.md","commands.txt","environment.json","index.html","manifest.json","process-stderr.txt","raw-events.jsonl","records.json","trials.csv","visual.svg"}

def _json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def _pretty(value): return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()

def adapt(bundle):
    bundle=Path(bundle); record=_json(bundle/"records.json")
    errors=report.validate(record)
    if errors: raise ValueError("invalid EXT-03 transform report: "+", ".join(errors))
    if bundle.name!=record["report_id"]: raise ValueError("EXT-03 report directory identity mismatch")
    manifest=_json(bundle/"manifest.json")
    actual={p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file() and not p.is_symlink()}
    if actual!=FILES or set(manifest.get("files",{}))!=FILES-{"manifest.json"}: raise ValueError("EXT-03 report bundle inventory mismatch")
    if manifest.get("schema")!="csl.ext03-transform-manifest/1" or manifest.get("report_id")!=bundle.name or manifest.get("source_commit")!=record["source_commit"]: raise ValueError("EXT-03 manifest identity mismatch")
    for name,expected in manifest["files"].items():
        if hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=expected: raise ValueError("EXT-03 bundle hash mismatch: "+name)
    if _json(bundle/"environment.json")!=record["environment"]: raise ValueError("EXT-03 environment sidecar differs from record")
    data.validate_svg((bundle/"visual.svg").read_bytes())
    if (bundle/"index.html").read_text(encoding="utf-8")!=report.render_html(record): raise ValueError("EXT-03 HTML differs from saved record")
    raw=(bundle/"raw-events.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=record["raw_events_sha256"]: raise ValueError("EXT-03 raw event hash mismatch")
    stderr=(bundle/"process-stderr.txt").read_bytes(); process=record.get("process",{})
    if process!={"return_code":0,"aborted":False,"complete":True,"stdout_sha256":hashlib.sha256(raw).hexdigest(),"stderr_sha256":hashlib.sha256(stderr).hexdigest()}: raise ValueError("EXT-03 process completion evidence mismatch")
    try: events=[json.loads(line) for line in raw.decode("utf-8").splitlines()]
    except (UnicodeError,json.JSONDecodeError) as error: raise ValueError("EXT-03 raw events are malformed") from error
    trials=events[1:]; measured=[event for event in trials if event.get("warmup") is False]
    m=record["measurement"]
    if len(events)!=9 or events[0]!={"event":"header","schema":"csl.ext03-transform-measurement/1","batch":10,"warmups":1,"repetitions":7}: raise ValueError("EXT-03 event header/count mismatch")
    if len(trials)!=8 or any(event.get("round")!=i or event.get("fixture")!="two_step_slew_integrator" or event.get("batch")!=10 or event.get("attempted_calls")!=10 or event.get("checked_calls")!=10 or event.get("failed_calls")!=0 or event.get("missing_calls")!=0 or event.get("status")!="passed" or event.get("warmup") is not (i==0) for i,event in enumerate(trials)): raise ValueError("EXT-03 warmup or trial row failed validation")
    if [event.get("elapsed_ns") for event in measured]!=m["batch_elapsed_ns"] or [event.get("elapsed_ns",0)/event.get("batch",1)/1000 for event in measured]!=m["microseconds_per_call"]: raise ValueError("EXT-03 trial events differ from record")
    if any(event.get("status")!="passed" or event.get("checked_calls")!=10 or event.get("failed_calls")!=0 or event.get("missing_calls")!=0 for event in measured): raise ValueError("EXT-03 measurement has failed or missing calls")
    stream=io.StringIO(newline=""); writer=csv.writer(stream,lineterminator="\n"); writer.writerow(["batch","elapsed_ns","calls","microseconds_per_call"])
    for i,(elapsed,value) in enumerate(zip(m["batch_elapsed_ns"],m["microseconds_per_call"]),1): writer.writerow([i,elapsed,10,f"{value:.6f}"])
    if (bundle/"trials.csv").read_bytes()!=stream.getvalue().encode(): raise ValueError("EXT-03 CSV differs from saved events")
    publisher_hash=hashlib.sha256(Path(__file__).read_bytes()+Path(report.__file__).read_bytes()).hexdigest()
    identity={"schema":"csl.registered-publication-identity/1","source_report_id":bundle.name,"source_files":{n:hashlib.sha256((bundle/n).read_bytes()).hexdigest() for n in sorted(FILES)},"publisher_sha256":publisher_hash}
    public_id="ext03-transform-"+common._digest(identity)
    payload=hashlib.sha256(report.canonical(record)).hexdigest()
    return common.PublicationRecord(KIND,public_id,payload,record["source_commit"],"One fixed two-step scalar temporal lift and history recovery; seven measured batches","Transform-only microbenchmark; no solver timing, comparator, speedup, source-mapped limiter, application-scale or scalability claim",tuple(sorted(FILES)),record["schema"],payload,bundle.name)

def render_page(bundle,publication): return (Path(bundle)/"index.html").read_text(encoding="utf-8")
def publication_artifacts(bundle,publication):
    bundle=Path(bundle); files={n:(bundle/n).read_bytes() for n in publication.files}
    record=_json(bundle/"records.json")
    files["report-envelope.json"]=_pretty({"schema":"csl.algorithm-report-envelope/1","report_id":publication.report_id,"report_kind":publication.kind,"payload_schema":publication.payload_schema,"payload_sha256":publication.payload_sha256,"native_payload_sha256":publication.native_payload_sha256,"source_commit":publication.source_commit,"measured_scope":publication.measured_scope,"evidence_limits":publication.evidence_limits,"source_report_id":publication.source_report_id,"payload":record})
    files["publication-manifest.json"]=_pretty({"schema":"csl.algorithm-report-publication-manifest/1","report_id":publication.report_id,"report_kind":publication.kind,"files":{name:hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}})
    return files

def offline_zip(bundle,publication): return common.publication_zip(publication.report_id,publication_artifacts(bundle,publication))
