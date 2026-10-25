import json
import argparse
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser()
parser.add_argument('results',type=Path)
parser.add_argument('--output-directory',type=Path)
args=parser.parse_args()
root=args.results.parent
out=args.output_directory or root
out.mkdir(parents=True,exist_ok=True)
rows=[json.loads(line) for line in (root/'results.jsonl').read_text().splitlines()]
fig,axes=plt.subplots(len(rows),2,figsize=(12,25),constrained_layout=True)
for row,(flow,stock) in zip(rows,axes):
    pts=row['winner_terminal_vertices_x1_x3_x2_x4']
    flow.scatter([p[0] for p in pts],[p[1] for p in pts],s=5,alpha=.3,color='#167d9a')
    flow.scatter([30],[20],marker='*',s=75,color='#d1495b',label='target')
    flow.set(xlim=(29,31),ylim=(19.5,20.5),xlabel='oxidizer flow x1 (kg/s)',ylabel='fuel flow x3 (kg/s)',title=f"{row['case_id']} | J={row['value_norm']:.4f}")
    flow.grid(alpha=.2); flow.legend(loc='best',fontsize=8)
    stock.scatter([p[2] for p in pts],[p[3] for p in pts],s=5,alpha=.3,color='#167d9a')
    stock.scatter([0],[0],marker='*',s=75,color='#d1495b',label='target')
    stock.set(xlabel='oxidizer stock x2 (kg)',ylabel='fuel stock x4 (kg)',title='terminal stock projection')
    stock.grid(alpha=.2); stock.legend(loc='best',fontsize=8)
fig.suptitle('B07 fuel minimax reconstructions: terminal reachable set projections',fontsize=15)
fig.savefig(out/'projections.png',dpi=180)
svg_path=out/'projections.svg'
fig.savefig(svg_path)
svg=svg_path.read_text(encoding='utf-8')
svg=re.sub(r'^<\?xml[^>]*\?>\s*','',svg)
svg=re.sub(r'^<!DOCTYPE svg PUBLIC [\s\S]*?>\s*','',svg)
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
svg_root=ET.fromstring(svg)
for element in list(svg_root):
    if element.tag=='{http://www.w3.org/2000/svg}metadata':
        svg_root.remove(element)
svg_path.write_bytes(ET.tostring(svg_root,encoding='utf-8'))

table=''.join(f"<tr><td>{escape(row['case_id'])}</td><td>{row['initial_stock_oxidizer_kg']}, {row['initial_stock_fuel_kg']}</td>"
    f"<td>{row['terminal_lambda']}</td><td>{row['disturbance_coefficients'][0]}, {row['disturbance_coefficients'][1]}</td>"
    f"<td>{row['plans_feasible']}</td><td>{', '.join(map(str,row['minimizing_plan_indices']))}</td>"
    f"<td>{row['value_norm']:.6f}</td><td>{row['median_elapsed_ns']/1e6:.3f}</td></tr>" for row in rows)
page=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>B07 owner-approved fuel reconstruction cases</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17212b}}table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{border:1px solid #bbc5cf;padding:.45rem;text-align:left}}th{{background:#edf2f5}}img{{max-width:100%;height:auto}}code{{background:#f1f3f5;padding:.1rem .25rem}}</style></head>
<body><main><h1>B07 owner-approved fuel reconstruction cases</h1>
<p><strong>Status:</strong> saved reconstruction evidence; not a historical reproduction. The source article states a 100-second duration and prints initial stocks (302,207). These cases use the owner-approved five 2-second steps (10 seconds) and compare both (305,205) and (302,207). The reported paper values were not used as targets.</p>
<p>All cases enumerate 3,125 fixed plans and four stagewise disturbance corners per step for the continuous box <code>[-1,1]^2</code>. An independent NumPy enumeration checked feasibility, complete minimizing-plan indices, and objective values. Seven measured Release calls follow one excluded warmup per case. Each timing includes request construction and one public minimax call; no speedup or cross-adapter claim is made.</p>
<h2>Results</h2><table><thead><tr><th>Case</th><th>Initial stocks (kg)</th><th>lambda</th><th>Disturbance coefficients</th><th>Feasible plans</th><th>Minimizing plan indices</th><th>Worst-case objective</th><th>Median (ms)</th></tr></thead><tbody>{table}</tbody></table>
<h2>Terminal set projections</h2><figure><img src="projections.png" alt="2D flow and stock projections for the eight fuel minimax cases"><figcaption>Left: oxidizer/fuel flow projection with target (30,20). Right: oxidizer/fuel stock projection with target (0,0). The projected sets do not show nonlinear replay trajectories.</figcaption></figure>
<p><a href="projections.svg">SVG figure</a> · <a href="results.jsonl">Raw solver records and terminal vertices</a> · <a href="independent-oracle-verification.json">Independent verification</a> · <a href="README.md">Full assumptions and timing notes</a> · <a href="SHA256SUMS">Bundle checksums</a></p>
</main></body></html>'''
(out/'index.html').write_text(page,encoding='utf-8')
