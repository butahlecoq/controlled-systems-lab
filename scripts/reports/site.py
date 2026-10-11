"""Validate allowlisted immutable report bundles and stage a static Pages site."""
from __future__ import annotations
import argparse
import csv
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import zipfile

import report_data as data

FILES={"index.html","records.json","scenarios.json","raw-events.jsonl","profile.json","build-provenance.txt",
       "process-stderr.txt","trials.csv","summary.csv","latency.svg","latency.png","export.json","manifest.json"}


class OfflineHTML(HTMLParser):
    def __init__(self,files):
        super().__init__(convert_charrefs=True);self.files=files;self.in_style=False
    def handle_starttag(self,tag,attrs):
        data.require(tag not in {"script","iframe","object","embed","link","base","form"},"active/external HTML element")
        if tag=="style": self.in_style=True
        for key,value in attrs:
            data.require(not key.lower().startswith("on"),"HTML event handler")
            if key=="style" and value:
                local=re.sub(r"url\(#[A-Za-z_][A-Za-z0-9_.:-]*\)","",value)
                data.require(re.search(r"@import|url\s*\(|expression\s*\(",local,re.I) is None,"external/active inline style")
            if key in {"href","src","xlink:href"} and value:
                if value.startswith("#"): continue
                if re.fullmatch(r"https://github.com/butahlecoq/controlled-systems-lab/(?:tree/[0-9a-f]{40}|issues/[0-9]+)",value): continue
                data.require(value in self.files,"external/escaping HTML asset")
    def handle_endtag(self,tag):
        if tag=="style": self.in_style=False
    def handle_data(self,value):
        if self.in_style: data.require(re.search(r"@import|url\s*\(",value,re.I) is None,"external HTML stylesheet resource")


def validate_sidecar_hashes(bundle,payload):
    expected={"raw-events.jsonl":payload["process"]["events_sha256"],
              "process-stderr.txt":payload["process"]["stderr_sha256"],
              "build-provenance.txt":payload["provenance"]["build_log_sha256"],
              "profile.json":payload["profile"]["sha256"]}
    for name,sha in expected.items():
        data.require(data.file_digest(data.local_file(bundle,name))==sha,"raw sidecar subject mismatch: "+name)


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
    with data.local_file(bundle,"trials.csv").open(encoding="utf-8",newline="") as stream:
        rows=list(csv.DictReader(stream))
    data.require(len(rows)==len(view["payload"]["trials"]),"CSV trial count mismatch")
    for row,trial in zip(rows,view["payload"]["trials"]):
        result=trial["result"]
        data.require(row["case_id"]==trial["case_id"] and int(row["round"])==trial["round"],"CSV subject mismatch")
        data.require(row["outcome"]==(result["outcome"] if result else "unavailable"),"CSV outcome mismatch")
        cost=result["original_objective"] if result else None
        data.require(row["original_objective"]=="" if cost is None else float(row["original_objective"])==cost,"CSV objective mismatch")
        for phase in data.PHASES:
            interval=trial["timings"][phase]
            expected=str(interval["duration_ns"]) if interval["available"] else ""
            data.require(row[phase+"_ns"]==expected,"CSV phase duration differs")
    with data.local_file(bundle,"summary.csv").open(encoding="utf-8",newline="") as stream:
        summary=list(csv.DictReader(stream))
    groups=data.aggregate(view)
    data.require(len(summary)==len(groups)*len(data.PHASES),"CSV summary count differs")
    for group_index,group in enumerate(groups):
        for phase_index,phase in enumerate(data.PHASES):
            row=summary[group_index*len(data.PHASES)+phase_index]
            data.require(row["phase"]==phase and row["unit"]=="ns","CSV summary phase/unit differs")
            for key in ("case_id","expected","attempts","matched","failed","missing","unsupported","cancelled","valid"):
                data.require(row[key]==str(group[key]),"CSV summary count/identity differs")
            stat=group["phases"][phase]
            for key in ("median","min","max"):
                data.require(row[key]==str(stat[key]) if stat else row[key]=="","CSV summary statistic differs")
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
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CSL algorithm reports</title></head><body><h1>Versioned algorithm reports</h1><p>Single-adapter numerical reports. No certificate, optimizer-family or speedup claim is implied.</p><ul>']
    for report in catalogue["reports"]:
        rid=report["report_id"]
        parts.append('<li><a href="'+rid+'/index.html">'+escape(rid)+'</a> — HiGHS reference LP, five analytic microfixtures; source <code>'+escape(report["source_commit"])+'</code> — <a href="'+rid+'/records.json">raw JSON</a> · <a href="'+rid+'/trials.csv">CSV</a> · <a href="'+rid+'.zip">offline ZIP</a></li>')
    return ''.join(parts)+"</ul></body></html>"


def stage(catalog_path,out,check=True):
    catalog_path=Path(catalog_path);root=catalog_path.parent
    catalogue=data.parse_json(catalog_path.read_text(encoding="utf-8"))
    data.require(catalogue["schema"]=="csl.algorithm-report-catalog/1" and catalogue["reports"],"nonempty versioned catalogue required")
    ids=set()
    for report in catalogue["reports"]:
        rid=report["report_id"]
        data.require(re.fullmatch(r"lp-\d{8}T\d{6}Z-[0-9a-f]{12}",rid) is not None and rid not in ids,"unsafe/duplicate report ID")
        ids.add(rid)
        view=validate_bundle(root/rid)
        data.require(report["payload_sha256"]==view["payload_sha256"] and report["source_commit"]==view["payload"]["provenance"]["source_commit"],"catalogue provenance mismatch")
        archive=data.local_file(root,rid+".zip")
        data.require(data.file_digest(archive)==report["zip_sha256"],"ZIP hash mismatch")
        with zipfile.ZipFile(archive) as saved:
            names=saved.namelist();expected={"index.html"}|{rid+"/"+name for name in FILES}
            data.require(len(names)==len(expected) and set(names)==expected,"ZIP inventory mismatch")
            for name in FILES: data.require(saved.read(rid+"/"+name)==data.local_file(root/rid,name).read_bytes(),"ZIP contents differ")
            OfflineHTML({rid+"/index.html"}).feed(saved.read("index.html").decode("utf-8"))
    index=catalogue_index(catalogue)
    if check: data.require(data.local_file(root,"index.html").read_text(encoding="utf-8")==index,"committed index differs from catalogue")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    for rid in ids:
        (out/rid).mkdir()
        for name in FILES: shutil.copyfile(data.local_file(root/rid,name),out/rid/name)
        shutil.copyfile(data.local_file(root,rid+".zip"),out/(rid+".zip"))
    shutil.copyfile(catalog_path,out/"catalog.json")
    (out/"index.html").write_text(index,encoding="utf-8")
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args();stage(args.catalog,args.out,args.check)


if __name__=="__main__": main()
