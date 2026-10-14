"""Create the immutable native SYN-03 Strategy A report bundle."""
from __future__ import annotations
import argparse,csv,hashlib,json,shutil
from pathlib import Path
import strategy_a_report as report

def write_json(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--collection",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args();collection=args.collection.resolve(strict=True);out=args.out.resolve()
    if out.exists(): raise SystemExit("immutable report output already exists")
    measurement=json.loads((collection/"collection.json").read_text(encoding="utf-8"))
    events=[json.loads(line) for line in (collection/"events.jsonl").read_text(encoding="utf-8").splitlines()]
    scenario={"profile":"ts01_exact_integrator","time_domain":"discrete","times":[0,1,2],"initial_state":[0],"dynamics":[{"A":[[1]],"B":[[1]],"offset":[0]},{"A":[[1]],"B":[[1]],"offset":[0]}],"controls":[{"lower":[0],"upper":[1]},{"lower":[0],"upper":[1]}],"state_constraints":"universal at all stages","external_channels":0,"information":"nominal_open_loop","terminal_objective":{"Q":[[2]],"linear":[-2],"offset":1},"effective_request":{"target":"exact_optimal_relation","representation":"csl.polyhedron.h","assurance":"numerical","materialization_limit":None}}
    measurement["trajectory_checks"]={"representative_coordinates":[e["representative_coordinates"] for e in events],"original_objectives":[e["trajectory_objective"] for e in events],"maximum_residuals":[e["trajectory_max_residual"] for e in events],"equations_checked":["x0=0","x1=x0+u0","x2=x1+u1","0<=u0<=1","0<=u1<=1","J(x2)=(x2-1)^2=0"],"tolerances":{"absolute":1e-8,"relative":1e-8},"verifiers":sorted({e["residual_verifier"] for e in events})}
    record={"schema":report.SCHEMA,"report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,"harness_commit":measurement["harness_commit"],
      "algorithm":{"strategy_id":"csl.synthesis.reach-back","strategy_version":"1","profile_id":"ts01_exact_integrator","lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0","registered_providers":["csl.conversion.qhull@1.0.0+qhull.8.0.2","csl.convex.highs@1.0.0+highs.1.11.0","csl.geometry.affine-sum@1.0.0","csl.geometry.polyhedral-projection@1.0.0","csl.hull.lp-membership@1.0.0","csl.lp.highs@1.0.0+highs.1.11.0"]},
      "scenario":{"value":scenario,"sha256":report.digest(scenario)},"canonical_relation":{"coordinates":["x0","x1","x2","u0","u1"],"inequalities":[[0,0,0,1,0],[0,0,0,-1,0],[0,0,0,0,1],[0,0,0,0,-1]],"inequality_rhs":[1,0,1,0],"equalities":[[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]],"equality_rhs":[0,0,1,1],"parametric_form":"(0,s,1,s,1-s), 0<=s<=1","objective_minimum":0},
      "assumptions":["Discrete two-step scalar integrator at times 0, 1, 2.","Known initial state x0=0; all state constraints are universal.","Both transitions are x[t+1]=x[t]+u[t] with zero affine offsets and no external channels.","Continuous controls independently constrained to [0,1].","Nominal open-loop information; no observations or temporal constraints.","Terminal quadratic objective J(x2)=x2^2-2*x2+1=(x2-1)^2.","Effective request asks for exact_optimal_relation in H-representation under Assurance::numerical and no materialization limit."],
      "evidence_limits":report.EXPECTED_EVIDENCE_LIMITS,
      "measurement":{k:v for k,v in measurement.items() if k not in ("schema","raw_stdout_sha256","raw_stderr_sha256")}|{"events":events},
      "environment":measurement["environment"],"build":measurement["build"]}
    errors=report.validate(record)
    if errors: raise SystemExit("collection does not satisfy typed report contract: "+", ".join(errors))
    out.mkdir(parents=True)
    write_json(out/"records.json",record)
    write_json(out/"scenarios.json",record["scenario"])
    write_json(out/"measurement.json",record["measurement"])
    write_json(out/"environment.json",record["environment"])
    write_json(out/"build-provenance.json",record["build"])
    write_json(out/"profile.json",record["measurement"]["profile_attempt"])
    shutil.copyfile(collection/"events.jsonl",out/"measurement-events.jsonl")
    shutil.copyfile(collection/"process-stderr.txt",out/"process-stderr.txt")
    with (out/"trials.csv").open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=("repetition","warmup","elapsed_ns","termination","outcome","result_disposition","registry_verified","assurance","canonical_relation_checked","completeness_verifier","completeness_verifier_version","status","consumed_result_marker","providers","lineage","representative_coordinates","trajectory_objective","trajectory_max_residual","absolute_tolerance","relative_tolerance","residual_verifier","error"),lineterminator="\n");writer.writeheader();writer.writerows({key:event[key] for key in writer.fieldnames} for event in events)
    shutil.copyfile(collection/"commands.json",out/"commands.json")
    (out/"README.md").write_text(f"""# SYN-03 registered Strategy A T-S01 result\n\nThis measured bundle pins algorithm source `{report.SOURCE_COMMIT}` and harness `{record['harness_commit']}`. It contains one warmup and seven measured public StrategyPort executions; all results passed the compiled T-S01 verifier, canonical relation checks, and independent original-system checks on the constructed representative `(0, 0.25, 1, 0.25, 0.75)`. That representative is not an optimizer-returned witness and is not used to infer completeness. Performance conclusion: inconclusive because Windows denied sampled CPU stack profiling (0xc5585011), so no source-mapped limiter is known. This is not a Strategy A versus Strategy B comparison or speedup claim and does not close #67.\n\nReproduce from a clean checkout with the exact dependency archive hashes in `build-provenance.json`: run `tooling/syn03/strategy_a_collect.py`, then `tooling/syn03/strategy_a_build_bundle.py`. The report page is generated from validated typed records.\n""",encoding="utf-8",newline="\n")
    (out/"index.html").write_text(report.render_html(record),encoding="utf-8",newline="\n")
    files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob("*")) if p.is_file()}
    write_json(out/"manifest.json",{"schema":"csl.syn03-strategy-a-ts01-manifest/1","report_id":report.REPORT_ID,"source_commit":report.SOURCE_COMMIT,"harness_commit":record["harness_commit"],"files":files})
    print(report.REPORT_ID)
if __name__=="__main__": main()
