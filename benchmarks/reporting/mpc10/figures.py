#!/usr/bin/env python3
"""Render bound saved MPC10 paths/branch identities with the shared figure style."""
import argparse
import json
import io
import importlib.metadata
import os
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[3]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'build/mpc10-mpl-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from benchmarks.reporting.mpc10.evidence import checked_verification,load,sha
sys.path.insert(0,str(ROOT/'scripts/reports'))
from figure_style import configure_numeric_axis,STYLE_ID
from plot import normalize_owned_svg


def render(bundle,verification,output):
    receipt=checked_verification(bundle,verification)
    if matplotlib.__version__!='3.11.2':raise ValueError('publication figures require pinned Matplotlib 3.11.2')
    output.mkdir(parents=True,exist_ok=False)
    cases=['published-2d-identity','guard-negative-reset']
    data={'verification_sha256':sha(verification),'figure_style':STYLE_ID,'scope':'saved actual CSL optimal anchors; y=0 is an exact invariant, not a general 2D scalability claim','cases':[]}
    with matplotlib.rc_context({'font.family':'DejaVu Sans','font.size':10,'svg.hashsalt':'csl-mpc10-figures-v1','svg.fonttype':'path'}):
        fig,axes=plt.subplots(1,2,figsize=(11,4.5))
        for ax,name in zip(axes,cases):
            source=bundle/name;s=load(source/'fixture.json');native=load(source/'native/stdout.txt');branch=native['branches'][0];point=branch['result']['primal'];x0,pre,post=point[0],point[3],point[5]
            configure_numeric_axis(ax);ax.plot([x0,pre],[0,0],'-o',label='source flow',color='#0072B2');ax.scatter([post],[0],s=120,facecolors='none',edgecolors='#D55E00',linewidths=2,label='post-reset state')
            ax.annotate(branch['path']['edges'][0],xy=(post,0),xytext=(post,.25),arrowprops={'arrowstyle':'->'},ha='center');ax.text(x0,-.15,'source @ 0',ha='center');ax.text(post,-.3,'target @ 1',ha='center')
            ax.set(xlabel='x',ylabel='y',ylim=(-.6,.6),title=name);ax.legend(loc='upper left',fontsize=8)
            data['cases'].append({'id':name,'native_stream_sha256':sha(source/'native/stdout.txt'),'path':branch['path'],'joint_anchor':point,'terminal_objective':branch['result']['primal_check']['objective'],'core_family_verification':native.get('family_verification')})
        fig.suptitle('MPC-10 supported 2D paths: flow, edge and reset timing');fig.tight_layout()
        svg=io.StringIO();fig.savefig(svg,format='svg',metadata={'Date':None});(output/'paths.svg').write_bytes(normalize_owned_svg(svg.getvalue()));fig.savefig(output/'paths.png',dpi=160)
        plt.close(fig)
        name='guard-negative-reset';native=load(bundle/name/'native/stdout.txt');exact=load(bundle/name/'exact.json');optimal={json.dumps(p,sort_keys=True) for p in exact['all_optimal_paths']}
        fig,ax=plt.subplots(figsize=(8,4));ax.axis('off');ax.scatter([0,1],[0,0],s=900,color=['#0072B2','#009E73']);ax.text(0,0,'source\nt=0',ha='center',va='center',color='white');ax.text(1,0,'target\nt=1',ha='center',va='center',color='white')
        for i,branch in enumerate(native['branches']):
            bend=.35 if i==0 else -.35;path=branch['path'];ax.annotate('',xy=(.94,0),xytext=(.06,0),arrowprops={'arrowstyle':'->','connectionstyle':f'arc3,rad={bend}','color':'#D55E00','lw':2});ax.text(.5,-bend*.6,path['edges'][0]+' — tied optimum '+exact['optimum'],ha='center')
        ax.set(xlim=(-.3,1.3),ylim=(-.5,.5));ax.set_title('Parallel edges retain two distinct optimal branches\nguard on pre-reset x; reset x⁺=1−x⁻; complete continuous families checked')
        fig.tight_layout()
        svg=io.StringIO();fig.savefig(svg,format='svg',metadata={'Date':None});(output/'branches.svg').write_bytes(normalize_owned_svg(svg.getvalue()));fig.savefig(output/'branches.png',dpi=160)
        plt.close(fig)
        (output/'figure-data.json').write_text(json.dumps(data,indent=2)+'\n');shutil.copy2(verification,output/'verification.json')
        exports={'schema':'csl.mpc10.figure-export/1','generator_sha256':sha(Path(__file__)),'shared_style_sha256':sha(ROOT/'scripts/reports/figure_style.py'),'normalizer_sha256':sha(ROOT/'scripts/reports/plot.py'),'verification_sha256':sha(verification),'packages':{name:importlib.metadata.version(name) for name in ['matplotlib','numpy','pillow']},'figures':{p.name:sha(p) for p in sorted(output.iterdir()) if p.suffix in ['.svg','.png']}}
        (output/'figure-export.json').write_text(json.dumps(exports,indent=2)+'\n')
        (output/'README.md').write_text('MPC-10 saved-data figures. Actual native anchors and branch identities are bound in figure-data.json; verification.json binds all consumed capture inputs and reviewing sources. No new optimization occurs while rendering.\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--verification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();render(a.bundle.resolve(),a.verification.resolve(),a.output.resolve())
