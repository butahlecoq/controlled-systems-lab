"""Validate allowlisted immutable report bundles and stage a static Pages site."""
from __future__ import annotations
import argparse
import csv
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import zipfile

import report_data as data
import render
import geo04_registered_reports as geo04
import geo02_registered_reports as geo02
import geo05_registered_reports as geo05
import syn02_registered_reports as syn02
import syn01_registered_reports as syn01
import ts01_registered_reports as ts01
import opt04_registered_reports as opt04
import registered_reports as registered

FILES={"index.html","records.json","scenarios.json","raw-events.jsonl","profile.json","build-provenance.txt",
       "process-stderr.txt","trials.csv","summary.csv","latency.svg","latency.png","export.json","manifest.json"}
LEGACY_PINS_SHA256="9422834b586490e43dc492f47b4a3b4e7000302a75bcb0b8f4557a9e9f1bb2d5"
# Frozen publisher identity for LP/convex publication v1. New report adapters
# must not silently change URLs for already published records.
LP_CONVEX_PUBLISHER_V1={
    "site.py":"5864b16bde6f129b1f973ddc50e4155470a35c02f95c2552937cd9a3b5e2e4c5",
    "registered_reports.py":"7c6d9913396b1f8a2dd8d74e14a37536b659bc7552c0a5d0d3ed85fbb801793a",
    "report_data.py":"c482a0c6a3f8e0973be3a239cb992e58d6737eb1b9f1d401f5135278418b5833",
    "render.py":"0bea998ed0cea04f670a25b68e9a93f25aa558e37d0521206c5e2681822e3888",
}


class OfflineHTML(HTMLParser):
    def __init__(self,files):
        super().__init__(convert_charrefs=True);self.files=files;self.in_style=False;self.in_svg=False
    def handle_starttag(self,tag,attrs):
        html={t:set() for t in ("head","title","body","h1","h2","p","strong","table","thead","tbody","tr","th","td","code","pre","details","summary","dl","dt","dd","figcaption","ul","li","style")}
        html.update({"html":{"lang"},"meta":{"charset","name","content"},"a":{"href"},"div":{"class","role","aria-label","tabindex"},"span":{"class"},"figure":{"aria-label"}})
        html["th"]={"scope"};html["p"]={"class"}
        svg_tags={"svg","g","defs","path","clippath","use","rect","line","polyline","polygon","circle","ellipse","text","tspan","style"}
        svg_attrs={"xmlns","xmlns:xlink","id","class","role","aria-label","width","height","viewbox","version","x","y","x1","x2","y1","y2","cx","cy","rx","ry","r","d","points","transform","style","clip-path","clippathunits","fill","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-dasharray","stroke-dashoffset","stroke-opacity","fill-opacity","opacity","font-size","font-family","font-style","font-weight","text-anchor","type","href","xlink:href"}
        if tag=="svg":
            data.require(not self.in_svg,"nested SVG not generated");self.in_svg=True
        allowed=svg_attrs if self.in_svg else html.get(tag)
        data.require((tag in svg_tags if self.in_svg else tag in html),"unsupported offline HTML element")
        keys=[key for key,_ in attrs]
        data.require(len(keys)==len(set(keys)) and set(keys)<=allowed,"unsupported/duplicate offline HTML attribute")
        if tag=="meta":
            values=dict(attrs)
            data.require(values=={"charset":"utf-8"} or values=={"name":"viewport","content":"width=device-width,initial-scale=1"},"unsupported meta directive")
        if tag=="style": self.in_style=True
        for key,value in attrs:
            data.require(not key.lower().startswith("on"),"HTML event handler")
            if key=="style" and value:
                local=re.sub(r"url\(#[A-Za-z_][A-Za-z0-9_.:-]*\)","",value)
                data.require(re.search(r"@import|url\s*\(|expression\s*\(",local,re.I) is None,"external/active inline style")
            if key in {"href","src","xlink:href"} and value:
                if value.startswith("#"): continue
                if re.fullmatch(r"https://github.com/butahlecoq/controlled-systems-lab/(?:tree/[0-9a-f]{40}|issues/[0-9]+|tree/(?:main|[0-9a-f]{40})/reports/algorithm-results/(?:lp|convex)-\d{8}T\d{6}Z-[0-9a-f]{12}|blob/(?:main|[0-9a-f]{40})/reports/algorithm-results/(?:lp|convex)-\d{8}T\d{6}Z-(?:[0-9a-f]{12}|[0-9a-f]{64})\.zip|tree/(?:main|[0-9a-f]{40})/reports/algorithm-results/opt04-\d{8}T\d{6}Z-[0-9a-f]{12}|blob/(?:main|[0-9a-f]{40})/reports/algorithm-results/opt04-\d{8}T\d{6}Z-[0-9a-f]{64}\.zip|tree/(?:main|[0-9a-f]{40})/reports/algorithm-results/geo04-\d{8}T\d{6}Z-[0-9a-f]{12}|blob/(?:main|[0-9a-f]{40})/reports/algorithm-results/geo04-\d{8}T\d{6}Z-[0-9a-f]{12}\.zip|tree/(?:main|[0-9a-f]{40})/reports/algorithm-results/syn02-terminal-\d{8}-[0-9a-f]{8}-[0-9a-f]{12}|blob/(?:main|[0-9a-f]{40})/reports/algorithm-results/syn02-[0-9a-f]{64}\.zip|tree/(?:main|[0-9a-f]{40})/reports/algorithm-results/syn01-nominal-\d{8}-[0-9a-f]{8}-[0-9a-f]{12}|blob/(?:main|[0-9a-f]{40})/reports/algorithm-results/syn01-[0-9a-f]{64}\.zip)",value): continue
                data.require(value in self.files,"external/escaping HTML asset")
    def handle_endtag(self,tag):
        if tag=="style": self.in_style=False
        if tag=="svg": self.in_svg=False
    def handle_decl(self,decl):
        data.require(decl.lower()=="doctype html","unsupported HTML declaration")
    def handle_data(self,value):
        if self.in_style: data.require(re.search(r"@import|url\s*\(",value,re.I) is None,"external HTML stylesheet resource")


def validate_sidecar_hashes(bundle,payload):
    expected={"raw-events.jsonl":payload["process"]["events_sha256"],
              "process-stderr.txt":payload["process"]["stderr_sha256"],
              "build-provenance.txt":payload["provenance"]["build_log_sha256"],
              "profile.json":payload["profile"]["sha256"]}
    for name,sha in expected.items():
        data.require(data.file_digest(data.local_file(bundle,name))==sha,"raw sidecar subject mismatch: "+name)


def validate_convex_sidecars(bundle,view):
    """Saved-only coherence; parsing retained events never starts a numerical process."""
    import collector_common as collector
    p=view["payload"]
    raw=data.local_file(bundle,"raw-events.jsonl").read_bytes()
    stderr=data.local_file(bundle,"process-stderr.txt").read_bytes()
    profile=data.parse_json(data.local_file(bundle,"profile.json").read_text(encoding="utf-8"))
    if "events_sha256" not in p["process"]:
        placeholder=data.parse_json(raw.decode())
        data.require(p["purpose"]=="test" and placeholder=={"purpose":"test","available":False,"reason":"synthetic saved fixture; no executed process"},"missing native raw sidecar")
        return
    data.require(collector.sha_bytes(raw)==p["process"]["events_sha256"] and collector.sha_bytes(stderr)==p["process"]["stderr_sha256"],"convex raw hashes differ")
    events=collector.events_from_bytes(raw,p["process"]["aborted"] or p["process"]["return_code"]!=0)
    data.require(events and collector.event_profile(events[0]) is collector.CONVEX,"convex raw header required")
    data.require(events[0]["build"]==p["provenance"]["build"],"raw build identity differs")
    rebuilt=collector.event_payload(events,p["process"]["return_code"],raw,stderr,p["provenance"],p["environment"],p["profile"],p["process"]["aborted"])
    rebuilt["created_utc"]=p["created_utc"]
    data.require(data.seal(rebuilt)==view,"saved convex view differs from retained events")
    if not p["profile"]["available"]:
        data.require(p["purpose"]=="test","measurement profile unavailable")
        return
    data.require(profile["schema"]=="csl.convex-profile/1" and profile["purpose"]=="profile","profile kind/version mismatch")
    data.require(data.file_digest(data.local_file(bundle,"profile.json"))==p["profile"]["sha256"],"profile hash mismatch")
    pevents=profile["events"]
    data.require(len(pevents)==2 and pevents[0]["event"]=="header" and pevents[1]["event"]=="profile","complete separate profile events required")
    header,body=pevents
    data.require(all(e["schema"]==data.CONVEX_EVENT_SCHEMA and e["purpose"]=="profile" for e in pevents),"profile event version/purpose")
    data.require(header["build"]==p["provenance"]["build"] and collector.scenarios(header)==p["scenarios"],"profile source/catalogue differs")
    rounds=data.integer(body["rounds"],1);data.require(rounds<=10000 and body["trials"]==rounds*len(p["scenarios"]),"profile count differs")
    wall=data.integer(body["wall_ns"])
    data.require(isinstance(body["observation_token"],str) and body["observation_token"].isdecimal(),"profile consumption token required")
    totals=body["phase_totals_ns"]
    data.require(len(totals)==6 and all(type(x) is int and x>=0 for x in totals) and sum(totals[:5])<=totals[5]<=wall,"profile nested timing scopes differ")
    for snapshot in ("before","after"):
        for name in ("user_cpu","kernel_cpu","peak_resident"):
            metric=body[snapshot][name];data.require(type(metric["available"]) is bool,"profile counter availability")
            if metric["available"]:
                data.integer(metric["value"]);data.require(metric["unit"]==("bytes" if name=="peak_resident" else "ns"),"profile counter unit")
            else:data.require(bool(metric["reason"]),"unavailable profile counter reason")
    failures=data.integer(body["failures"]);data.require(failures<=body["trials"],"profile failure count invalid")
    data.require(profile["phase_order"]==list(data.PHASES) and profile["assessment"]==collector.profile_assessment(body),"profile assessment differs")
    data.require(p["profile"]["valid"]==(profile["return_code"]==0 and not profile["aborted"] and failures==0),"profile success claim differs")


def validate_bundle(bundle,allow_test=False):
    bundle=Path(bundle)
    data.require(bundle.is_dir() and not bundle.is_symlink(),"bundle directory required")
    data.require({p.name for p in bundle.iterdir()}==FILES,"bundle inventory differs from allowlist")
    manifest=data.parse_json(data.local_file(bundle,"manifest.json").read_text(encoding="utf-8"))
    data.require(manifest["schema"]=="csl.report-manifest/1" and set(manifest["files"])==FILES-{"manifest.json"},"manifest inventory/version")
    for name,sha in manifest["files"].items():
        data.require(data.file_digest(data.local_file(bundle,name))==sha,"bundle file hash mismatch: "+name)
    view=data.load_view(data.local_file(bundle,"records.json"))
    data.require(manifest["report_id"]==view["report_id"] and bundle.name==view["report_id"],"bundle identity mismatch")
    data.require(data.publishable(view) or (allow_test and view["payload"]["purpose"]=="test"),"unreviewable/nonmeasurement bundle")
    if view["payload"]["purpose"]=="measurement": validate_sidecar_hashes(bundle,view["payload"])
    if view["schema"]==data.CONVEX_SCHEMA: validate_convex_sidecars(bundle,view)
    data.require(data.parse_json(data.local_file(bundle,"scenarios.json").read_text(encoding="utf-8"))==view["payload"]["scenarios"],"scenario sidecar mismatch")
    svg=data.local_file(bundle,"latency.svg").read_bytes();data.validate_svg(svg)
    png=data.local_file(bundle,"latency.png").read_bytes();data.require(png.startswith(b'\x89PNG\r\n\x1a\n'),"PNG signature missing")
    export=data.parse_json(data.local_file(bundle,"export.json").read_text(encoding="utf-8"))
    data.require(export["payload_sha256"]==view["payload_sha256"] and export["svg_policy"]=="csl.report.svg.mpl-3.11.2/1","export identity/policy mismatch")
    for name in ("latency.svg","latency.png"):
        data.require(export["figure_files"][name]==manifest["files"][name],"final figure digest mismatch")
    page=data.local_file(bundle,"index.html").read_text(encoding="utf-8")
    OfflineHTML(FILES).feed(page)
    data.require(svg.decode() in page,"embedded figure differs from final bytes")
    data.require(export["document_policy"]==render.document_policy(view),"unsupported document projection")
    data.artifact_reference(export["artifact_ref"])
    data.require(page==render.document(view,svg.decode(),export["artifact_ref"]),"HTML differs from saved document projection")
    data.validate_figure_metadata(view,export["plot"])
    data.require(export["plot"]["files"]==export["figure_files"],"plot/export figure digest differs")
    fields,trial_rows,summary_fields,summary_rows=render.csv_projection(view)
    for name,columns,expected in (("trials.csv",fields,trial_rows),("summary.csv",summary_fields,summary_rows)):
        with data.local_file(bundle,name).open(encoding="utf-8",newline="") as stream:
            reader=csv.DictReader(stream);rows=list(reader)
            data.require(reader.fieldnames==columns,"CSV field vocabulary/order differs")
        encoded=[{key:str(row[key]) for key in columns} for row in expected]
        data.require(rows==encoded,"complete CSV projection differs from saved records: "+name)
    return view


def make_zip(bundle,path,allow_test=False):
    bundle=Path(bundle);view=validate_bundle(bundle,allow_test)
    path=Path(path)
    index='<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline algorithm report</title><h1>Offline report</h1><a href="'+view["report_id"]+'/index.html">'+escape(view["report_id"])+'</a></html>'
    with zipfile.ZipFile(path,"x",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,content in [("index.html",index.encode())]+[(bundle.name+"/"+name,data.local_file(bundle,name).read_bytes()) for name in sorted(FILES)]:
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            archive.writestr(info,content)
    return path


def catalogue_index(catalogue):
    artifact_ref=catalogue.get("artifact_ref","main");data.artifact_reference(artifact_ref)
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CSL algorithm reports</title></head><body><h1>Versioned algorithm reports</h1><p>Each report identifies its measured scope and evidence limits. Cross-method performance or certification claims are not implied.</p><ul>']
    for report in catalogue["reports"]:
        rid=report["report_id"]
        source_id=report.get("source_report_id",rid)
        tree,_,label=data.artifact_links(source_id,artifact_ref)
        _,archive,_=data.artifact_links(rid,artifact_ref)
        label_kind='HiGHS reference LP, five analytic microfixtures'
        if catalogue.get("schema","csl.algorithm-report-catalog/1") in ("csl.algorithm-report-catalog/2","csl.algorithm-report-catalog/3"):
            if catalogue["schema"]=="csl.algorithm-report-catalog/3":
                data.require(report["report_kind"] in ("lp","convex","opt04-phase-one","opt05-hull","geo03-hv","geo04-intersection","geo02-affine-sum","geo05-projection-predecessor","syn02-terminal-minimizers","syn01-nominal-forward","syn07-ts01-analytic"),"unknown catalogue kind")
                data.require(isinstance(report.get("measured_scope"),str) and isinstance(report.get("evidence_limits"),str),"schema-v3 scope/evidence metadata required")
                label_kind=report["measured_scope"]+"; limits: "+report["evidence_limits"]
            else:
                data.require(report["report_kind"] in ("lp","convex"),"unknown catalogue kind")
                label_kind='HiGHS reference convex, nine analytic microfixtures' if report["report_kind"]=='convex' else label_kind
        csv_name = "stdout.jsonl" if report.get("report_kind") == opt04.KIND else "raw-driver-output.csv" if report.get("report_kind") in ("geo04-intersection", "geo02-affine-sum") else "trials.csv"
        trial_label = "trial JSONL" if report.get("report_kind") == opt04.KIND else "CSV"
        figure_link = (' · <a href="'+escape(rid,quote=True)+'/performance.svg">performance SVG</a>'
                       if report.get("report_kind") == opt04.KIND else "")
        parts.append('<li><a href="'+escape(rid,quote=True)+'/index.html">'+escape(rid)+'</a> — '+escape(label_kind)+'; source <code>'+escape(str(report["source_commit"]))+'</code> — <a href="'+escape(rid,quote=True)+'/records.json">raw JSON</a> · <a href="'+escape(rid,quote=True)+'/'+csv_name+'">'+trial_label+'</a>'+figure_link+' · <a href="'+escape(rid,quote=True)+'.zip">offline ZIP</a> · <a href="'+escape(tree,quote=True)+'">Repository artifact fallback ('+escape(label)+')</a> · <a href="'+escape(archive,quote=True)+'">Repository ZIP fallback</a></li>')
    return ''.join(parts)+"</ul></body></html>"


def lp_convex_publication_metadata(kind,view):
    expected_schema=data.CONVEX_SCHEMA if kind=="convex" else data.SCHEMA
    data.require(kind in ("lp","convex") and view.get("schema")==expected_schema,"LP/convex kind/schema mismatch")
    scenarios=view.get("payload",{}).get("scenarios")
    data.require(isinstance(scenarios,list) and scenarios,"LP/convex scenario inventory required")
    count_labels={5:"Five",9:"Nine"}
    data.require(len(scenarios) in count_labels,"LP/convex scenario inventory differs from publication policy")
    label="convex" if kind=="convex" else "LP"
    scope=f"{count_labels[len(scenarios)]} analytic {label} microfixtures"
    limits="Single-adapter reference measurements; no comparator or application-scale claim; numerical references are not validated certificates"
    return scope,limits


def lp_convex_publication_id(root,source_id):
    """Bind a new public route to the exact native bundle and publisher code."""
    bundle=Path(root)/source_id
    native_files={name:data.file_digest(data.local_file(bundle,name)) for name in sorted(FILES)}
    native_files["source.zip"]=data.file_digest(data.local_file(root,source_id+".source.zip"))
    publisher_files=dict(LP_CONVEX_PUBLISHER_V1)
    identity={"schema":"csl.lp-convex-publication-identity/1","source_report_id":source_id,
              "source_files":native_files,"publisher_files":publisher_files}
    return source_id.rsplit("-",1)[0]+"-"+registered._digest(identity)


def legacy_pins(root):
    pins=data.parse_json(data.local_file(root,"legacy-publications.json").read_text(encoding="utf-8"))
    data.require(registered._digest(pins)==LEGACY_PINS_SHA256 and pins.get("schema")=="csl.legacy-report-pins/1",
                 "legacy publication pinset differs")
    return pins["reports"]


def validate_legacy_publication(root,source_id,pins):
    data.require(source_id in pins and set(pins[source_id]["files"])==FILES,"legacy publication inventory differs")
    for name,digest in pins[source_id]["files"].items():
        data.require(data.file_digest(data.local_file(root/source_id,name))==digest,
                     "legacy publication file differs: "+name)
    archive_digest=pins[source_id]["zip_sha256"]
    for suffix in (".source.zip",".zip"):
        data.require(data.file_digest(data.local_file(root,source_id+suffix))==archive_digest,
                     "legacy publication ZIP differs")


def stage(catalog_path,out,check=True,allow_test=False):
    catalog_path=Path(catalog_path);root=catalog_path.parent
    catalogue=data.parse_json(catalog_path.read_text(encoding="utf-8"))
    data.require(catalogue["schema"] in ("csl.algorithm-report-catalog/1","csl.algorithm-report-catalog/2","csl.algorithm-report-catalog/3") and catalogue["reports"],"nonempty versioned catalogue required")
    artifact_ref=catalogue.get("artifact_ref","main");data.artifact_reference(artifact_ref)
    ids=set()
    registered_records={}
    registered_artifacts={}
    registered_archives={}
    pinned_legacy=legacy_pins(root) if catalogue["schema"]=="csl.algorithm-report-catalog/3" else {}
    legacy_sources=set()
    for report in catalogue["reports"]:
        rid=report["report_id"]
        data.require(isinstance(rid,str) and rid not in ids,"unsafe/duplicate report ID")
        ids.add(rid)
        if catalogue["schema"]=="csl.algorithm-report-catalog/3" and report.get("report_kind") in ("opt04-phase-one","opt05-hull","geo03-hv","geo04-intersection","geo02-affine-sum","geo05-projection-predecessor","syn02-terminal-minimizers","syn01-nominal-forward","syn07-ts01-analytic"):
            source_id=report.get("source_report_id",rid)
            source_pattern = (opt04.SOURCE_PATTERN if report["report_kind"] == opt04.KIND else
                              r"opt05-hull-\d{8}-[0-9a-f]{8}" if report["report_kind"]=="opt05-hull" else
                              r"geo04-\d{8}T\d{6}Z-[0-9a-f]{12}" if report["report_kind"]=="geo04-intersection" else
                              r"geo02-\d{8}T\d{6}Z-[0-9a-f]{12}" if report["report_kind"]=="geo02-affine-sum" else
                              r"geo05-[0-9a-f]{16}" if report["report_kind"]=="geo05-projection-predecessor" else
                              r"syn02-terminal-\d{8}-[0-9a-f]{8}-[0-9a-f]{12}" if report["report_kind"]=="syn02-terminal-minimizers" else
                              r"syn01-nominal-\d{8}-[0-9a-f]{8}-[0-9a-f]{12}" if report["report_kind"]=="syn01-nominal-forward" else
                              r"syn07-ts01-\d{8}-[0-9a-f]{8,12}" if report["report_kind"]=="syn07-ts01-analytic" else
                              r"geo03-\d{8}-[0-9a-f]{12}")
            data.require(isinstance(source_id,str) and re.fullmatch(source_pattern,source_id) is not None,"invalid registered source bundle identity")
            publisher = opt04 if report["report_kind"] == opt04.KIND else geo04 if report["report_kind"] == "geo04-intersection" else geo02 if report["report_kind"] == "geo02-affine-sum" else geo05 if report["report_kind"] == "geo05-projection-predecessor" else syn02 if report["report_kind"] == "syn02-terminal-minimizers" else syn01 if report["report_kind"] == "syn01-nominal-forward" else ts01 if report["report_kind"] == "syn07-ts01-analytic" else registered
            item=publisher.adapt(root/source_id, allow_test=allow_test) if report["report_kind"] == opt04.KIND else publisher.adapt(root/source_id)
            data.require(item.report_id==rid and report.get("report_kind")==item.kind,"registered catalogue kind differs from bundle")
            data.require(report.get("source_report_id","")==item.source_report_id,"registered catalogue source identity mismatch")
            data.require(report.get("payload_sha256")==item.payload_sha256 and report.get("source_commit")==item.source_commit,"registered catalogue provenance mismatch")
            data.require(report.get("measured_scope")==item.measured_scope and report.get("evidence_limits")==item.evidence_limits,"registered scope/evidence differs from typed records")
            data.require(report.get("payload_schema")==item.payload_schema,"registered catalogue payload schema differs")
            if report["report_kind"] == opt04.KIND:
                data.require(report.get("native_payload_sha256") == item.native_payload_sha256,"OPT-04 catalogue native digest differs")
            generated_page=publisher.render_page(root/source_id,item)
            page_files = set(item.files) | {"report-envelope.json", "publication-manifest.json"}
            if report["report_kind"] == opt04.KIND:
                page_files |= {"source-evidence/" + name for name in item.files}
            OfflineHTML(page_files).feed(generated_page)
            if report["report_kind"] not in ("geo05-projection-predecessor", "syn07-ts01-analytic"):
                if report["report_kind"] == opt04.KIND:
                    data.validate_svg(opt04.public_svg(data.parse_json((root/source_id/"records.json").read_text(encoding="utf-8"))))
                else:
                    svg_name = "timings.svg" if report["report_kind"] == "geo02-affine-sum" else "latency.svg"
                    data.validate_svg((root/source_id/svg_name).read_bytes())
            artifacts=publisher.publication_artifacts(root/source_id,item)
            archive_bytes=publisher.offline_zip(root/source_id,item)
            data.require(hashlib.sha256(archive_bytes).hexdigest()==report.get("zip_sha256"),"registered generated ZIP digest differs")
            registered_records[rid]=item
            registered_artifacts[rid]=artifacts
            registered_archives[rid]=archive_bytes
            continue
        if catalogue["schema"]=="csl.algorithm-report-catalog/3":
            data.require(report.get("report_kind") in ("lp","convex"),"unknown catalogue kind")
            source_id=report.get("source_report_id")
            data.require(isinstance(source_id,str) and re.fullmatch(r"(?:lp|convex)-\d{8}T\d{6}Z-[0-9a-f]{12}",source_id) is not None,"unsafe LP/convex source identity")
            data.require(lp_convex_publication_id(root,source_id)==rid,"LP/convex public identity differs from source")
            if source_id in pinned_legacy:
                validate_legacy_publication(root,source_id,pinned_legacy)
                legacy_sources.add(source_id)
        else:
            source_id=rid
        data.require(re.fullmatch(r"(?:lp|convex)-\d{8}T\d{6}Z-[0-9a-f]{12}",source_id) is not None,"unsafe source report ID")
        view=validate_bundle(root/source_id,allow_test)
        expected_kind="convex" if view["schema"]==data.CONVEX_SCHEMA else "lp"
        if catalogue["schema"]=="csl.algorithm-report-catalog/1": data.require(expected_kind=="lp" and "report_kind" not in report,"v1 catalogue is LP only")
        else: data.require(report["report_kind"]==expected_kind,"catalogue kind differs from bundle")
        exported=data.parse_json(data.local_file(root/source_id,"export.json").read_text(encoding="utf-8"))
        data.require(exported["artifact_ref"]==artifact_ref,"catalogue/bundle artifact reference differs")
        source_commit=view["payload"]["provenance"]["source_commit"]
        if catalogue["schema"]=="csl.algorithm-report-catalog/3":
            data.require(report.get("native_payload_sha256")==view["payload_sha256"] and report.get("payload_sha256")==registered._digest(view),"catalogue payload envelope digest mismatch")
        else:
            data.require(report["payload_sha256"]==view["payload_sha256"],"catalogue payload digest mismatch")
        data.require(report["source_commit"]==source_commit,"catalogue provenance mismatch")
        source_archive_name=source_id+".source.zip" if catalogue["schema"]=="csl.algorithm-report-catalog/3" else rid+".zip"
        archive=data.local_file(root,source_archive_name)
        if catalogue["schema"]!="csl.algorithm-report-catalog/3":
            data.require(data.file_digest(archive)==report["zip_sha256"],"ZIP hash mismatch")
        with zipfile.ZipFile(archive) as saved:
            names=saved.namelist();expected={"index.html"}|{source_id+"/"+name for name in FILES}
            data.require(len(names)==len(expected) and set(names)==expected,"ZIP inventory mismatch")
            for name in FILES: data.require(saved.read(source_id+"/"+name)==data.local_file(root/source_id,name).read_bytes(),"ZIP contents differ")
            OfflineHTML({source_id+"/index.html"}).feed(saved.read("index.html").decode("utf-8"))
        if catalogue["schema"]=="csl.algorithm-report-catalog/3":
            payload_schema=view["schema"]
            data.require(report.get("payload_schema")==payload_schema and isinstance(report.get("measured_scope"),str) and isinstance(report.get("evidence_limits"),str),"LP/convex common envelope metadata required")
            expected_scope,expected_limits=lp_convex_publication_metadata(expected_kind,view)
            data.require(report["measured_scope"]==expected_scope and report["evidence_limits"]==expected_limits,"LP/convex scope/evidence differs from validated report policy")
            publication=registered.PublicationRecord(expected_kind,rid,report["payload_sha256"],view["payload"]["provenance"]["source_commit"],report["measured_scope"],report["evidence_limits"],tuple(sorted(FILES)),payload_schema,report["native_payload_sha256"],source_id)
            source_page=data.local_file(root/source_id,"index.html").read_text(encoding="utf-8")
            links='<p>Publication <code>'+escape(rid)+'</code>; source <code>'+escape(source_id)+'</code>. <a href="report-envelope.json">Versioned report envelope</a> · <a href="publication-manifest.json">Publication manifest</a></p>'
            staged_page=source_page.replace("</body>",links+"</body>") if "</body>" in source_page else source_page+links
            artifacts=registered.publication_artifacts(root/source_id,publication,staged_page.encode("utf-8"))
            OfflineHTML(set(FILES)|{"report-envelope.json","publication-manifest.json"}).feed(staged_page)
            archive_bytes=registered.publication_zip(rid,artifacts)
            data.require(hashlib.sha256(archive_bytes).hexdigest()==report.get("zip_sha256"),"generated publication ZIP digest differs")
            registered_records[rid]=publication
            registered_artifacts[rid]=artifacts
            registered_archives[rid]=archive_bytes
    index=catalogue_index(catalogue)
    if pinned_legacy:
        data.require(set(pinned_legacy)==legacy_sources,"legacy publication sources differ from pinned inventory")
    if check: data.require(data.local_file(root,"index.html").read_text(encoding="utf-8")==index,"committed index differs from catalogue")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if catalogue["schema"]=="csl.algorithm-report-catalog/3":
        for rid in ids:
            (out/rid).mkdir()
            if rid in registered_records:
                item=registered_records[rid]
                for name,content in registered_artifacts[rid].items():
                    destination=out/rid/name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(content)
                expected={"report_id":item.report_id,"report_kind":item.kind,"payload_schema":item.payload_schema,
                    "payload_sha256":item.payload_sha256,"source_commit":item.source_commit,
                    "measured_scope":item.measured_scope,"evidence_limits":item.evidence_limits,
                    "native_payload_sha256":item.native_payload_sha256,"source_report_id":item.source_report_id}
                data.require(registered.validate_publication_manifest(out/rid,expected),"generated publication manifest failed validation")
                (out/(rid+".zip")).write_bytes(registered_archives[rid])
            else:
                for name in FILES: shutil.copyfile(data.local_file(root/rid,name),out/rid/name)
                shutil.copyfile(data.local_file(root,rid+".zip"),out/(rid+".zip"))
        for source_id in legacy_sources:
            (out/source_id).mkdir()
            for name in FILES:
                shutil.copyfile(data.local_file(root/source_id,name),out/source_id/name)
            shutil.copyfile(data.local_file(root,source_id+".source.zip"),out/(source_id+".zip"))
        shutil.copyfile(catalog_path,out/"catalog.json")
        (out/"index.html").write_text(index,encoding="utf-8")
        return out
    for rid in ids:
        (out/rid).mkdir()
        for name in FILES: shutil.copyfile(data.local_file(root/rid,name),out/rid/name)
        shutil.copyfile(data.local_file(root,rid+".zip"),out/(rid+".zip"))
    shutil.copyfile(catalog_path,out/"catalog.json")
    (out/"index.html").write_text(index,encoding="utf-8")
    return out


def validate_publication_manifest(report_dir, expected):
    return registered.validate_publication_manifest(report_dir,expected)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args();stage(args.catalog,args.out,args.check)


if __name__=="__main__": main()
