#!/usr/bin/env python3
"""Render a reading layer from saved, independently checked query attempts."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import html
import json
from pathlib import Path
import statistics


def bound_receipt(bundle,path,check):
    """Consume only the exact bytes certified by this check record."""
    bindings=check.get('bindings')
    if not bindings:raise ValueError('missing check-record byte bindings')
    for key,file in (('receipt_sha256',path),('stdout_sha256',path.parent/'stdout.txt'),
                     ('stderr_sha256',path.parent/'stderr.txt')):
        if hashlib.sha256(file.read_bytes()).hexdigest()!=bindings[key]:
            raise ValueError('stale check-record byte binding: '+key)
    receipt=json.loads(path.read_bytes())
    if Path(receipt['scenario']).name!=receipt['scenario']:raise ValueError('unsafe scenario receipt binding')
    scenario=bundle/'scenarios'/receipt['scenario']
    actual=hashlib.sha256(scenario.read_bytes()).hexdigest() if scenario.is_file() else None
    if actual!=bindings['scenario_sha256']:raise ValueError('stale check-record scenario binding')
    if receipt['stdout_sha256']!=bindings['stdout_sha256'] or receipt['stderr_sha256']!=bindings['stderr_sha256']:
        raise ValueError('receipt/raw output binding mismatch')
    return receipt


def summary(bundle):
    checks=json.loads((bundle/'checks.json').read_text());checked={r['attempt']:r for r in checks['attempts']}
    groups=defaultdict(list);attempts=[]
    for path in sorted((bundle/'attempts').glob('*/receipt.json')):
        key=str(path.parent.relative_to(bundle));check=checked[key]
        receipt=bound_receipt(bundle,path,check)
        record=None
        try:record=json.loads((path.parent/'stdout.txt').read_text())
        except (ValueError,TypeError):pass
        attempts.append((key,receipt,record,check))
        if receipt.get('warmup') or receipt.get('refusal_probe') or check['status']!='verified':continue
        groups[(record['fixture'],record['horizon'],record['strategy'],receipt['mode'])].append((receipt,record,check))
    rows=[]
    for key,values in sorted(groups.items()):
        row={'fixture':key[0],'horizon':key[1],'strategy':key[2],'collector':key[3],'n':len(values)}
        for field in ('prepare_ns','registered_synthesis_ns','selector_prepare_ns','selector_ns','literal_replay_ns','relation_json_bytes'):
            data=[v[1][field] for v in values];row[field]={'median':statistics.median(data),'min':min(data),'max':max(data)}
        for field in ('family_check_ns','independent_query_replay_ns'):
            data=[v[2][field] for v in values];row[field]={'median':statistics.median(data),'min':min(data),'max':max(data)}
        wall=[v[0]['process_wall_ns'] for v in values]
        row['process_wall_ns']={'median':statistics.median(wall),'min':min(wall),'max':max(wall)}
        row['peak_rss_kib']={'median':statistics.median(v[0]['resources']['peak_rss_kib'] for v in values),
            'min':min(v[0]['resources']['peak_rss_kib'] for v in values),'max':max(v[0]['resources']['peak_rss_kib'] for v in values)}
        row['relation_shape']={'dimension':values[0][1]['relation']['dimension'],'inequalities':len(values[0][1]['relation']['inequalities']),'equalities':len(values[0][1]['relation']['equalities'])}
        row['observed_backend_threads']=sorted({v[1].get('observed_backend_threads') for v in values},key=str)
        row['returned']=values[0][1]['returned_witnesses'];row['distinct_range']=[min(v[1]['distinct_witnesses'] for v in values),max(v[1]['distinct_witnesses'] for v in values)]
        if key[3]=='on':
            ticks=[]
            for _,record,_ in values:
                timing=record['selector_timing'];factor=timing['period_numerator']/timing['period_denominator']*1e9
                ticks.append(sum(s['ticks'] for s in timing['spans'] if s['operation']=='selector.lp.direction-query' and s['ticks'] is not None)*factor)
            row['actual_direction_lp_total_ns']={'median':statistics.median(ticks),'min':min(ticks),'max':max(ticks)}
        rows.append(row)
    overhead=[]
    by_key={(r['fixture'],r['horizon'],r['strategy'],r['collector']):r for r in rows}
    for row in rows:
        if row['collector']!='on':continue
        off=by_key.get((row['fixture'],row['horizon'],row['strategy'],'off'))
        if off:
            overhead.append({'fixture':row['fixture'],'horizon':row['horizon'],'strategy':row['strategy'],
                'registered_synthesis_on_minus_off_median_ns':row['registered_synthesis_ns']['median']-off['registered_synthesis_ns']['median'],
                'selector_on_minus_off_median_ns':row['selector_ns']['median']-off['selector_ns']['median'],
                'process_on_minus_off_median_ns':row['process_wall_ns']['median']-off['process_wall_ns']['median'],
                'claim':'descriptive OBS collector-mode difference; distributions and host interference prevent attributing every difference to overhead'})
    result={'schema':'csl.review05.family-query-summary/1','statuses':dict(Counter(c['status'] for *_,c in attempts)),
        'process_failures':sum(r['returncode']!=0 or r['timed_out'] for _,r,_,_ in attempts),
        'retained_attempts':len(attempts),'rows':rows,'collector_mode_differences':overhead,
        'verdict':'inconclusive; no strategy ranking or unique source-level limiter established',
        'phase_limits':['isolated verifier time unavailable; registered synthesis includes verifier/registry validation',
            'OBS selector spans measure actual LP runner calls including runner validation, not only native solver time',
            'literal driver replay and exact Python family/query replay are distinct intervals',
            'source-level limiter profile and native-clock overhead remain separate issue95 gates']}
    return result,attempts


def plot_saved(record,bundle):
    import io
    import os
    import sys
    import importlib.metadata
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'source'))
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/reports'))
    from figure_style import configure_numeric_axis,STYLE_ID
    from plot import normalize_owned_svg
    os.environ.setdefault('MPLCONFIGDIR',str(bundle/'mpl-config'))
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('Matplotlib 3.11.2 required for saved figure')
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    colors=['#a6e3a1','#89b4fa','#f9e2af','#f38ba8']
    with matplotlib.rc_context({'font.family':'DejaVu Sans','font.size':10,'svg.hashsalt':'review05-family-query-v1',
        'svg.fonttype':'path','figure.facecolor':'#1e1e2e','axes.facecolor':'#1e1e2e',
        'text.color':'#cdd6f4','axes.labelcolor':'#cdd6f4','axes.edgecolor':'#cdd6f4',
        'xtick.color':'#cdd6f4','ytick.color':'#cdd6f4'}):
        fig,axes=plt.subplots(1,2,figsize=(11,4.7),layout='constrained')
        try:
            left,right=axes
            left.add_patch(Rectangle((0,0),1,1,facecolor='#a6e3a1',alpha=.15,edgecolor='#a6e3a1'))
            for i,w in enumerate(record['witnesses']):
                u=[v[0] for v in w['controls']];x=[v[0] for v in w['states']]
                left.scatter([u[0]],[u[1]],s=40+30*i,facecolors='none',edgecolors=colors[i%4],label=f'query {i}')
                right.plot(range(3),x,marker='o',color=colors[i%4],label=f'query {i}: u=({u[0]:g},{u[1]:g})')
            left.set(xlim=(-.1,1.1),ylim=(-.1,1.1),xlabel='u0 (dimensionless)',ylabel='u1 (dimensionless)',title='Complete family control projection')
            left.set_aspect('equal',adjustable='box')
            right.set(xlim=(-.05,2.05),ylim=(-.1,2.1),xlabel='discrete stage t',ylabel='scalar state x[t]',title='Recorded selected state paths')
            for axis in axes:configure_numeric_axis(axis)
            right.legend(fontsize=8,facecolor='#1e1e2e',labelcolor='#cdd6f4')
            fig.suptitle('Scalar state dimension n=1; T=2; original objective is constant zero')
            fig.supxlabel('Shaded control square: all optimal controls; highlighted histories: actual saved direction queries',fontsize=9)
            output=io.StringIO();fig.savefig(output,format='svg',metadata={'Date':None,'Format':None,'Type':None,'Creator':None})
            (bundle/'control-projection.svg').write_bytes(normalize_owned_svg(output.getvalue()))
            fig.savefig(bundle/'control-projection.png',dpi=150,metadata={'Software':'CSL REVIEW05 saved figure'})
        finally:plt.close(fig)
    export={'schema':'csl.review05.family-query-figure/1','matplotlib':importlib.metadata.version('matplotlib'),
        'quantitative_axis_policy':STYLE_ID,'source_problem_id':record['problem_id'],
        'scenario_sha256':record['scenario_sha256'],'state_dimension':1,'control_coordinates':['u0','u1'],
        'histories':record['witnesses'],'scope':'saved query observations and independently checked control-cube projection; no solve during rendering',
        'files':{name:hashlib.sha256((bundle/name).read_bytes()).hexdigest() for name in ('control-projection.svg','control-projection.png')}}
    (bundle/'figure-export.json').write_text(json.dumps(export,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);args=parser.parse_args();bundle=args.bundle
    result,attempts=summary(bundle);(bundle/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    selected=next((record for _,receipt,record,check in attempts if check['status']=='verified' and record['fixture']=='FAMILY-QUERY-FLAT' and record['horizon']==2 and record['strategy']=='csl.synthesis.reach-back'),None)
    if selected:plot_saved(selected,bundle)
    env=json.loads((bundle/'environment.json').read_text());parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>REVIEW-05 complete family and witness queries</title>',
        '<style>body{font:16px/1.6 system-ui;background:#1e1e2e;color:#cdd6f4;max-width:1200px;margin:3rem auto;padding:0 1.5rem}a{color:#89b4fa}h1,h2{color:#a6e3a1}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:.5rem;border-bottom:1px solid #45475a;text-align:left}code{color:#f9e2af}img{max-width:100%}</style>',
        '<h1>Complete scalar families and actual witness direction queries</h1>',
        '<p><strong>Inconclusive comparison.</strong> These bounded Release observations measure matched full optimizer families and real direction-LP queries at T=2/4/8. They establish neither a performance ranking, asymptotic scaling nor a hard real-time guarantee.</p>',
        f'<p>Source <code>{html.escape(env["source_commit"])}</code>; binary SHA-256 <code>{env["binary_sha256"]}</code>. {result["retained_attempts"]} attempts retained; check statuses {html.escape(str(result["statuses"]))}. The schedule requests {env["repetitions"]} alternating measured pairs after a warmup pair, with a fresh process per strategy attempt. Group n records actual successful observations; failures remain retained. See <a href="environment.json">environment/resources</a>, <a href="checks.json">independent checks</a>, <a href="summary.json">machine-readable distributions and collector-mode differences</a>.</p>',
        '<p>Input: x[t+1]=x[t]+u[t], x[0]=0, 0≤u[t]≤1. HORIZON-01 minimizes x[T] and has only the all-zero optimal history; it requests one witness. FAMILY-QUERY-FLAT minimizes the constant zero and retains every feasible control history; it requests 2T observations over ±control basis directions. Fewer distinct observations than requested is a search shortfall, never a uniqueness conclusion. The independent exact-dyadic checker proves both H-family inclusions and checks each selected history and its associated direction minimum.</p>',
        '<h2>Minimal 2D illustration from saved T=2 flat-family records</h2><p>The state is scalar. The square uses the two control coordinates u0 and u1; all controls in [0,1]² are optimal and x1=u0, x2=u0+u1. The highlighted points and scalar state paths are actual recorded query selections; no new solve is run while rendering.</p><img src="control-projection.svg" alt="Scalar state dimension one; complete control square and selected state histories">',
        '<h2>Measured distributions</h2><p>Times below are medians [min, max] in milliseconds. Collector on/off are separate groups from the same binary. Actual LP sums are observed operation spans, including the registered query runner; they are not isolated native solver time. Synthesis includes producer execution plus compiled verifier/registry validation. Collector-plan construction is outside the per-phase timers; the saved end-to-end process-wall distributions include it, startup and serialization. Isolated verifier time is unavailable; generic membership/slice APIs are unsupported.</p>',
        '<table><tr><th>Fixture / T</th><th>Strategy / collector</th><th>Synthesis ms</th><th>Selector ms</th><th>Actual LP ms</th><th>H shape / JSON bytes</th><th>Returned / distinct</th></tr>']
    def timing(value):return f'{value["median"]/1e6:.3f} [{value["min"]/1e6:.3f}, {value["max"]/1e6:.3f}]'
    for row in result['rows']:
        shape=row['relation_shape'];actual=timing(row['actual_direction_lp_total_ns']) if 'actual_direction_lp_total_ns' in row else 'unobserved'
        parts.append(f'<tr><td>{row["fixture"]} / {row["horizon"]}</td><td>{html.escape(row["strategy"])} / {row["collector"]} (n={row["n"]})</td><td>{timing(row["registered_synthesis_ns"])}</td><td>{timing(row["selector_ns"])}</td><td>{actual}</td><td>{shape["dimension"]} cols, {shape["inequalities"]} inequalities, {shape["equalities"]} equalities / {row["relation_json_bytes"]["median"]:g}</td><td>{row["returned"]} / {row["distinct_range"]}</td></tr>')
    parts.append('</table><h2>Limits and reproduction</h2><p>Per process: 300 CPU seconds, 150-second wall timeout, 8 GiB address space; library context deadline 120 seconds; one requested outer/backend thread. Peak RSS and per-child CPU are wait4 observations. Native heap budgeting remains unsupported. All failures and deliberate materialization-limit refusals stay in the raw attempt directories. Current host load and compiler interference are retained; timing differences are descriptive. A separate source-level limiter profile and native-clock instrumentation overhead remain issue #95 gates. No unique limiter is attributed from these numbers.</p><p>Reproduce with the commands in the source <a href="source/run_family_query.py">capture script</a> and benchmark README, then run <code>python3 source/check_family_query.py .</code> and <code>python3 source/render_family_query.py .</code>. Input bytes are in <a href="scenarios/">scenarios/</a>; raw stdout, stderr and resource receipts are in <a href="attempts/">attempts/</a>. The report is a reading layer over these saved records. Pages publication and platform/installed-consumer delivery checks are pending integration; #95 remains open.</p>')
    profile=bundle/'limiter-profile/profile.json'
    if profile.exists():
        value=json.loads(profile.read_text())
        assessment=bundle/'limiter-profile/assessment.json'
        if assessment.exists():value['verdict']=json.loads(assessment.read_text())['verdict']
        parts.append('<h2>Separate limiter diagnostic</h2><p>'+html.escape(value['scope'])+'. '+html.escape(value['verdict'])+'. The profile binary differs from the primary unprofiled binary; these attempts are excluded from the timing groups. See <a href="limiter-profile/profile.json">profile provenance/resources</a> and <a href="limiter-profile/gprof.txt">raw gprof symbols</a>.</p>')
    parts.append('</html>')
    (bundle/'index.html').write_text('\n'.join(parts)+'\n')
    paths=sorted(p for p in bundle.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (bundle/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(bundle).as_posix()}\n' for p in paths))
    print(json.dumps({'groups':len(result['rows']),'attempts':result['retained_attempts'],'statuses':result['statuses']}))

if __name__=='__main__':main()
