#!/usr/bin/env python3
"""Summarize verified DIMENSION-01 matched timing pairs."""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--bundle',required=True,type=Path);a=p.parse_args();b=a.bundle.resolve(strict=True)
 attempts=[json.loads(x) for x in (b/'attempts.jsonl').read_text().splitlines() if x]
 checks={x['attempt_id']:x for x in (json.loads(x) for x in (b/'checks.jsonl').read_text().splitlines() if x)}
 summary={'schema':'csl.review05.dimension-summary/1','claim':'matched descriptive timings for a 1D/2D vector-integrator ladder at horizons 2 and 4; the exact fixture oracle proves only the unique zero optimum on these cases; no general completeness, winner, speedup, or complexity claim','timed_region':'SynthesisWorkspace::run, steady_clock nanoseconds','cases':[]}
 strategies_order=('csl.synthesis.reach-back','csl.synthesis.strategy-b')
 for key,n,t in [('n1-t2',1,2),('n1-t4',1,4),('n2-t2',2,2),('n2-t4',2,4)]:
  reps={}
  for x in attempts:
   if x['case']==key and not x['warmup']: reps.setdefault(x['repetition'],[]).append(x)
  paired={s:[] for s in strategies_order};shapes={s:[] for s in strategies_order};verified_attempts=0
  for rows in reps.values():
   by_strategy={x['strategy']:x for x in rows}
   for x in rows:
    verified_attempts+=checks[x['attempt_id']]['status']=='verified'
   if set(by_strategy)!=set(strategies_order) or any(checks[by_strategy[s]['attempt_id']]['status']!='verified' for s in strategies_order): continue
   for s in strategies_order:
    x=by_strategy[s];paired[s].append(x['result']['strategy_run_ns']);rel=x['result']['candidate_relation']
    shapes[s].append({'joint_coordinates':rel['dimension'],'inequality_rows':len(rel['inequalities']),'equality_rows':len(rel['equalities']),'nonzero_h_coefficients':sum(v!=0 for r in rel['inequalities']+rel['equalities'] for v in r)})
  count=len(paired[strategies_order[0]])
  strategies={}
  for s,values in paired.items():
   structures=shapes[s];shape=structures[0] if structures and all(item==structures[0] for item in structures) else None
   strategies[s]={'verified_rows_in_pairs':len(values),'median_ns':statistics.median(values) if values else None,'min_ns':min(values) if values else None,'max_ns':max(values) if values else None,'representation_shape':shape}
  summary['cases'].append({'case':key,'state_dimension':n,'control_dimension':n,'horizon':t,'verified_measured_attempts':verified_attempts,'verified_paired_repetitions':count,'strategies':strategies})
 (b/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));return 0
if __name__=='__main__': raise SystemExit(main())
