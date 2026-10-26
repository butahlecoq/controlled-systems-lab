"""Render validated saved control-system figure documents offline."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import control_figure_data as data
import figure_style


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def set_coordinate_aspect(axis, first, second, style):
    if style.get("equal_aspect_for_matching_units") and first.get("unit") and first.get("unit")==second.get("unit"):
        axis.set_aspect("equal",adjustable="box")
        return "Equal x/y data scaling; both coordinates use " + first["unit"] + "."
    return "Independent x/y scales; do not infer geometric distances or angles."


def render(document, source_hash, style_path, out, additional_inputs=None):
    style_bytes = Path(style_path).read_bytes()
    style = json.loads(style_bytes)
    if style.get("schema") != "csl.figure-style/1":
        raise ValueError("expected csl.figure-style/1")
    if style.get("quantitative_axis_policy") != figure_style.STYLE_ID:
        raise ValueError("expected the versioned quantitative axis policy")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("MPLCONFIGDIR", str(out.parent / "mpl-config"))
    started = time.monotonic_ns()
    import matplotlib
    if matplotlib.__version__ != style.get("matplotlib_version"):
        raise ValueError(f"Matplotlib {style.get('matplotlib_version')} required")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    state_defs = {c["id"]: c for c in document["coordinates"]["states"]}
    control_defs = {c["id"]: c for c in document["coordinates"]["controls"]}
    files = []
    trajectories = [s for s in document["series"] if s["kind"] == "trajectory"]
    trajectory_pairs = [s for s in document["series"] if s["kind"] == "trajectory_pair"]
    projections = [s for s in document["series"] if s["kind"] == "projection"]
    samples = [s for s in document["series"] if s["kind"] == "support_samples"]
    timings = [s for s in document["series"] if s["kind"] == "timing"]
    rc = {"font.family": style["font_family"], "font.size": style["font_size"], "svg.hashsalt": style["style_id"], "svg.fonttype":"none"}
    with matplotlib.rc_context(rc):
        if trajectories:
            first=trajectories[0]
            state_ids=first["state_coordinate_ids"];control_ids=first["control_coordinate_ids"]
            fig, axes = plt.subplots(len(state_ids)+len(control_ids), 1,
                                     figsize=(style["trajectory_size"][0],style["trajectory_height_per_axis"]*(len(state_ids)+len(control_ids))))
            axes=list(axes)
            try:
                x_state = document["axes"]["states"]["points"]
                x_control = document["axes"]["controls"]["points"]
                fig.suptitle(f"{document['provenance']['scenario_id']} · {document['provenance']['method_id']}",fontsize=11)
                for coord_index, coord_id in enumerate(state_ids):
                    coord=state_defs[coord_id];ax=axes[coord_index]
                    for trace in trajectories:
                        coord = state_defs[coord_id]
                        ax.plot(x_state, [row[coord_index] for row in trace["states"]], marker="o",
                                label=f"{trace['witness_id']} (J={trace['objective']})")
                    ax.axhline(0, color="#777", linewidth=.8)
                    ax.set(xlabel=document["axes"]["states"].get("label", "stage"), ylabel=f"{coord['name']} ({coord.get('unit') or 'unit unavailable'})",
                           title=f"State coordinate {coord['id']}")
                    figure_style.configure_numeric_axis(ax)
                    ax.set_xticks(x_state)
                    ax.legend(fontsize="small")
                for coord_index, coord_id in enumerate(control_ids):
                    coord=control_defs[coord_id];ax=axes[len(state_ids)+coord_index]
                    for trace in trajectories:
                        y = [row[coord_index] for row in trace["controls"]]
                        ends = document["axes"]["controls"]["interval_ends"]
                        ax.step(x_control + ends[-1:], y + y[-1:], where="post", label=trace["witness_id"])
                    ax.axhline(0, color="#777", linewidth=.8)
                    ax.set(xlabel=document["axes"]["controls"].get("label", "stage"), ylabel=f"{coord['name']} ({coord.get('unit') or 'unit unavailable'})",
                           title=f"Stage-aligned control coordinate {coord['id']} (left-held)")
                    figure_style.configure_numeric_axis(ax)
                    ax.set_xticks(x_control + ends[-1:])
                    ax.legend(fontsize="small")
                note=("Stage and physical-coordinate axes use independent scales. " +
                      " · ".join(f"{t['witness_id']}: J={t['objective']} ({t['objective_evidence']}); {t['evidence']} ({t['assurance']}; {t['approximation']})" for t in trajectories))
                fig.tight_layout(rect=(0,0,1,.96))
                path = out / "trajectories"
                _save(fig, path, style, note)
                files.extend((path.with_suffix(".svg"), path.with_suffix(".png")))
            finally: plt.close(fig)
        for index,item in enumerate(trajectory_pairs):
            a,b=(state_defs[k] for k in item["coordinate_ids"])
            fig,ax=plt.subplots(figsize=tuple(style["projection_size"]))
            try:
                x=document["axes"]["states"]["points"]
                for path in item["paths"]:
                    ax.plot([point[0] for point in path["points"]],[point[1] for point in path["points"]],
                            marker="o",label=f"{path['run_id']} · {path['method_id']} v {path['method_version']} · {path['witness_id']} · J={path['objective']} · {path['assurance']}")
                ax.set(xlabel=f"{a['name']} ({a.get('unit') or 'unit unavailable'})",
                       ylabel=f"{b['name']} ({b.get('unit') or 'unit unavailable'})",
                       title=f"{item['title']} · {document['provenance']['scenario_id']}")
                aspect_note=set_coordinate_aspect(ax,a,b,style)
                figure_style.configure_numeric_axis(ax)
                ax.legend(fontsize="small")
                source_ids="; ".join(f"{path['run_id']} / {path['method_id']} v {path['method_version']}" for path in item["paths"])
                note=f"{aspect_note} Source: {source_ids}\n{item['relation']} · {item['evidence']} · {item['limitation']}"
                fig.tight_layout(rect=(0,0,1,.92))
                path=out/f"trajectory-pair-{index+1:02d}";_save(fig,path,style,note)
                files.extend((path.with_suffix(".svg"),path.with_suffix(".png")))
            finally: plt.close(fig)
        for index, item in enumerate(projections + samples):
            a, b = (state_defs[k] for k in item["coordinate_ids"])
            fig, ax = plt.subplots(figsize=tuple(style["projection_size"]))
            try:
                pts = item["points"]
                ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=style["point_size"], alpha=style["point_alpha"],
                           label=f"{item['kind'].replace('_', ' ')} ({len(pts)})")
                target = item.get("target")
                if target is not None:
                    ax.scatter([target[0]], [target[1]], marker="*", s=style["target_size"], color="#d1495b")
                    ax.annotate("target",(target[0],target[1]),xytext=(9,9),textcoords="offset points",
                                color="#a92f43",fontsize=style["font_size"])
                xr=[p[0] for p in pts]+([target[0]] if target is not None else [])
                yr=[p[1] for p in pts]+([target[1]] if target is not None else [])
                def limits(values):
                    lo,hi=min(values),max(values); span=hi-lo
                    margin=.08*span if span else max(abs(lo)*.08,.5)
                    return lo-margin,hi+margin
                if xr and yr:
                    ax.set_xlim(limits(xr));ax.set_ylim(limits(yr))
                    if min(yr)<=0<=max(yr): ax.axhline(0,color="#777",linewidth=.7)
                    if min(xr)<=0<=max(xr): ax.axvline(0,color="#777",linewidth=.7)
                elif item["kind"]=="support_samples":
                    ax.set_xticks([]);ax.set_yticks([])
                    ax.text(.5,.5,"No finite maximizing points\n(empty or unbounded support outcomes)",
                            transform=ax.transAxes,ha="center",va="center")
                ax.set(xlabel=f"{a['name']} ({a.get('unit') or 'unit unavailable'})",
                       ylabel=f"{b['name']} ({b.get('unit') or 'unit unavailable'})",
                       title=f"{item.get('title', item['kind'])} · {item.get('scenario_id', document['provenance']['scenario_id'])}")
                aspect_note=set_coordinate_aspect(ax,a,b,style)
                ax.set_title(ax.get_title(),fontsize=10,wrap=True)
                objective=(f"J={item['objective']} ({item['objective_label']}; {item['objective_evidence']})"
                           if "objective" in item else item["objective_context"])
                source=item["source"]
                note=(f"{aspect_note} Source: {source['kind']} {source['id']} · {source['method_id']} v {source['method_version']}\n"
                      f"{objective}\n{item['relation']} · {item['evidence']} · {item['limitation']}")
                if item["kind"]=="support_samples":
                    point_count=sum(sample.get("point") is not None for sample in item["samples"])
                    outcomes={kind:sum(sample["value"]["kind"]==kind for sample in item["samples"])
                              for kind in ("finite","empty","unbounded")}
                    note+=(f"\n{len(item['samples'])} directions; {point_count} finite maximizing points plotted; "
                           f"{outcomes['empty']} empty and {outcomes['unbounded']} unbounded outcomes")
                figure_style.configure_numeric_axis(ax)
                if target is None:
                    ax.legend(fontsize="small")
                fig.tight_layout(rect=(0,0,1,.92))
                prefix="support" if item["kind"]=="support_samples" else "projection"
                path = out / f"{prefix}-{index + 1:02d}"
                _save(fig, path, style, note)
                files.extend((path.with_suffix(".svg"), path.with_suffix(".png")))
            finally: plt.close(fig)
        if timings:
            fig, ax = plt.subplots(figsize=tuple(style["timing_size"]), layout="constrained")
            try:
                labels=[]
                for item in timings:
                    labels.append(f"{item['operation']} · {item['metric']} {item.get('summary_statistic','')} ({item['span_semantics']})" +
                                  (" — unavailable" if item["availability"] == "unavailable" else ""))
                    if item["availability"] == "available":
                        ax.scatter(item["values"], [len(labels)-1]*len(item["values"]), label=labels[-1])
                ax.set_yticks(range(len(labels)), labels); ax.set_ylim(-.5, len(labels)-.5); ax.set_xlabel("Duration (ns); operation rows are not additive"); ax.set_title("Saved performance observations")
                figure_style.configure_numeric_axis(ax, "x")
                path=out/"timing";_save(fig,path,style,"Saved performance observations. Operation rows are not additive.");files.extend((path.with_suffix(".svg"),path.with_suffix(".png")))
            finally:plt.close(fig)
    ended=time.monotonic_ns()
    receipt={"schema":"csl.figure-export/1","input_sha256":source_hash,"style_id":style["style_id"],
             "quantitative_axis_policy":figure_style.STYLE_ID,
             "style_sha256":hashlib.sha256(style_bytes).hexdigest(),"matplotlib":matplotlib.__version__,
             "export_wall_ns":ended-started,"export_scope":"saved-data validation already complete; matplotlib import through SVG/PNG writes",
             "solve_query_latency_included":False,"additional_inputs":additional_inputs or {},"files":{p.name:_hash(p) for p in files}}
    for package in ("numpy","pillow","contourpy","cycler","fonttools","kiwisolver","packaging","pyparsing","python-dateutil","six"):
        receipt[package]=importlib.metadata.version(package)
    (out/"export.json").write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return receipt


def _save(fig, path, style, description_text=""):
    fig.savefig(path.with_suffix(".svg"), metadata={"Date":None,"Creator":"CSL saved figure exporter"})
    fig.savefig(path.with_suffix(".png"), dpi=style["png_dpi"], metadata={"Software":style["style_id"]})
    svg=path.with_suffix(".svg")
    tree=ET.parse(svg);root=tree.getroot();root.set("role","img")
    root.set("aria-labelledby","figure-title figure-description")
    title=ET.Element("{http://www.w3.org/2000/svg}title",{"id":"figure-title"})
    title.text=fig._suptitle.get_text() if fig._suptitle else "; ".join(
        axis.get_title() for axis in fig.axes if axis.get_title()) or path.stem
    axes_summary="; ".join(
        ", ".join(part for part in (axis.get_xlabel(),axis.get_ylabel()) if part)
        for axis in fig.axes)
    description=ET.Element("{http://www.w3.org/2000/svg}desc",{"id":"figure-description"})
    description.text=(f"{axes_summary}. Numeric ticks and major gridlines are shown. {description_text} "
                      "Read the adjacent HTML description and saved-value record for exact values, evidence and limitations.")
    root.insert(0,description);root.insert(0,title)
    tree.write(svg,encoding="utf-8",xml_declaration=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True);parser.add_argument("--style",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--obs05-tables",type=Path)
    args=parser.parse_args();document,digest=data.load(args.input);additional={}
    if args.obs05_tables:
        document=data.add_obs05_tables(document,args.obs05_tables)
        for name in ("manifest.json","comparison-record.json","phase-summary.csv","module-summary.csv"):
            additional[name]=_hash(args.obs05_tables/name)
    render(document,digest,args.style,args.out,additional)


if __name__ == "__main__": main()
