#!/usr/bin/env python3
"""Check saved NI1/NI2 captures and report numerical mesh sensitivity."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from check_nmpc_saved import check
from run_nmpc import write


def load(path):return json.loads(path.read_text())

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def check_package_sources(package):
    binding=load(package/'source-binding.json')
    for label,entry in binding['capture_sources'].items():
        manifest=load(package/label/'manifest.json')
        revision=entry['source_revision']
        if manifest['source_revision']!=revision:raise ValueError('capture source revision mismatch')
        snapshot=package/('source-'+revision[:8])
        for name,expected in entry['snapshot_sha256'].items():
            path=(snapshot/name).resolve()
            if not path.is_relative_to(snapshot.resolve()) or digest(path)!=expected:raise ValueError('source snapshot binding mismatch')
            committed=subprocess.check_output(['git','show',revision+':'+name],cwd=Path(__file__).resolve().parents[3])
            if path.read_bytes()!=committed:raise ValueError('source snapshot differs from recorded git commit')
        for name,expected in manifest['source_sha256'].items():
            if entry['snapshot_sha256']['benchmarks/reporting/mpc11/'+name]!=expected:raise ValueError('native capture source binding mismatch')
        if label=='accepted':
            for case in ['lv','fuel']:
                name=f'benchmarks/reporting/mpc11/scenarios/mesh-ni2/syn-nl-{case}-01.json'
                if (snapshot/name).read_bytes()!=(package/label/f'syn-nl-{case}-01/scenario.json').read_bytes():raise ValueError('scenario snapshot binding mismatch')
    for name,expected in binding['review_source_sha256'].items():
        if digest(package/'review-source'/name)!=expected:raise ValueError('review source snapshot binding mismatch')
    return binding


def compare(baseline, refined):
    reports={'ni1':check(baseline),'ni2':check(refined)}
    cases=[]
    for case in ['lv','fuel']:
        folders=[root/f'syn-nl-{case}-01' for root in [baseline,refined]]
        scenarios=[load(f/'scenario.json') for f in folders]
        a,b=map(copy.deepcopy,scenarios)
        for s in [a,b]:
            s.pop('controller_id');s['nmpc']['collocation'].pop('elements_per_interval')
        if a!=b:raise ValueError('mesh comparison changed more than controller identity/elements')
        if [s['nmpc']['collocation']['elements_per_interval'] for s in scenarios]!=[1,2]:raise ValueError('expected NI1/NI2')
        attempts=[load(f/'attempt.json') for f in folders]
        if any(r['status']!='complete' for r in attempts):raise ValueError('comparison requires completed trajectories')
        result={'case_id':scenarios[0]['case_id'],'ni1_scenario_sha256':digest(folders[0]/'scenario.json'),'ni2_scenario_sha256':digest(folders[1]/'scenario.json'),
                'max_abs_control_difference_by_component':np.max(np.abs(np.array(attempts[0]['controls'])-attempts[1]['controls']),axis=0).tolist(),
                'max_abs_executed_physical_state_difference_by_component':np.max(np.abs(np.array(attempts[0]['physical_states'])-attempts[1]['physical_states']),axis=0).tolist()}
        for label,folder,attempt in zip(['ni1','ni2'],folders,attempts):
            solves=[load(folder/f'update-{j:03d}/result.json') for j in range(len(attempt['controls']))]
            r=next(r for r in reports[label] if r['case_id']==result['case_id'])
            result[label]={'executed_objective_J0':attempt['completed_objective'],'checked':r,
                'max_stationarity_infinity_norm':max(s['local_stationarity_infinity_norm'] for s in solves),
                'max_scaled_primal_violation':max(s['max_scaled_primal_violation'] for s in solves),
                'max_optimization_node_physical_state_violation_by_component':np.max([s['optimization_node_max_physical_state_violation'] for s in solves],axis=0).tolist(),
                'iterations':{'sum':sum(s['iteration_count'] for s in solves),'max':max(s['iteration_count'] for s in solves)},
                'descriptive_pilot_seconds':{'setup_sum':sum(s['setup_seconds'] for s in solves),'solve_sum':sum(s['solve_seconds'] for s in solves),'execution_sum':sum(s['elapsed_seconds'] for s in attempt['execution_intervals'])},
                'independent_replay':load(folder/'replay-summary.json')}
        result['ni2_minus_ni1_executed_objective']=result['ni2']['executed_objective_J0']-result['ni1']['executed_objective_J0']
        cases.append(result)
    return {'schema':'csl.mpc11.mesh-comparison/1','scope':'Different discretized local NLPs; original physical objective/grid/plant and held execution semantics unchanged. Numerical samples are not an ODE enclosure or global optimality proof. Single pilot durations do not establish a timing ranking.','cases':cases}


def replay(bundle,bridge,output):
    output.mkdir(parents=True,exist_ok=False)
    records=[]
    for case in ['lv','fuel']:
        for mode in ['rk4','rk4-tight']:
            source=bundle/f'syn-nl-{case}-01'/mode
            target=output/f'syn-nl-{case}-01'/mode;target.mkdir(parents=True)
            request=source/'request.json'
            p=subprocess.run([str(bridge),str(request)],capture_output=True,timeout=300)
            (target/'stdout.json').write_bytes(p.stdout);(target/'stderr.txt').write_bytes(p.stderr)
            if p.returncode!=0:raise ValueError('independent replay failed')
            actual=json.loads(p.stdout);expected=load(source/'stdout.json')
            # A fresh process has a new measured duration; all numerical and
            # identity fields must reproduce exactly. Preserve both raw clocks.
            for response in [actual,expected]:
                if not np.isfinite(response['elapsed_seconds']) or response['elapsed_seconds']<0:raise ValueError('invalid native replay clock')
            numerical=lambda response:{k:v for k,v in response.items() if k!='elapsed_seconds'}
            if numerical(actual)!=numerical(expected):raise ValueError('fresh native replay differs from saved numerical response')
            records.append({'case':case,'mode':mode,'request_sha256':digest(request),'stdout_sha256':digest(target/'stdout.json'),'return_code':p.returncode,'all_fields_except_elapsed_seconds_equal':True,'saved_elapsed_seconds':expected['elapsed_seconds'],'fresh_elapsed_seconds':actual['elapsed_seconds']})
    write(output/'receipt.json',{'bridge_sha256':digest(bridge),'records':records,'scope':'Fresh execution of existing CSL native replay binary, no controller solve or rebuild.'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--refined',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--bridge',type=Path);p.add_argument('--fresh-replay',type=Path);p.add_argument('--package',type=Path)
    a=p.parse_args()
    if a.package:check_package_sources(a.package.resolve())
    write(a.output,compare(a.baseline,a.refined))
    if a.bridge:
        if a.fresh_replay is None:p.error('--fresh-replay required with --bridge')
        replay(a.refined,a.bridge.resolve(),a.fresh_replay)
