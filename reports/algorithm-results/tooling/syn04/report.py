"""Typed saved-data report for registered SYN-04 Strategy B on T-S01."""
from __future__ import annotations
import hashlib
import html
import json
import math
import statistics

SCHEMA = "csl.syn04-strategy-b-ts01-report/1"
SOURCE_COMMIT = "2a5ab835295dfd22f02b19d440bb8158267d985a"
REPORT_ID = "syn04-strategy-b-ts01-20261014-2a5ab835"
EVENT_SCHEMA = "csl.syn04-strategy-b-ts01-measurement-event/1"

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def validate(record):
    errors=[]
    if record.get("schema") != SCHEMA: errors.append("schema")
    if record.get("source_commit") != SOURCE_COMMIT: errors.append("source_commit")
    if record.get("report_id") != REPORT_ID: errors.append("report_id")
    if record.get("algorithm") != {"strategy_id":"csl.synthesis.strategy-b","strategy_version":"1","profile_id":"ts01_exact_integrator","lp_provider":"csl.lp.highs@1.0.0+highs.1.11.0","convex_provider":"csl.convex.highs@1.0.0+highs.1.11.0"}:
        errors.append("algorithm")
    scenario=record.get("scenario",{})
    if not isinstance(scenario.get("value"),dict) or scenario.get("sha256")!=digest(scenario.get("value")):
        errors.append("scenario_hash")
    relation=record.get("canonical_relation",{})
    if relation != {"coordinates":["x0","x1","x2","u0","u1"],"inequalities":[[0,0,0,1,0],[0,0,0,-1,0],[0,0,0,0,1],[0,0,0,0,-1]],"inequality_rhs":[1,0,1,0],"equalities":[[1,0,0,0,0],[0,1,0,-1,0],[0,0,1,0,0],[0,0,0,1,1]],"equality_rhs":[0,0,1,1],"parametric_form":"(0,s,1,s,1-s), 0<=s<=1","objective_minimum":0}:
        errors.append("canonical_relation")
    measurement=record.get("measurement",{})
    events=measurement.get("events",[])
    if len(events)!=8 or [(x.get("repetition"),x.get("warmup")) for x in events] != [(0,True),*[(n,False) for n in range(1,8)]]:
        errors.append("event_matrix")
    if any(e.get("schema")!=EVENT_SCHEMA or e.get("status")!="passed" or e.get("result_disposition")!="complete_optimal_family" or e.get("termination")!="completed" or e.get("outcome")!="optimal" or e.get("registry_verified") is not True or e.get("assurance")!="numerical" or e.get("canonical_relation_checked") is not True or e.get("completeness_verifier")!="csl.verifier.ts01-analytic" or e.get("completeness_verifier_version")!="1" or type(e.get("elapsed_ns")) is not int or e["elapsed_ns"]<0 or not e.get("consumed_result_marker") or e.get("lp_provider")!="csl.lp.highs@1.0.0+highs.1.11.0" or e.get("convex_provider")!="csl.convex.highs@1.0.0+highs.1.11.0" or type(e.get("trajectory_objective")) not in (int,float) or e.get("trajectory_objective")!=0 or type(e.get("trajectory_max_residual")) not in (int,float) or not math.isfinite(e["trajectory_max_residual"]) or e["trajectory_max_residual"]<0 or e.get("absolute_tolerance")!=1e-8 or e.get("relative_tolerance")!=1e-8 or not e.get("residual_verifier") for e in events):
        errors.append("event_invalid")
    measured=[e["elapsed_ns"] for e in events[1:] if type(e.get("elapsed_ns")) is int]
    summary=measurement.get("timing_ns",{})
    if len(measured)!=7 or measured!=summary.get("observations"):
        errors.append("timing_observations")
    elif any(summary.get(k)!=v for k,v in {"median":statistics.median(measured),"min":min(measured),"max":max(measured),"range":max(measured)-min(measured)}.items()):
        errors.append("timing_summary")
    counts=measurement.get("counts",{})
    if counts!={"warmup":1,"measured":7,"passed":7,"failed":0,"all_outputs_consumed_and_validated":True}:
        errors.append("counts")
    if measurement.get("performance_conclusion")!="inconclusive": errors.append("performance_conclusion")
    if not measurement.get("limiter",{}).get("reason"): errors.append("limiter_gap")
    observation=measurement.get("result_observation",{})
    if observation!={"termination":"completed","outcome":"optimal","disposition":"complete_optimal_family","registry_verified":True,"assurance":"numerical","objective_lower":0,"objective_upper":0,"canonical_relation_checked_each_trial":True}:
        errors.append("result_observation")
    if measurement.get("trajectory_checks")!={"original_objectives":[e.get("trajectory_objective") for e in events],"maximum_residuals":[e.get("trajectory_max_residual") for e in events],"tolerances":{"absolute":1e-8,"relative":1e-8},"verifiers":sorted({e.get("residual_verifier") for e in events})}:
        errors.append("trajectory_checks")
    if measurement.get("scope") is None or "exact canonical H-relation" not in measurement.get("scope",""):
        errors.append("timing_scope")
    if record.get("evidence_limits") is None or not isinstance(record.get("evidence_limits"),list): errors.append("evidence_limits")
    return errors

def render_html(record):
    errors=validate(record)
    if errors: raise ValueError("invalid SYN-04 report: "+", ".join(errors))
    esc=lambda value: html.escape(str(value))
    measurement=record["measurement"]
    timing=measurement["timing_ns"]
    residuals=[e["trajectory_max_residual"] for e in measurement["events"]]
    dots="".join(f'<circle cx="{45+i*48}" cy="{190-(v/max(timing["max"],1))*125:.2f}" r="4" fill="#087e8b"></circle>' for i,v in enumerate(timing["observations"]))
    rows="".join(f"<tr><th scope=\"row\">{e['repetition']}</th><td>{e['elapsed_ns']}</td><td>{esc(e['trajectory_objective'])}</td><td>{esc(e['trajectory_max_residual'])}</td><td>{esc(e['result_disposition'])}</td><td>{esc(e['status'])}</td></tr>" for e in measurement["events"][1:])
    assumptions="".join("<li>"+esc(x)+"</li>" for x in record["assumptions"])
    limits="".join("<li>"+esc(x)+"</li>" for x in record["evidence_limits"])
    return ''.join([
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SYN-04 Strategy B T-S01 report</title><style>body{font:16px system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#18232d}table{border-collapse:collapse}td,th{border:1px solid #bac6cc;padding:.45rem .7rem;text-align:left}pre{overflow:auto;background:#f4f7f8;padding:1rem}.note{background:#fff4d6;padding:1rem}</style></head><body>',
        '<h1>Registered Strategy B on the T-S01 profile</h1>',
        '<p>This is one exploratory measurement of the integrated public StrategyPort path using registered HiGHS LP and convex providers. It is not a strategy comparison, speedup, application-scale result, or scalability claim.</p>',
        '<p>Algorithm source commit: <code>'+esc(record['source_commit'])+'</code>; harness: <code>'+esc(record['harness_commit'])+'</code>. Profile: <code>ts01_exact_integrator</code>. Assumptions:</p><ul>'+assumptions+'</ul>',
        '<h2>Analytic T-S01 relation</h2><p>For <code>x₀=0</code>, <code>xₜ₊₁=xₜ+uₜ</code>, <code>u₀,u₁∈[0,1]</code> and <code>J(x₂)=(x₂−1)²</code>, the complete relation is <code>(x₀,x₁,x₂,u₀,u₁)=(0,s,1,s,1−s)</code>, <code>0≤s≤1</code>. Each timed run required a registry-verified complete-family result and checked the literal canonical H-representation and exact membership/nonmembership points.</p>',
        '<p>Completeness is limited to this exact admitted T-S01 profile under its declared <code>Assurance::numerical</code> evidence path. Each output names the accepted compiled verifier <code>csl.verifier.ts01-analytic@1</code>; no generic strategy coverage or validated-arithmetic assurance is implied.</p>',
        '<p>Each result also retained one independently checked optimizer anchor with original objective 0. The reported maximum trajectory residuals are '+esc(min(residuals))+'–'+esc(max(residuals))+' under absolute and relative tolerances 1e−8; the exact verifier ID is in each raw event.</p>',
        '<h2>Observed timings</h2><p>'+esc(measurement['scope'])+'</p><p>One excluded warmup; seven measured runs. Median <strong>'+esc(timing['median'])+' ns</strong>; range '+esc(timing['min'])+'–'+esc(timing['max'])+' ns (width '+esc(timing['range'])+' ns). Failures: '+esc(measurement['counts']['failed'])+'.</p>',
        '<figure aria-label="Seven Strategy B timing observations"><svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Dots show the seven elapsed nanosecond observations" viewBox="0 0 390 220" width="390" height="220"><line x1="30" y1="190" x2="370" y2="190" stroke="#18232d" stroke-width="1"></line>'+dots+'<text x="200" y="215" text-anchor="middle">measured repetition</text></svg><figcaption>Raw observations are available in the linked JSONL and CSV files.</figcaption></figure>',
        '<table><thead><tr><th scope="col">Repetition</th><th scope="col">Elapsed (ns)</th><th scope="col">Anchor objective</th><th scope="col">Max residual</th><th scope="col">Result disposition</th><th scope="col">Validation</th></tr></thead><tbody>'+rows+'</tbody></table>',
        '<p class="note"><strong>Performance conclusion: inconclusive.</strong> A separate CPU profile was attempted with Windows Performance Recorder, but its system-performance policy setup failed (0xc5585011). Process CPU-time and memory counters are retained, but no trustworthy sampled call-stack/source hot spot was available to identify a limiter.</p>',
        '<h2>Evidence limits</h2><ul>'+limits+'</ul>',
        '<h2>Environment and reproduction evidence</h2><p>Machine, operating system, compiler, Release configuration, dependency pins, provider identity, system load observations, profiling attempt and all unavailable phase counters are retained in the machine-readable sidecars.</p>',
        '<p><a href="records.json">Typed report</a> · <a href="measurement-events.jsonl">Raw timing events</a> · <a href="trials.csv">Timing CSV</a> · <a href="measurement.json">Measurement and host evidence</a> · <a href="build-provenance.json">Build provenance</a> · <a href="scenarios.json">Scenario</a> · <a href="profile.json">Separate profile attempt</a></p>',
        '<p>This result is partial SYN-04 evidence and does not close issue <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/67">#67</a>.</p></body></html>'
    ])

if __name__=="__main__":
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");parser.add_argument("records")
    args=parser.parse_args();saved=json.loads(Path(args.records).read_text(encoding="utf-8"));errors=validate(saved)
    if errors: raise SystemExit("invalid report: "+", ".join(errors))
    print("SYN-04 Strategy B report valid" if args.check else render_html(saved))
