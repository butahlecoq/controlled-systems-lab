"""Pinned Matplotlib figure adapter over validated saved records."""
from __future__ import annotations
import argparse
import hashlib
import io
import importlib.metadata
import json
import os
from pathlib import Path
import time

import report_data as data

SVG_PROLOG='<?xml version="1.0" encoding="utf-8" standalone="no"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n  "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'


def normalize_owned_svg(text):
    """Only called on our newly generated StringIO; never repair an imported asset."""
    data.require(text.startswith(SVG_PROLOG),"pinned SVG producer prolog changed")
    final=text[len(SVG_PROLOG):].encode("utf-8")
    data.validate_svg(final)
    return final


def plot(view,out):
    data.validate_view(view)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    os.environ.setdefault("MPLCONFIGDIR",str(out.parent/"mpl-config"))
    started=time.monotonic_ns()
    import matplotlib
    data.require(matplotlib.__version__=="3.11.2","Matplotlib 3.11.2 required")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups=data.aggregate(view)
    series=data.figure_series(view)
    with matplotlib.rc_context({"font.family":"DejaVu Sans","font.size":10,"svg.hashsalt":"csl-report-style-v1","svg.fonttype":"path"}):
        fig,axes=plt.subplots(1,2,figsize=(11,6.6 if view["schema"]==data.CONVEX_SCHEMA else 4.6),layout="constrained")
        try:
            for axis,phase,title in zip(axes,("public_run","end_to_end"),("Public registered run","Input-to-verified-result")):
                for index,row in enumerate(series[phase]):
                    values=row["values"];summary=row["summary"]
                    offsets=[(i-(len(values)-1)/2)*0.045 for i in range(len(values))]
                    axis.scatter(values,[index+x for x in offsets],s=18,color="#355c88",alpha=.65,label="raw trials" if index==0 else None)
                    if summary is not None:
                        axis.plot([summary["min"],summary["max"]],[index,index],color="#172235",linewidth=2)
                        axis.scatter([summary["median"]],[index],marker="D",s=30,color="#b64c26",zorder=3,label="median / min-max" if index==0 else None)
                axis.set_yticks(range(len(groups)),[g["case_id"] for g in groups]);axis.invert_yaxis()
                axis.set_xlabel("Inclusive duration (ns)");axis.set_title(title);axis.grid(axis="x",alpha=.2)
            fig.supxlabel("Dots: raw trials · Diamonds: median · Line: min–max · Inclusive panels are not additive",fontsize=9)
            fig.suptitle(("TEST DATA — " if view["payload"]["purpose"]=="test" else "")+("Convex" if view["schema"]==data.CONVEX_SCHEMA else "LP")+" microfixtures · unestablished outcome support",fontsize=12)
            owned=io.StringIO()
            fig.savefig(owned,format="svg",metadata={"Date":None,"Format":None,"Type":None,"Creator":None})
            final=normalize_owned_svg(owned.getvalue())
            (out/"latency.svg").write_bytes(final)
            fig.savefig(out/"latency.png",format="png",dpi=160,metadata={"Software":"CSL algorithm report style1"})
        finally: plt.close(fig)
    ended=time.monotonic_ns()
    metadata={"schema":"csl.report-figure/1","payload_sha256":view["payload_sha256"],"series":series,
              "unit":"ns","matplotlib":matplotlib.__version__,"svg_policy":"csl.report.svg.mpl-3.11.2/1",
              "plot_ns":ended-started,"scope":"saved-data plotting including imports/figure creation and SVG/PNG write; excludes metadata serialization",
              "files":{name:data.file_digest(out/name) for name in ("latency.svg","latency.png")}}
    metadata["packages"]={name:importlib.metadata.version(name) for name in ("matplotlib","numpy","contourpy","cycler","fonttools","kiwisolver","packaging","pillow","pyparsing","python-dateutil","six")}
    (out/"export.json").write_text(json.dumps(metadata,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args();plot(data.load_view(args.records),args.out)


if __name__=="__main__": main()
