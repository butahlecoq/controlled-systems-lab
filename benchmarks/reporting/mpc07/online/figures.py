"""Render a checked saved N8 physical trace; no new policy/plant execution."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from benchmarks.reporting.mpc07.online.inputs import encoded,digest
from benchmarks.reporting.mpc07.online.check import inventory

ROOT=Path(__file__).resolve().parents[4]


def render(capture,verification,output):
    checked=json.loads(verification.read_bytes())
    if checked['status']!='checked' or checked['input_files']!=inventory(capture):raise ValueError('checked capture binding differs')
    if output.exists():raise ValueError('new figure directory required')
    import matplotlib
    if matplotlib.__version__!='3.11.2':raise ValueError('publication Matplotlib3.11.2 required')
    matplotlib.use('Agg');import matplotlib.pyplot as plt
    sys.path.insert(0,str(ROOT/'scripts/reports'));from figure_style import configure_numeric_axis
    records=[json.loads(line) for line in (capture/'measured/stdout.jsonl').read_text().splitlines()]
    rows=[r for r in records if r['profile'].startswith('joint-T8-') and r['family']=='positive' and r['repetition']==0]
    if len(rows)!=4:raise ValueError('N8 four-policy physical trace inventory')
    output.mkdir();data=dict(schema='csl.mpc07.online-figures/1',verification_sha256=digest(verification.read_bytes()),family='positive physical uncertainty trace',rows=rows,scope='actual consumed binary64 feedback actions and observed physical states; q=0 is a zero terminal-cost reference, not claimed attainment along this trace')
    with plt.rc_context({'font.family':'DejaVu Sans','svg.hashsalt':'mpc07-online-evaluation-v1','svg.fonttype':'path'}):
        fig,axes=plt.subplots(1,3,figsize=(15,4.7),layout='constrained')
        for row in rows:
            label=next(k for k in ('fixed-plan','fixed-gain','fixed-filter','joint') if row['profile'].endswith('-'+k))
            states=[row['steps'][0]['observation']]+[s['next_state'] for s in row['steps']];p=[s[0] for s in states];q=[s[1] for s in states];u=[s['control'] for s in row['steps']]
            axes[0].plot(p,q,'-o',markersize=3,label=label);axes[0].scatter(p[0],q[0],marker='o',s=70);axes[0].scatter(p[-1],q[-1],marker='x',s=65)
            axes[1].plot(range(9),q,'-o',markersize=3,label=label);axes[2].step(range(9),u+[u[-1]],where='post',label=label)
        axes[0].axhline(0,color='gray',linestyle=':',label='q=0: terminal q²=0 reference');axes[1].axhline(0,color='gray',linestyle=':')
        axes[0].set(xlabel='position p (authored state units)',ylabel='velocity q (authored state units)',title='Physical phase paths; circle initial, cross final')
        axes[1].set(xlabel='decision stage',ylabel='observed q (authored state units)',title='Closed-loop state samples')
        axes[2].set(xlabel='decision stage',ylabel='applied u (authored control units)',title='Causal held controls; |u|≤1')
        for ax in axes:configure_numeric_axis(ax);ax.legend(fontsize=7)
        fig.suptitle('Existing N8 diagonal-filter policy classes, one positive physical trace\nBinary64 policy evaluation, not reoptimization; no reachable/global/real-time claim')
        for ext in ('svg','png'):fig.savefig(output/('online-policy-traces.'+ext),dpi=160,metadata={'Date':None} if ext=='svg' else None)
        plt.close(fig)
    (output/'figure-data.json').write_bytes(encoded(data));(output/'figure-export.json').write_bytes(encoded(dict(generator_sha256=digest(Path(__file__).read_bytes()),shared_style_sha256=digest((ROOT/'scripts/reports/figure_style.py').read_bytes()),verification_sha256=digest(verification.read_bytes()),input_data_sha256=digest((output/'figure-data.json').read_bytes()),images={p.name:digest(p.read_bytes()) for p in output.glob('online-policy-traces.*')},matplotlib=matplotlib.__version__)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True);p.add_argument('--verification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();render(a.capture.resolve(),a.verification.resolve(),a.output.resolve())
