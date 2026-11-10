"""Extract scoped initial cost observations from checked native/reference records."""
import json
from pathlib import Path
import re
from benchmarks.reporting.mpc10.evidence import checked_verification,load,sha


def metrics(bundle,verification):
    checked=checked_verification(bundle,verification);rows=[]
    for report in checked['reports']:
        case=bundle/report['id'];s=load(case/'fixture.json');native=load(case/'native/stdout.txt');np=load(case/'native/process.json');sp=load(case/'scip-process/process.json');scip=load(case/'scip/results.json');branches=native.get('branches',[])
        load_seconds=[];solve_seconds=[];iterations=[];observed_threads=[]
        for branch in branches:
            diagnostics=branch.get('result',{}).get('raw_diagnostics','')
            for name,values,convert in [('native.load_seconds',load_seconds,float),('native.solve_seconds',solve_seconds,float),('native.simplex_iterations',iterations,int),('native.scheduler_threads',observed_threads,int)]:
                matches=re.findall(r'^'+re.escape(name)+r'=(.+)$',diagnostics,re.MULTILINE)
                if len(matches)!=1:raise ValueError('missing/ambiguous native diagnostic cost: '+name)
                values.append(convert(matches[0]))
        attempts=scip.get('attempts',[]);global_record=next((a['result'] for a in attempts if a['relative_path']=='global'),None);fixed=[a['result'] for a in attempts if a['relative_path'].startswith('branch-')]
        rows.append({'id':s['id'],'product':s['product'],'horizon':s['horizon'],'physical_dimension':2,'active_scalar_coordinate':1,'native_status':native['status'],'checked_native':report['native'],'checked_scip':report['scip'],'native_branches':len(branches),'native_total_lp_variables':sum(len(b['program']['linear']) for b in branches if 'program' in b),'native_total_lp_rows':sum(len(b['program']['matrix']) for b in branches if 'program' in b),'native_simplex_iterations_sum':sum(iterations) if iterations else None,'observed_scheduler_threads':sorted(set(observed_threads)),
            'exact_optimum':report.get('exact_optimum'),'all_tie_count':len(report.get('exact_all_optimal_paths') or []),'native_core_family_verification':native.get('family_verification'),'native_seconds':{'provider_registration':native.get('provider_setup_ns',0)/1e9 if 'provider_setup_ns' in native else None,'history_enumeration':native.get('history_enumeration_ns',0)/1e9 if 'history_enumeration_ns' in native else None,'hybrid_enumeration_probe':native.get('path_enumeration_probe_ns',0)/1e9 if 'path_enumeration_probe_ns' in native else None,'formulation_with_internal_enumeration':native.get('enumeration_and_formulation_ns',0)/1e9 if 'enumeration_and_formulation_ns' in native else None,'portfolio_prepare_run_and_record':native.get('solve_portfolio_ns',0)/1e9 if 'solve_portfolio_ns' in native else None,'native_lp_load_sum':sum(load_seconds) if load_seconds else None,'native_lp_solve_sum':sum(solve_seconds) if solve_seconds else None,'family_verification':native.get('family_check_ns',0)/1e9 if 'family_check_ns' in native else None,'whole_worker':np['whole_process_seconds']},
            'scip_global':global_record,'scip_fixed_branch_totals':{'count':len(fixed),'formulation_and_setup_seconds':sum(a['formulation_and_setup_seconds'] for a in fixed),'optimization_seconds':sum(a['optimization_seconds'] for a in fixed)},'scip_whole_worker_seconds':sp['whole_process_seconds'],'resource_receipts':{'native':np,'scip':sp}})
    return {'schema':'csl.mpc10.initial-observations/1','verification_sha256':sha(verification),'generator_sha256':sha(Path(__file__)),'cases':rows,'verdict':'single bounded configured observations only; no performance ranking, timing ratio or general scalability claim','clock_scopes':'Provider registration, independent enumeration probe, portfolio construction and solve wrapper, inner HiGHS load/run, independent family check, unrestricted SCIP model setup/optimization and extra fixed-branch checks are distinct or nested. Whole workers include startup and serialization. No absent phase is relabelled zero. Dimension2 has one active scalar coordinate.'}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--verification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    a.output.write_text(json.dumps(metrics(a.bundle.resolve(),a.verification.resolve()),indent=2,allow_nan=False)+'\n')
