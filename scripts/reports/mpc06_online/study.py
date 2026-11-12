#!/usr/bin/env python3
"""Capture public-port QPs and independent rational restricted-policy checks."""
import argparse
from fractions import Fraction as Q
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import subprocess
import time
from model import (R,plan,problem,optimizer,value,tightenings,representation_checks,replay)

METHODS=('finite-reference','polytope','inflated-zonotope','ellipsoid-certified')
INITIAL=((Q(1,8),Q(0)),(Q(3,8),-Q(1,8)),(-Q(1,4),Q(1,8)))


def encode(obj):
    if isinstance(obj,Q):return str(obj)
    raise TypeError(type(obj).__name__)


def exact_approximation_check(record):
    if record['schema']!='csl.mpc06-online-approximation/1' or record['direction']!='outer':
        raise ValueError('APP-04 binding mismatch')
    if record['orientation']!=[[1,0],[1,1]] or record['center']!=[0,0]:raise ValueError('APP-04 geometry mismatch')
    radii=list(map(Q,record['radii']))
    for s in (-R,R):
        for t in (-R,R):
            if s*s/radii[0]**2+t*t/radii[1]**2>1:raise ValueError('APP-04 lost an exact Z vertex')
    # Rational point strictly inside the emitted ellipse, next point outside it.
    s,t,w=Q(0),Q(5,32),R
    if s*s/radii[0]**2+t*t/radii[1]**2>1:raise ValueError('counterexample is not in emitted ellipse')
    if t*t/radii[0]**2+w*w/radii[1]**2<=1:raise ValueError('counterexample does not refute RPI')
    return dict(status='verified',enclosure=True,rpi=False,decision='reject for recursive tube tightening',
                counterexample=dict(st=[s,t],w=w,next_st=[t,w]))


def grid():
    started=time.perf_counter_ns();rows=[]
    for p in (Q(i,8) for i in range(-8,9)):
        for q in (Q(i,8) for i in range(-8,9)):
            candidates={method:problem((p,q),tightenings(method)) for method in METHODS}
            reference=candidates['finite-reference']
            for method,qp in candidates.items():
                if qp['feasible'] and not reference['feasible']:raise ValueError('tube feasibility escaped matched robust reference')
                if qp['feasible'] and (qp['lower']<reference['lower'] or qp['upper']>reference['upper']):
                    raise ValueError('tube interval is not a subset of exact matched robust interval')
                rows.append(dict(anchor=[p,q],method=method,qp=qp,
                    nominal_optimum=value(qp,optimizer(qp)) if qp['feasible'] else None))
    return dict(rows=rows,elapsed_ns=time.perf_counter_ns()-started,
        scope='exact rational elimination of N=3 terminal-zero plans with same fixed K; stage-specific disturbance supports; grid is not a full winning-set certificate')


def read_line(process,selector,transcript):
    if not selector.select(15):raise TimeoutError('native response exceeded 15 seconds')
    line=process.stdout.readline()
    if not line:raise RuntimeError('native driver ended without response')
    transcript.append(line)
    return line,json.loads(line)


def process_limits():
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(300,300))


def run(driver,output,repetitions):
    if output.exists():raise ValueError('output directory must be new')
    output.mkdir(parents=True);root=Path(__file__).resolve().parents[3]
    base_scenario=root/'benchmarks/scenarios/mpc06-nilpotent-tube-v1.json'
    (output/'base-scenario.json').write_bytes(base_scenario.read_bytes())
    result=dict(schema='csl.mpc06-online-study/1',base_scenario_sha256=hashlib.sha256(base_scenario.read_bytes()).hexdigest(),
        plant=dict(A=[[1,1],[0,1]],B=[[0],[1]],E=[[0],[1]],W=['-1/8','1/8'],X=[[-1,1],[-1,1]],U=[-1,1],
            observation='exact full state before input',uncertainty='stagewise independent compact additive interval',actuators='continuous',
            closed_loop_F=[[1,1],[-1,-1]],stability='F squared is zero; controllability matrix [B,AB] has nonzero determinant'),
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        source_status=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True),
        binary_sha256=hashlib.sha256(driver.read_bytes()).hexdigest(),platform=platform.platform(),
        logical_cpus=os.cpu_count(),load_before=os.getloadavg(),active_compiler_processes=subprocess.run(['pgrep','-c','cc1plus'],capture_output=True,text=True).stdout.strip(),
        resources=dict(cpu_seconds=300,address_space_bytes=8*1024**3,per_response_timeout_seconds=15,mechanism='POSIX RLIMIT_CPU/RLIMIT_AS; response watchdog; no native heap/RSS cap'),
        warmups=0,workspace_policy='fresh workspace per QP; process reused per repetition; first native call may initialize backend state',
        compiler=subprocess.check_output(['c++','--version'],text=True),architecture=platform.machine(),
        source_file_sha256={path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(__file__),Path(__file__).with_name('model.py'),Path(__file__).with_name('check.py'),root/'benchmarks/reporting/mpc06_online/driver.cpp']},
        build='Release required for comparative capture; explicit CMakeCache retained when available',
        policy=dict(kind='propagated-anchor',gain=[-1,-2],initial_error='zero',nominal_horizon=3,terminal='z3=0',native_optimum_absolute_tolerance='1/1000000',native_objective_absolute_tolerance='1/1000000',
            nominal_objective='sum(k=0..2,z_k^T z_k+v_k^2)',actual_objective='sum(t=0..2,x_t^T x_t+u_t^2)+x3^T x3',
            quantifier='deterministic nominal-anchor reoptimization with fixed ancillary K; all stagewise continuous disturbance sequences',
            exclusions=['measured-state reset','fixed-plan minimax optimum','general causal optimality','general feedback winning set']),
        representations=representation_checks(),grid=grid(),attempts=[],processes=[],repetitions=repetitions,
        timing_scope='native prepare/setup/solve separate; Python exact construction and checker separate; IPC/end-to-end separate; no performance winner')
    (output/'source').mkdir()
    for path in (Path(__file__),Path(__file__).with_name('model.py'),Path(__file__).with_name('check.py'),Path(__file__).with_name('render.py'),Path(__file__).with_name('evidence.py'),root/'benchmarks/reporting/mpc06_online/driver.cpp',root/'benchmarks/reporting/mpc06_online/CMakeLists.txt'):
        (output/'source'/path.name).write_bytes(path.read_bytes())
    cache=driver.parent/'CMakeCache.txt'
    if cache.exists():(output/'CMakeCache.txt').write_bytes(cache.read_bytes())
    for repetition in range(repetitions):
        folder=output/f'repetition-{repetition:02}';folder.mkdir();stdout=[];startup=time.perf_counter_ns()
        with (folder/'stderr.txt').open('w') as stderr:
            process=subprocess.Popen([str(driver)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1,start_new_session=True,preexec_fn=process_limits)
            selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
            try:
                line,approx=read_line(process,selector,stdout)
                approx_check_start=time.perf_counter_ns();approx_check=exact_approximation_check(approx)
                approx_check['checker_ns']=time.perf_counter_ns()-approx_check_start
                proc=dict(repetition=repetition,approximation=approx,independent_approximation=approx_check,
                    process_startup_and_offline_wall_ns=time.perf_counter_ns()-startup,
                    requested_native_threads=1,actual_native_threads='unavailable',peak_rss='unavailable',memory_enforcement='observation-only')
                methods=METHODS if repetition%2==0 else METHODS[::-1]
                for initial in INITIAL:
                    for method in methods:
                        anchor=initial;controls=[];steps=[];failed=False
                        attempt=dict(repetition=repetition,initial=initial,method=method,status='completed',steps=steps)
                        result['attempts'].append(attempt)
                        for stage in range(3):
                            construction=time.perf_counter_ns();qp=problem(anchor,tightenings(method,stage));construction_ns=time.perf_counter_ns()-construction
                            if not qp['feasible']:
                                attempt.update(status='inconclusive',reason='empty exact tightened interval');failed=True;break
                            request=[qp['quadratic'],qp['linear'],qp['offset'],qp['lower'],qp['upper']]
                            request_text=' '.join(format(float(x),'.17g') for x in request)+'\n'
                            row=dict(stage=stage,anchor=anchor,qp=qp,native_input=request_text,status='pending')
                            steps.append(row)
                            begin=time.perf_counter_ns();process.stdin.write(request_text);process.stdin.flush()
                            line,native=read_line(process,selector,stdout);wall=time.perf_counter_ns()-begin
                            check_start=time.perf_counter_ns()
                            row.update(native=native,exact_construction_ns=construction_ns,native_roundtrip_ns=wall)
                            if native['status']!='completed':raise ValueError('native QP failed')
                            a=Q(native['a']);target=optimizer(qp)
                            # Native coefficients were rounded when serialized. This comparison is
                            # numerical optimum evidence; safety below uses exact stored native a.
                            if abs(a-target)>Q(1,1000000):raise ValueError('native solution differs from exact strict-convex optimum')
                            if not qp['lower']<=a<=qp['upper']:raise ValueError('native first control outside exact safe interval')
                            if abs(Q(native['objective'])-value(qp,a))>Q(1,1000000):raise ValueError('native original objective mismatch')
                            row.update(checker_ns=time.perf_counter_ns()-check_start,exact_optimum_a=target,
                                exact_nominal_objective=value(qp,a),status='verified')
                            controls.append(a);anchor=(anchor[0]+anchor[1],anchor[1]+a)
                        if not failed:
                            checking=time.perf_counter_ns();actual=replay(initial,controls)
                            if not all(path['safe'] for path in actual['paths']):raise ValueError('native closed-loop history unsafe')
                            attempt.update(nominal_controls=controls,actual=actual,actual_checker_ns=time.perf_counter_ns()-checking)
                process.stdin.close();process.wait(timeout=15);proc['returncode']=process.returncode
                if process.returncode:raise RuntimeError('native process failed')
                result['processes'].append(proc)
            except (ValueError,RuntimeError,TimeoutError,subprocess.TimeoutExpired) as error:
                result['processes'].append(dict(repetition=repetition,status='inconclusive',reason=str(error)))
                if result['attempts'] and result['attempts'][-1]['repetition']==repetition:
                    result['attempts'][-1].update(status='inconclusive',reason=str(error))
                os.killpg(process.pid,9);process.wait()
            finally:
                selector.close();(folder/'stdout.txt').write_text(''.join(stdout))
                process.stdout.close()
                if not process.stdin.closed:process.stdin.close()
    result['load_after']=os.getloadavg()
    result['limitations']=['bounded deterministic-anchor profile only','initial grid is finite','numerical QP optimum checked against exact fixture, not solver certified',
        'native supported toolchain/platform capture is Linux only until hosted checks','prior invariant plot and fixed zero-plan cost remain immutable',
        'no speedup or universal winner; resource/process limiter profile pending']
    (output/'result.json').write_text(json.dumps(result,default=encode,indent=2)+'\n')
    paths=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output).as_posix()}\n' for p in paths))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--driver',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=5);args=parser.parse_args()
    if args.repetitions<1:parser.error('positive repetitions required; at least five for descriptive comparisons')
    result=run(args.driver.resolve(strict=True),args.output,args.repetitions)
    print(json.dumps(dict(processes=len(result['processes']),attempts=len(result['attempts']),failures=sum(p.get('status')=='inconclusive' for p in result['processes']))))

if __name__=='__main__':main()
