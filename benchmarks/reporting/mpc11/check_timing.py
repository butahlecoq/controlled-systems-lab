#!/usr/bin/env python3
"""Verify captured programs/trajectories before extracting scoped pilot clocks."""
import argparse
import math
from pathlib import Path
import statistics
import time
from check_affine_saved import check as check_affine
from check_nonlinear_saved import check as check_nonlinear
from check_nmpc_saved import check as check_nmpc
from run_timing import load,sha,validate_receipt
from run_affine import write


def nonnegative(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('invalid timing clock')
    return value


def selected(root,key):
    completed=[p for p in sorted((root/key).glob('attempt-*')) if (p/'receipt.json').exists()]
    if len(completed)!=1:raise ValueError('expected one completed immutable unit: '+key)
    folder=completed[0];return folder,validate_receipt(folder)


def summarize(root):
    environment=load(root/'environment.json');records=[]
    for repetition in ['warmup',*[f'rep-{i:02d}' for i in range(5)]]:
        for arm in ['affine','nmpc']:
            key=repetition+'/'+arm
            folder,receipt=selected(root,key+('/optimization' if arm=='affine' else ''))
            record={'repetition':repetition,'arm':arm,'measured':repetition!='warmup','status':receipt['status'],'outer_process_seconds':nonnegative(receipt['whole_process_seconds']),
                    'process_cpu_seconds':receipt['process_cpu_seconds'],'max_rss_kib':receipt['max_rss_kib'],'cases':[]}
            if receipt['status']!='completed':records.append(record);continue
            capture=folder/'capture';start=time.monotonic()
            if arm=='affine':
                checked=check_affine(capture)
                if not all(r['status']=='verified-numerical-witness' for r in checked):raise ValueError('affine witness check failed')
                nonlinear_folder,nonlinear_receipt=selected(root,key+'/nonlinear');record['nonlinear_outer_process_seconds']=nonnegative(nonlinear_receipt['whole_process_seconds'])
                record['nonlinear_process_status']=nonlinear_receipt['status']
                if nonlinear_receipt['status']!='completed':records.append(record);continue
                nonlinear=nonlinear_folder/'capture';check_nonlinear(nonlinear)
                if load(nonlinear/'manifest.json')['affine_capture_source']!=load(capture/'manifest.json')['source_revision']:raise ValueError('nonlinear source capture association')
                attempts=load(capture/'manifest.json')['attempts']
                for case in ['syn-nl-lv-01','syn-nl-fuel-01']:
                    source=capture/case;native=load(source/'stdout.json');attempt=next(r for r in attempts if r['case_id'].lower()==case)
                    values={'configuration_construction_seconds':attempt['configuration_construction_ns']/1e9,'native_setup_seconds':native['setup_ns']/1e9,'native_optimization_seconds':native['solve_ns']/1e9,'native_outer_process_seconds':attempt['whole_process_ns']/1e9}
                    integration={}
                    for mode in ['cvodes','cvodes-tight','rk4','rk4-tight']:
                        target=nonlinear/case/mode;raw=load(target/'stdout.json');process=load(target/'process.json')
                        integration[mode]={'native_integration_seconds':nonnegative(raw['elapsed_seconds']),'whole_process_seconds':nonnegative(process['whole_process_seconds']),'status':raw['status']}
                    record['cases'].append({'case':case,'cost_seconds':{k:nonnegative(v) for k,v in values.items()},'integration':integration,'original_affine_objective':load(nonlinear/case/'affine-witness.json')['objective'],'nonlinear_executed_objective':load(nonlinear/case/'cvodes/record.json')['objective']})
            else:
                checks=check_nmpc(capture)
                for checked in checks:
                    case=checked['case_id'].lower();source=capture/case;attempt=load(source/'attempt.json');updates=[load(source/f'update-{j:03d}/result.json') for j in range(len(attempt['updates']))]
                    values={'controller_setup_seconds':sum(nonnegative(r['setup_seconds']) for r in updates),'optimization_seconds':sum(nonnegative(r['solve_seconds']) for r in updates),'held_cvodes_execution_seconds':sum(nonnegative(r['elapsed_seconds']) for r in attempt['execution_intervals'])}
                    integration={}
                    for mode in ['rk4','rk4-tight']:
                        raw=load(source/mode/'stdout.json');process=load(source/mode/'process.json')
                        integration[mode]={'native_integration_seconds':nonnegative(raw['elapsed_seconds']),'whole_process_seconds':nonnegative(process['elapsed_seconds']),'status':raw['status']}
                    record['cases'].append({'case':case,'cost_seconds':values,'integration':integration,'completed_holds':attempt['completed_holds'],'controller_status':attempt['status'],'original_executed_objective':attempt['completed_objective'],'checked':checked})
            record['offline_saved_checker_seconds']=time.monotonic()-start
            records.append(record)
    aggregates=[]
    for arm in ['affine','nmpc']:
        for case in ['syn-nl-lv-01','syn-nl-fuel-01']:
            samples=[c for r in records if r['arm']==arm and r['measured'] and r['status']=='completed' for c in r['cases'] if c['case']==case]
            aggregate={'arm':arm,'case':case,'completed_sample_count':len(samples),'expected_sample_count':5,'cost_seconds':{},'integration_seconds':{}}
            def stats(values):return {'count':len(values),'median':statistics.median(values),'min':min(values),'max':max(values)}
            if samples:
                for key in samples[0]['cost_seconds']:aggregate['cost_seconds'][key]=stats([s['cost_seconds'][key] for s in samples])
                for mode in samples[0]['integration']:
                    aggregate['integration_seconds'][mode]={key:stats([s['integration'][mode][key] for s in samples]) for key in ['native_integration_seconds','whole_process_seconds']}
            aggregates.append(aggregate)
    return {'schema':'csl.mpc11.alternating-timing/1','environment_sha256':sha(root/'environment.json'),'verdict':'inconclusive comparative performance: configured policy classes differ and native limiter profile is unavailable; descriptive repeated costs only',
            'clock_scopes':'Affine native setup/solve, Python configuration construction, NMPC per-update setup/solve/held CVODES, and nonlinear integration/process clocks are distinct. Warmups and saved checker clocks excluded from measured aggregates. CVODES affine integration clock includes integrator setup; NMPC held CVODES excludes its once-per-case integrator setup, retained in process envelope.',
            'records':records,'aggregates':aggregates}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    write(a.output,summarize(a.bundle.resolve()))
