from pathlib import Path
import argparse, json, csv, statistics, hashlib, subprocess
root=Path(__file__).resolve().parents[3]
report=root/'reports/algorithm-results/exp02-paired-profiles-20261027-r1'
parser=argparse.ArgumentParser(description='Regenerate summaries and figures from saved paired-profile events.')
parser.add_argument('--raw', type=Path, default=report/'raw', help='directory containing the retained JSONL profile events')
parser.add_argument('--out', type=Path, required=True, help='new empty directory for regenerated summary and figure files')
args=parser.parse_args()
raw=args.raw.resolve()
out=args.out.resolve()
try:
 out.relative_to(report.resolve())
 raise SystemExit('output directory must be outside the committed report bundle')
except ValueError:
 pass
if out.exists() and any(out.iterdir()):
 raise SystemExit(f'refusing to overwrite non-empty output directory: {out}')
out.mkdir(parents=True, exist_ok=True)
summary=[]
for profile,label in [('ts02_constant_integrator','T-S02 constant integrator'),('ts03_singular_integrator','T-S03 singular integrator')]:
 rows=[json.loads(x) for x in (raw/f'{profile}.jsonl').read_text().splitlines()]
 if len(rows) != 13 or rows[0].get('event') != 'header' or rows[0].get('schema') != 'csl.synthesis.paired-family-event/1' or rows[0].get('profile') != profile:
  raise SystemExit(f'{profile}: expected one matching header and exactly 12 trial rows')
 trials=rows[1:]
 expected_strategies={'csl.synthesis.reach-back','csl.synthesis.strategy-b'}
 if any(r.get('event') != 'trial' or r.get('schema') != 'csl.synthesis.paired-family-event/1' for r in trials):
  raise SystemExit(f'{profile}: malformed or missing trial event')
 for repetition in range(6):
  pair=[r for r in trials if r.get('repetition') == repetition]
  expected_warmup=(repetition == 0)
  expected_order=(['csl.synthesis.reach-back','csl.synthesis.strategy-b']
                  if repetition == 0 or repetition % 2 == 1 else ['csl.synthesis.strategy-b','csl.synthesis.reach-back'])
  if len(pair) != 2 or [r.get('order_position') for r in pair] != [0,1] or [r.get('strategy') for r in pair] != expected_order or any(r.get('warmup') is not expected_warmup for r in pair):
   raise SystemExit(f'{profile}: repetition {repetition} is missing, duplicated, or not alternating')
  if any(r.get('family_identity',{}).get('request',{}).get('profile') != profile for r in pair):
   raise SystemExit(f'{profile}: trial request profile does not match header')
 measured=[r for r in trials if r.get('repetition') in range(1,6)]
 for strategy in expected_strategies:
  group=[r for r in measured if r.get('strategy') == strategy]
  if len(group) != 5:
   raise SystemExit(f'{profile}: expected exactly five measured attempts for {strategy}')
  if any(r.get('status') != 'passed' or r.get('termination') != 'completed' or r.get('outcome') != 'optimal' or r.get('complete_family_verified') is not True or r.get('distinct_witnesses') != 2 for r in group):
   raise SystemExit(f'{profile}: failed or incomplete measured attempt for {strategy}')
 for strategy in ['csl.synthesis.reach-back','csl.synthesis.strategy-b']:
  vals=[r['timings_ns']['end_to_end_strategy']['value'] for r in measured if r['strategy']==strategy]
  summary.append({'profile':profile,'case':label,'strategy':strategy,'n':len(vals),'median_ns':int(statistics.median(vals)),'min_ns':min(vals),'max_ns':max(vals),'all_passed':True})
# Summary files
with (out/'summary.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=summary[0].keys()); w.writeheader(); w.writerows(summary)
(out/'summary.json').write_text(json.dumps({'schema':'csl.exp02-paired-profile-summary/1','result_classification':'descriptive; performance-inconclusive','profiles':summary,'limitations':['load average was collected after rather than before the timed runs','perf and a profiler-instrumented build were unavailable; source-mapped limiter is unknown','only T-S02 and T-S03 exact profiles are covered; no scalability or general winner claim']},indent=2)+'\n')
# Standalone SVG analytic feasible optimal control set illustrations
for profile,title,desc,edge in [
 ('ts02_constant_integrator','T-S02 · constant objective','Every control pair in [0,1]² is feasible and optimal.','all'),
 ('ts03_singular_integrator','T-S03 · singular integrator','Feasible controls fill [0,1]²; the optimum is the edge u₁ = 1.','top')]:
 fill='<rect x="100" y="90" width="400" height="300" fill="#d8e9f5" stroke="#17324d" stroke-width="3"/>'
 if edge=='all': mark='<rect x="100" y="90" width="400" height="300" fill="none" stroke="#d76b00" stroke-width="8" stroke-dasharray="12 8"/>'
 else: mark='<line x1="100" y1="90" x2="500" y2="90" stroke="#d76b00" stroke-width="9"/>'
 svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="720" height="500" viewBox="0 0 720 500"><rect width="100%" height="100%" fill="white"/><text x="60" y="45" font-family="sans-serif" font-size="24" font-weight="bold">{title}</text><text x="60" y="75" font-family="sans-serif" font-size="15">{desc}</text>{fill}{mark}<line x1="100" y1="390" x2="500" y2="390" stroke="#222"/><line x1="100" y1="390" x2="100" y2="90" stroke="#222"/><text x="280" y="430" font-family="sans-serif" font-size="18">u₀</text><text x="55" y="245" font-family="sans-serif" font-size="18" transform="rotate(-90 55 245)">u₁</text><text x="92" y="414" font-family="sans-serif" font-size="14">0</text><text x="494" y="414" font-family="sans-serif" font-size="14">1</text><text x="78" y="395" font-family="sans-serif" font-size="14">0</text><text x="78" y="96" font-family="sans-serif" font-size="14">1</text><rect x="520" y="140" width="18" height="18" fill="#d8e9f5" stroke="#17324d"/><text x="550" y="155" font-family="sans-serif" font-size="15">feasible controls</text><line x1="520" y1="190" x2="540" y2="190" stroke="#d76b00" stroke-width="7"/><text x="550" y="195" font-family="sans-serif" font-size="15">optimal controls</text><text x="60" y="475" font-family="sans-serif" font-size="12" fill="#444">Analytic projection from the saved scenario; illustrates the entire optimal control family, not only sampled witnesses.</text></svg>'''
 svg_path=out/f'{profile}-control-projection.svg'; svg_path.write_text(svg)
 subprocess.run(['rsvg-convert','-o',str(svg_path.with_suffix('.png')),str(svg_path)],check=True)
# The frozen README, index and checksums are intentionally not regenerated.
