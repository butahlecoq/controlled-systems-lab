"""Check immutable MPC11 mesh/timing inputs and render a separate reading layer."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):return json.loads(path.read_bytes())

def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def runtime():
    if sys.version_info[:3]!=(3,11,14):raise ValueError('saved studies require existing pinned Python3.11.14 environment')
    expected={'do-mpc':'5.1.2','casadi':'3.8.0','matplotlib':'3.11.2'}
    actual={name:importlib.metadata.version(name) for name in expected}
    if actual!=expected:raise ValueError('saved studies optional stack differs from reviewed lock')
    return actual


def stable_timing(value,exclude=frozenset({'offline_saved_checker_seconds'})):
    if isinstance(value,dict):return {k:stable_timing(v,exclude) for k,v in value.items() if k not in exclude}
    if isinstance(value,list):return [stable_timing(v,exclude) for v in value]
    return value


def check(mesh,baseline,timing,mesh_summary_path,timing_summary_path):
    versions=runtime()
    import mesh_summary
    import check_timing
    mesh_summary.check_package_sources(mesh)
    compared=mesh_summary.compare(baseline/'accepted',mesh/'accepted')
    frozen_mesh=load(mesh_summary_path)
    cached_fields={k:frozen_mesh[k] for k in ('schema','scope','cases')}
    if stable_timing(compared,{'checked'})!=stable_timing(cached_fields,{'checked'}):raise ValueError('current mesh archive-derived comparison differs from frozen evidence')
    measured=check_timing.summarize(timing/'capture',timing/'source-68515dcb')
    frozen_timing=load(timing_summary_path)
    for key in ('schema','input_files','environment_sha256','verdict','clock_scopes','records','aggregates'):
        excluded={'offline_saved_checker_seconds','checked'}
        if stable_timing(measured[key],excluded)!=stable_timing(frozen_timing[key],excluded):raise ValueError('current timing archive-derived record differs: '+key)
    if len(measured['records'])!=12 or any(r['status']!='completed' for r in measured['records']):raise ValueError('incomplete repeated-study records')
    if len(measured['aggregates'])!=4 or any(r['completed_sample_count']!=5 for r in measured['aggregates']):raise ValueError('five completed samples required in every arm/case cell')
    mesh_count=sum(case[label]['checked']['transcriptions_checked'] for case in compared['cases'] for label in ('ni1','ni2'))
    timing_count=sum(c['checked']['transcriptions_checked'] for row in measured['records'] if row['arm']=='nmpc' for c in row['cases'])
    if (mesh_count,timing_count)!=(140,420):raise ValueError('full saved transcription inventory differs')
    diagnostics=dict(schema='csl.mpc11.study-current-diagnostics/1',
        mesh=[dict(case_id=c['case_id'],**{label:c[label]['checked'] for label in ('ni1','ni2')}) for c in compared['cases']],
        timing=[dict(arm=r['arm'],repetition=r['repetition'],offline_saved_checker_seconds=r['offline_saved_checker_seconds'],
                     cases=[dict(case=c['case'],checked=c['checked']) for c in r['cases'] if 'checked' in c]) for r in measured['records']])
    print(json.dumps(diagnostics,sort_keys=True),file=sys.stderr)
    compared=stable_timing(compared,{'checked'})
    measured=stable_timing(measured,{'checked','offline_saved_checker_seconds'})
    return compared,measured,dict(status='checked',mesh_transcriptions=mesh_count,timing_transcriptions=timing_count,
        timing_record_count=12,measured_cells=4,measured_samples_per_cell=5,versions=versions,
        scope='current saved NLP/QP/replay checks only; no optimizer/integrator/native execution; fresh checker durations excluded',
        comparison='archive-derived clocks/counts/objectives compared exactly; fresh numerical checker diagnostics satisfy their own current policy and stay in stderr/CI receipts, outside immutable publication bytes')


def figure_data(mesh,baseline,compared,measured):
    cases=[]
    for slug in ('lv','fuel'):
        folders=[root/'accepted'/f'syn-nl-{slug}-01' for root in (baseline,mesh)]
        scenario=[load(p/'scenario.json') for p in folders];attempt=[load(p/'attempt.json') for p in folders]
        if attempt[0]['times']!=attempt[1]['times']:raise ValueError('mesh execution grids differ')
        if [len(a['controls']) for a in attempt]!=[scenario[0]['time']['intervals']]*2:raise ValueError('mesh hold inventory differs')
        names=[s['name'] for s in scenario[0]['states']]
        pairs=[('P','R')] if slug=='lv' else [('m_ox','q_ox'),('m_f','q_f')]
        if set(names)!=set(sum(([a,b] for a,b in pairs),[])):raise ValueError('unexpected canonical state coordinates')
        import numpy as np
        states=[np.asarray(a['physical_states'],dtype=float) for a in attempt];controls=[np.asarray(a['controls'],dtype=float) for a in attempt]
        cases.append(dict(case_id=scenario[0]['case_id'],states=scenario[0]['states'],controls=scenario[0]['controls'],phase_pairs=pairs,
            times=attempt[0]['times'],hold_times=scenario[0]['time']['grid'],time_unit=scenario[0]['time']['unit'],
            ni1_states=states[0].tolist(),ni2_states=states[1].tolist(),state_difference=(states[1]-states[0]).tolist(),
            ni1_controls=controls[0].tolist(),ni2_controls=controls[1].tolist(),control_difference=(controls[1]-controls[0]).tolist(),
            scenario_sha256=[digest(p/'scenario.json') for p in folders],attempt_sha256=[digest(p/'attempt.json') for p in folders],
            objectives=[a['completed_objective'] for a in attempt]))
    return dict(schema='csl.mpc11.study-figures/1',cases=cases,timing_aggregates=measured['aggregates'],mesh_comparison=compared,
        scope='saved physical sample paths/differences and recorded phase medians/ranges; no reachable/winning sets, convergence bound or ranking')


def figures(data,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    sys.path.insert(0,str(ROOT/'scripts/reports'));from figure_style import configure_numeric_axis
    style={'font.family':'DejaVu Sans','svg.hashsalt':'mpc11-mesh-timing-v1','figure.facecolor':'#1e1e2e','axes.facecolor':'#1e1e2e',
        'text.color':'#cdd6f4','axes.labelcolor':'#cdd6f4','axes.edgecolor':'#cdd6f4','xtick.color':'#cdd6f4','ytick.color':'#cdd6f4',
        'legend.labelcolor':'#cdd6f4','legend.facecolor':'#1e1e2e','axes.prop_cycle':plt.cycler(color=['#89b4fa','#f9e2af','#a6e3a1'])}
    def save(fig,name):
        for ext in ('svg','png'):fig.savefig(output/(name+'.'+ext),dpi=160,metadata={'Date':None} if ext=='svg' else None)
        plt.close(fig)
    with plt.rc_context(style):
        fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained');slot=0
        for case in data['cases']:
            names=[s['name'] for s in case['states']];units={s['name']:s['unit'] for s in case['states']}
            for left,right in case['phase_pairs']:
                ax=axes[slot];slot+=1;i,j=names.index(left),names.index(right)
                for label,color,key,linestyle in [('NI1','#89b4fa','ni1_states','-'),('NI2','#f9e2af','ni2_states','--')]:
                    x=np.asarray(case[key]);ax.plot(x[:,i],x[:,j],label=label,color=color,linestyle=linestyle);ax.scatter(x[0,i],x[0,j],marker='o',color=color,s=20);ax.scatter(x[-1,i],x[-1,j],marker='x',color=color,s=35)
                ax.set(xlabel=f'{left} ({units[left]})',ylabel=f'{right} ({units[right]})',title=case['case_id']+' '+left+'/'+right);configure_numeric_axis(ax);ax.legend()
        fig.suptitle('NI1/NI2 executed sample paths; same original plant/grid/objective, different local NLP meshes\nOverlapping curves are shown explicitly by the difference panels; no continuous-time enclosure')
        save(fig,'mesh-phase-overlays')
        fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
        for column,(slug,names) in enumerate([('lv',['P','R']),('fuel',['m_ox','m_f']),('fuel',['q_ox','q_f'])]):
            case=next(c for c in data['cases'] if c['case_id'].lower()==f'syn-nl-{slug}-01');all_names=[s['name'] for s in case['states']]
            indices=[all_names.index(name) for name in names];delta_state=np.asarray(case['state_difference'])[:,indices]
            scale=10.**np.floor(np.log10(np.max(np.abs(delta_state)))) if np.any(delta_state) else 1.
            for i,name in enumerate(names):axes[0,column].plot(case['times'],delta_state[:,i]/scale,label='Δ'+name)
            unit=case['states'][indices[0]]['unit'];axes[0,column].set(xlabel=f"physical time ({case['time_unit']})",ylabel=f'(NI2−NI1) / ({scale:g} {unit})',title=' / '.join(names));axes[0,column].legend()
            if column<2:
                case=data['cases'][column];delta=np.asarray(case['control_difference']);grid=case['hold_times']
                scale=10.**np.floor(np.log10(np.max(np.abs(delta)))) if np.any(delta) else 1.
                control_units={c['unit'] for c in case['controls']}
                if len(control_units)!=1:raise ValueError('control difference panel requires common physical units')
                control_unit=next(iter(control_units))
                for i,control in enumerate(case['controls']):axes[1,column].step(grid,np.r_[delta[:,i],delta[-1,i]]/scale,where='post',label='Δ'+control['name'])
                axes[1,column].set(xlabel=f"physical time ({case['time_unit']})",ylabel=f'(NI2−NI1) / ({scale:g} {control_unit})',title=case['case_id']);axes[1,column].legend()
            else:
                axes[1,column].axis('off');axes[1,column].text(.02,.9,'Different discretized local NLPs.\nSmall differences are diagnostics.\nNo mesh-convergence, global-optimum\nor nonlinear-safety certificate.',va='top',transform=axes[1,column].transAxes)
        for ax in axes.flat:
            if ax.axison:configure_numeric_axis(ax)
        fig.suptitle('Componentwise physical differences on the identical saved sample/hold grids')
        save(fig,'mesh-differences')
        fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
        for ax,group in zip(axes.flat,data['timing_aggregates'],strict=True):
            if group['arm']=='affine':
                entries=[('Python config',group['cost_seconds']['configuration_construction_seconds']),('native QP setup',group['cost_seconds']['native_setup_seconds']),('native QP + checks',group['cost_seconds']['native_optimization_seconds']),('CVODES incl setup',group['integration_seconds']['cvodes']['native_integration_seconds'])]
            else:entries=[('sum controller setup',group['cost_seconds']['controller_setup_seconds']),('sum local NLP solves',group['cost_seconds']['optimization_seconds']),('sum held CVODES',group['cost_seconds']['held_cvodes_execution_seconds'])]
            for i,(label,values) in enumerate(entries):
                ax.errorbar(i,values['median'],yerr=[[values['median']-values['min']],[values['max']-values['median']]],fmt='o',capsize=6,color='#89b4fa')
            ax.set_xticks(range(len(entries)),[label.replace('Python config','Python\nconfiguration').replace('native QP setup','native QP\nsetup').replace('native QP + checks','native QP\n+ checks').replace('CVODES incl setup','CVODES\nincl setup').replace('sum controller setup','sum controller\nsetup').replace('sum local NLP solves','sum local\nNLP solves').replace('sum held CVODES','sum held\nCVODES') for label,_ in entries],ha='center');ax.set_yscale('log');ax.set(ylabel='seconds, log scale',title=group['arm']+' / '+group['case']+'; n=5');configure_numeric_axis(ax,direction='y')
            from matplotlib.ticker import LogLocator, NullFormatter
            ax.yaxis.set_major_locator(LogLocator(base=10,numticks=6));ax.yaxis.set_minor_formatter(NullFormatter());ax.tick_params(axis='x',labelsize=8)
        fig.suptitle('Recorded NI1 phase costs: median and min/max, five alternating measured repetitions\nDifferent model/policy scopes; no summing nested spans or solver ranking; warmup/checker clocks excluded')
        save(fig,'timing-phases')


def render(mesh,baseline,timing,mesh_summary_path,timing_summary_path,output):
    if output.exists():raise ValueError('new study reading layer required')
    compared,measured,verification=check(mesh,baseline,timing,mesh_summary_path,timing_summary_path)
    data=figure_data(mesh,baseline,compared,measured);output.mkdir(parents=True)
    write(output/'mesh-comparison.json',compared);write(output/'timing-comparison.json',measured);write(output/'verification.json',verification);write(output/'figure-data.json',data)
    figures(data,output)
    write(output/'figure-export.json',dict(input_data_sha256=digest(output/'figure-data.json'),images={p.name:digest(p) for p in sorted(output.glob('*.svg'))+sorted(output.glob('*.png'))}))
    return verification


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mesh',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--timing',type=Path,required=True);p.add_argument('--mesh-summary',type=Path,required=True);p.add_argument('--timing-summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(render(a.mesh,a.baseline,a.timing,a.mesh_summary,a.timing_summary,a.output)))
