#!/usr/bin/env python3
"""Render a saved full-state nominal H tube without re-running its producer."""
import argparse
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "reports/closed-loop-pilot/closed-loop-pilot-v1/raw/geometry/nominal-h-tube-lotka-v1-bounded-backward-compaction-maxrows-1000000"
ATTEMPT = ROOT / "reports/closed-loop-pilot/closed-loop-pilot-v1/raw/attempts/syn-nl-lv-01/syn-nl-lv-01-20261111T114908Z-8dc20bed/attempt.json"
OUTPUT = ROOT / "docs/examples/closed-loop/figures/nominal-h-tube-lotka"
TOL = 1e-8
COLORS = {"F": "#66d9ef", "B": "#fd971f", "I": "#a6e22e"}

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def clip(poly, row, rhs):
    """Clip against one raw H row without changing its coefficients."""
    if not poly:
        return []
    a, b = row
    result = []
    previous = poly[-1]
    pv = a * previous[0] + b * previous[1] - rhs
    pin = pv <= 0.0
    for current in poly:
        cv = a * current[0] + b * current[1] - rhs
        cin = cv <= 0.0
        if cin != pin:
            t = pv / (pv - cv)
            result.append((previous[0] + t * (current[0] - previous[0]),
                           previous[1] + t * (current[1] - previous[1])))
        if cin:
            result.append(current)
        previous, pv, pin = current, cv, cin
    return result

def vertices(h, bounds):
    (xmin, xmax), (ymin, ymax) = bounds
    poly = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    rows, rhs = h["inequalities"]["A"], h["inequalities"]["b"]
    for row, value in zip(rows, rhs, strict=True):
        poly = clip(poly, row, value)
    violation = max((sum(a * x for a, x in zip(row, point, strict=True)) - value
                     for row, value in zip(rows, rhs, strict=True) for point in poly), default=0.0)
    return poly, violation

def math_matrix(name, m):
    rows = "".join("<mtr>" + "".join("<mtd><mn>{:.8g}</mn></mtd>".format(v) for v in row) + "</mtr>" for row in m)
    spoken = "; ".join(", ".join("{:.8g}".format(v) for v in row) for row in m)
    return ('<span class="math-matrix" role="math" aria-label="' + html.escape(name + ": " + spoken) +
            '"><span class="math-bracket math-bracket-left" aria-hidden="true"></span><math display="inline" aria-hidden="true"><mtable>' +
            rows + '</mtable></math><span class="math-bracket math-bracket-right" aria-hidden="true"></span></span>')

def svg(data, k):
    W, H, L, R, T, B = 1000, 620, 100, 950, 48, 525
    (xb, xe), (yb, ye) = data["display_bounds"]
    x = lambda v: L + (v-xb)/(xe-xb)*(R-L)
    y = lambda v: B - (v-yb)/(ye-yb)*(B-T)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 620" role="img" aria-label="Forward, backward, and full-state intersection sets at stage {}">'.format(k),
           '<rect width="100%" height="100%" fill="#303129"/>']
    for i in range(6):
        xv, yv = xb+(xe-xb)*i/5, yb+(ye-yb)*i/5
        out += ['<line x1="{:.3f}" y1="{}" x2="{:.3f}" y2="{}" stroke="#504945"/>'.format(x(xv),T,x(xv),B),
                '<line x1="{}" y1="{:.3f}" x2="{}" y2="{:.3f}" stroke="#504945"/>'.format(L,y(yv),R,y(yv)),
                '<text x="{:.3f}" y="{}" text-anchor="middle" fill="#f8f8f2" font-size="13">{:g}</text>'.format(x(xv),B+22,xv),
                '<text x="{}" y="{:.3f}" text-anchor="end" fill="#f8f8f2" font-size="13">{:g}</text>'.format(L-10,y(yv)+5,yv)]
    stage = data["stages"][k]
    for key, title, n in (("F","Forward F",0),("B","Backward B",1),("I","Full-state intersection I",2)):
        p = stage[key]["display_vertices"]
        if p:
            points = " ".join("{:.5f},{:.5f}".format(x(a),y(b)) for a,b in p)
            out.append('<polygon points="{}" fill="{}" fill-opacity=".2" stroke="{}" stroke-width="2"/>'.format(points,COLORS[key],COLORS[key]))
        out.append('<text x="{}" y="{}" fill="{}" font-size="14">{} · {} raw H rows</text>'.format(L+10,T+20+20*n,COLORS[key],title,len(stage[key]["H"]["b"])))
    trace = data["nonlinear_nmpc_overlay"]["physical_states"]
    points = " ".join("{:.5f},{:.5f}".format(x(p[0]),y(p[1])) for p in trace)
    out += ['<polyline points="{}" fill="none" stroke="#f8f8f2" stroke-width="2" stroke-dasharray="6 5"/>'.format(points),
            '<path d="M {:.3f} {:.3f} h 14 M {:.3f} {:.3f} v 14" stroke="#f0c674" stroke-width="3"/>'.format(x(data["initial_state"][0])-7,y(data["initial_state"][1]),x(data["initial_state"][0]),y(data["initial_state"][1])-7),
            '<path d="M {:.3f} {:.3f} l 12 12 M {:.3f} {:.3f} l 12 -12" stroke="#ff6e6e" stroke-width="2.5"/>'.format(x(data["objective_metadata"]["soft_terminal_target"][0])-6,y(data["objective_metadata"]["soft_terminal_target"][1])-6,x(data["objective_metadata"]["soft_terminal_target"][0])-6,y(data["objective_metadata"]["soft_terminal_target"][1])+6),
            '<text x="{}" y="26" fill="#f8f8f2" font-size="13">dashed white: separate saved nonlinear NMPC trajectory</text>'.format(R-330),
            '<text x="{}" y="{}" text-anchor="middle" fill="#f8f8f2">Prey population P (thousand individuals)</text>'.format((L+R)/2,H-22),
            '<text x="24" y="{}" transform="rotate(-90 24 {})" text-anchor="middle" fill="#f8f8f2">Predator population R (thousand individuals)</text>'.format((T+B)/2,(T+B)/2),
            '</svg>']
    return "\n".join(out)+"\n"

def page(data, stem, default):
    a = data["physical_coefficients"][0]
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lotka full-state nominal H tube · Recorded geometry</title><link rel="stylesheet" href="../../examples.css">
<style>
.tube{width:min(100% - 2rem,76rem);margin:auto;padding:1.4rem 0 4rem}.controls{display:flex;flex-wrap:wrap;gap:.8rem;align-items:center}.scroll{max-width:100%;overflow:auto;border:1px solid var(--line);background:var(--surface)}.scroll svg{width:100%;min-width:40rem;height:auto;display:block}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr));gap:.8rem}.cards article{padding:1rem;border:1px solid var(--line);background:var(--surface)}@media(max-width:520px){.tube{width:min(100% - 1rem,76rem);padding-top:.7rem}}
</style></head><body><main class="tube">
<p><a href="../figure-index.json">All recorded closed-loop figures</a></p><p class="eyebrow">Saved geometry · frozen affine predictor</p><h1>Lotka full-state nominal H tube</h1>
<p>Each stage is displayed in the full physical state x=(P,R). Compare the forward set F<sub>k</sub>, backward feasible set B<sub>k</sub>, and full-state intersection I<sub>k</sub> before projection.</p>
<div class="math-input"><p>Frozen affine stage map: x<sub>k+1</sub>=A<sub>k</sub>x<sub>k</sub>+G<sub>k</sub>u<sub>k</sub>+c<sub>k</sub>, with u<sub>k</sub>∈[0,0.05].</p>
<p>Stage 0 A<sub>0</sub> = __A__ &nbsp; G<sub>0</sub> = __G__ &nbsp; c<sub>0</sub> = __C__</p>
<p>Initial physical state x<sub>0</sub> = __X0__. State and terminal feasible box: X={{x: 0≤x≤__XMAX__}}. The separate soft objective target is x<sub>target</sub>=__XTARGET__.</p><p>F<sub>0</sub>={{x<sub>0</sub>}}, F<sub>k+1</sub>=A<sub>k</sub>F<sub>k</sub>⊕(G<sub>k</sub>U⊕{{c<sub>k</sub>}}), B<sub>30</sub>=X, B<sub>k</sub>=F<sub>k</sub>∩Pre(B<sub>k+1</sub>), I<sub>k</sub>=F<sub>k</sub>∩B<sub>k</sub>.</p></div>
<div class="controls"><label for="stage">Stage</label><input id="stage" type="range" min="0" max="30" value="__STAGE__"><output id="label">__STAGE__</output><a href="__STEM__.svg">Standalone SVG</a><a href="__STEM__.plotted-data.json">All H rows and plotted vertices</a></div>
<figure><div class="scroll"><svg id="plot" viewBox="0 0 1000 620" role="img" aria-label="Selected-stage forward, backward, and intersection sets"></svg></div><figcaption>Cyan F; orange B; green I. Dashed white: separate saved nonlinear NMPC plant trajectory. Gold plus: initial state. Red x: soft objective target, not terminal feasibility. Half-plane clipping is a numerical illustration using every raw coefficient.</figcaption></figure>
<div class="cards"><article><h2>Geometry record</h2><p>30 frozen-affine transitions and 31 state sets. P∈[0,200], R∈[0,150], and each control is in [0,0.05] per day.</p><p id="rows"></p><p id="check"></p></article><article><h2>Separate nonlinear replay</h2><p>The dashed trace is the archived continuous nonlinear NMPC run from (120,60). It is not used to generate the affine H sets.</p><p>Controller: <code>__CONTROLLER__</code></p><p>Source soft target: <strong>__TARGET__</strong> thousand individuals (objective <code>__OBJECTIVE__</code>). This target is distinct from the physical terminal feasible box. Full objective metadata, including every running-cost term, is retained in plotted-data JSON; optimizer selection is not used for this geometry.</p></article></div>
<p class="note"><strong>Numerical scope.</strong> The affine coefficients use a frozen coexistence-point linearization and binary64 matrix-exponential discretization. Geometry uses floating-point equality substitution and Fourier–Motzkin elimination. The display clips the raw H rows against the physical-state box without clamping coefficients, then checks plotted vertices against those rows at absolute tolerance 1e-8. This finite numerical check is not a set-containment certificate. No nonlinear enclosure or controller/global optimality claim is made.</p>
<details><summary>Saved source hashes and provider identities</summary><div class="provenance">__PROVENANCE__</div></details>
</main><script>
const durl="__STEM__.plotted-data.json",svg=document.querySelector("#plot"),range=document.querySelector("#stage"),label=document.querySelector("#label"),rows=document.querySelector("#rows"),check=document.querySelector("#check"),N="http://www.w3.org/2000/svg",colors={F:"#66d9ef",B:"#fd971f",I:"#a6e22e"};const el=(t,a,s)=>{const e=document.createElementNS(N,t);Object.entries(a).forEach(([k,v])=>e.setAttribute(k,v));if(s)e.textContent=s;return e};
function draw(d,k){const [xb,xe]=d.display_bounds[0],[yb,ye]=d.display_bounds[1],L=100,R=950,T=48,B=525,x=v=>L+(v-xb)/(xe-xb)*(R-L),y=v=>B-(v-yb)/(ye-yb)*(B-T),s=d.stages[k];svg.replaceChildren();for(let i=0;i<=5;i++){const xv=xb+(xe-xb)*i/5,yv=yb+(ye-yb)*i/5;svg.append(el("line",{x1:x(xv),y1:T,x2:x(xv),y2:B,stroke:"#504945"}),el("line",{x1:L,y1:y(yv),x2:R,y2:y(yv),stroke:"#504945"}),el("text",{x:x(xv),y:B+22,"text-anchor":"middle",fill:"#f8f8f2","font-size":13},String(Number(xv.toPrecision(5)))),el("text",{x:L-10,y:y(yv)+5,"text-anchor":"end",fill:"#f8f8f2","font-size":13},String(Number(yv.toPrecision(5)))))}for(const key of ["F","B","I"]){const q=s[key],p=q.display_vertices;if(p.length)svg.append(el("polygon",{points:p.map(v=>x(v[0])+","+y(v[1])).join(" "),fill:colors[key],"fill-opacity":.2,stroke:colors[key],"stroke-width":2}));svg.append(el("text",{x:L+10,y:T+20+20*["F","B","I"].indexOf(key),fill:colors[key],"font-size":14},key+" · "+q.H.b.length+" raw H rows"))}const t=d.nonlinear_nmpc_overlay.physical_states;svg.append(el("polyline",{points:t.map(v=>x(v[0])+","+y(v[1])).join(" "),fill:"none",stroke:"#f8f8f2","stroke-width":2,"stroke-dasharray":"6 5"}));const ix=x(d.initial_state[0]),iy=y(d.initial_state[1]),tx=x(d.objective_metadata.soft_terminal_target[0]),ty=y(d.objective_metadata.soft_terminal_target[1]);svg.append(el("path",{d:"M "+(ix-7)+" "+iy+" h 14 M "+ix+" "+(iy-7)+" v 14",stroke:"#f0c674","stroke-width":3}),el("path",{d:"M "+(tx-6)+" "+(ty-6)+" l 12 12 M "+(tx-6)+" "+(ty+6)+" l 12 -12",stroke:"#ff6e6e","stroke-width":2.5}));svg.append(el("line",{x1:L,y1:B,x2:R,y2:B,stroke:"#f8f8f2"}),el("line",{x1:L,y1:T,x2:L,y2:B,stroke:"#f8f8f2"}),el("text",{x:(L+R)/2,y:592,"text-anchor":"middle",fill:"#f8f8f2"},"Prey population P (thousand individuals)"),el("text",{x:24,y:(T+B)/2,transform:"rotate(-90 24 "+((T+B)/2)+")","text-anchor":"middle",fill:"#f8f8f2"},"Predator population R (thousand individuals)"));label.value=k;label.textContent=k;rows.textContent="Raw H inequalities: F "+s.F.H.b.length+", B "+s.B.H.b.length+", I "+s.I.H.b.length+".";check.textContent=["F","B","I"].map(a=>a+" max row residual "+s[a].vertex_check.max_raw_row_violation.toExponential(2)).join("; ")+"; display check only."}
fetch(durl).then(r=>r.json()).then(d=>{draw(d,Number(range.value));range.addEventListener("input",()=>draw(d,Number(range.value)))});
</script></body></html>
""".replace("__A__",math_matrix("A0",a["A"])).replace("__G__",math_matrix("G0",a["B"])).replace("__C__",math_matrix("c0",[[v] for v in a["c"]])).replace("__X0__",math_matrix("x0",[[v] for v in data["initial_state"]])).replace("__XMAX__",math_matrix("physical state upper bounds",[[b[1]] for b in data["display_bounds"]])).replace("__XTARGET__",math_matrix("soft objective target",[[v] for v in data["objective_metadata"]["soft_terminal_target"]])).replace("__STAGE__",str(default)).replace("__STEM__",stem).replace("__CONTROLLER__",html.escape(data["nonlinear_nmpc_overlay"]["controller_id"])).replace("__TARGET__",html.escape(str(data["objective_metadata"]["soft_terminal_target"]))).replace("__OBJECTIVE__",html.escape(data["objective_metadata"]["objective_id"])).replace("__PROVENANCE__", "".join("<p>{}: <code>{}</code></p>".format(html.escape(k),html.escape(str(v))) for k,v in data["provenance"].items()))

def build(capture, attempt_path, stem):
    record_path, request_path, manifest_path = capture/"raw-record.json", capture/"request.json", capture/"capture-manifest.json"
    raw, request, attempt, manifest = load(record_path), load(request_path), load(attempt_path), load(manifest_path)
    if raw.get("completion") != "complete" or len(raw.get("stages",[])) != 31: raise ValueError("expected complete original 30-stage tube")
    if attempt.get("status") != "complete" or len(attempt.get("physical_states",[])) != 31: raise ValueError("expected saved complete nonlinear trajectory")
    stages=[]
    for s in raw["stages"]:
        out={"stage":s["stage"]}
        for key,field in (("F","forward"),("B","backward"),("I","intersection")):
            h=s[field]["output"]
            if h["dimension"] != 2 or h["representation"] != "csl.polyhedron.h": raise ValueError("expected two-state H sets")
            poly,violation=vertices(h,request["state_constraints"])
            out[key]={"H":{"A":h["inequalities"]["A"],"b":h["inequalities"]["b"],"E":h["equalities"]["E"],"f":h["equalities"]["f"],"set_id":h["set_id"]},
                       "display_vertices":poly,"vertex_check":{"max_raw_row_violation":violation,"tolerance":TOL,"within_tolerance":violation<=TOL,"meaning":"numerical plotted-vertex check only; not a set containment certificate"}}
        stages.append(out)
    data={"schema":"csl.nominal-h-tube.figure/1","title":"Lotka full-state nominal H tube",
          "time":{"step_days":request["time"]["dt"],"states":31,"transitions":30},
          "state_coordinates":request["state_coordinates"],"display_bounds":request["state_constraints"],
          "physical_coefficients":request["physical_coefficients"],"initial_state":request["initial_state"],
          "control_constraints":request["control_constraints"],"terminal_feasibility":request["terminal_feasibility"],
          "objective_metadata":request["objective_metadata"],"coefficient_producer_receipt":request["coefficient_producer_receipt"],"stages":stages,
          "nonlinear_nmpc_overlay":{"attempt_id":attempt["attempt_id"],"task_id":attempt["task_id"],"task_sha256":attempt["task_sha256"],"source_sha256":attempt["source_sha256"],"controller_id":attempt["controller_id"],"status":attempt["status"],"physical_objective":attempt["physical_objective"],"controls":attempt["controls"],"physical_states":attempt["physical_states"],"interpretation":"Separate saved nonlinear NMPC plant trace; not produced by the frozen-affine H tube."},
          "provenance":{"geometry_capture":str(record_path.relative_to(ROOT)),"geometry_record_sha256":digest(record_path),"geometry_request_sha256":digest(request_path),"geometry_manifest_sha256":digest(manifest_path),"geometry_source_commit":manifest["source"]["commit"],"geometry_binary_sha256":manifest["binary"]["sha256"],"geometry_providers":sorted({p["actual_provider"]["id"]+"@"+p["actual_provider"]["version"] for s in raw["stages"] for p in s["providers"]}),"nonlinear_attempt":str(attempt_path.relative_to(ROOT)),"nonlinear_attempt_sha256":digest(attempt_path),"nonlinear_attempt_id":attempt["attempt_id"]},
          "display_method":{"algorithm":"Sutherland-Hodgman clipping against the explicit physical-state display box","coefficients_preserved":True,"vertex_check_tolerance":TOL,"claim_limit":"finite plotted vertices checked against raw H rows; no set guarantee inferred"}}
    stem.parent.mkdir(parents=True,exist_ok=True)
    stem.with_suffix(".plotted-data.json").write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    default=15
    stem.with_suffix(".svg").write_text(svg(data,default),encoding="utf-8")
    stem.with_suffix(".html").write_text(page(data,stem.name,default),encoding="utf-8")
    return data

def update_index(data):
    path = ROOT / "docs/examples/closed-loop/figure-index.json"
    index = load(path)
    stem = OUTPUT.name
    base = "examples/closed-loop/figures/" + stem
    source = data["provenance"]
    entry = {
        "id": stem,
        "availability": "ready",
        "href": base + ".html",
        "svg_href": base + ".svg",
        "plotted_data_href": base + ".plotted-data.json",
        "title": data["title"],
        "task_id": data["nonlinear_nmpc_overlay"]["task_id"] + " (frozen-affine geometry producer)",
        "task_sha256": data["nonlinear_nmpc_overlay"]["task_sha256"],
        "geometry_source_commit": source["geometry_source_commit"],
        "stage_count": data["time"]["states"],
        "transition_count": data["time"]["transitions"],
        "time_step": data["time"]["step_days"],
        "timeline_end": data["time"]["step_days"] * data["time"]["transitions"],
        "coordinate_transform": {
            "raw_indices": [0, 1],
            "names": ["Prey population P", "Predator population R"],
            "units": ["thousand individuals", "thousand individuals"],
            "description": "Full physical state; plotted before any projection.",
            "permutation_matrix": [[1.0, 0.0], [0.0, 1.0]],
            "source_values_are_physical": True,
            "scale_applied_to_source_values": False,
        },
        "layer_scopes": [
            "full-state forward H sets F[0..30]",
            "compacted full-state backward feasible H sets B[0..30]",
            "full-state intersections I[0..30] before projection",
            "separate saved nonlinear continuous NMPC plant trajectory",
        ],
        "missing_layers": [
            "nonlinear reachable-set enclosure",
            "exact or validated-arithmetic set-relation certificate",
        ],
        "raw_record_refs": [{
            "geometry_capture": source["geometry_capture"],
            "geometry_record_sha256": source["geometry_record_sha256"],
            "geometry_request_sha256": source["geometry_request_sha256"],
            "geometry_manifest_sha256": source["geometry_manifest_sha256"],
            "nonlinear_attempt": source["nonlinear_attempt"],
            "nonlinear_attempt_sha256": source["nonlinear_attempt_sha256"],
        }],
        "reproduction_command": "python scripts/reports/nominal_tube_figure.py",
    }
    index["figures"] = [item for item in index["figures"] if item.get("id") != stem]
    index["figures"].append(entry)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--capture",type=Path,default=CAPTURE);p.add_argument("--attempt",type=Path,default=ATTEMPT);p.add_argument("--output-stem",type=Path,default=OUTPUT);a=p.parse_args()
    d=build(a.capture,a.attempt,a.output_stem)
    if a.output_stem.resolve() == OUTPUT.resolve(): update_index(d)
    checks=[s[k]["vertex_check"] for s in d["stages"] for k in ("F","B","I")]
    print(json.dumps({"stages":len(d["stages"]),"all_vertex_checks_within_tolerance":all(x["within_tolerance"] for x in checks),"max_abs_raw_row_violation":max(x["max_raw_row_violation"] for x in checks),"geometry_record_sha256":d["provenance"]["geometry_record_sha256"],"nonlinear_attempt_sha256":d["provenance"]["nonlinear_attempt_sha256"]},indent=2))

if __name__=="__main__": main()
