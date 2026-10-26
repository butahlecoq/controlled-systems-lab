#!/usr/bin/env python3
"""Summarize canonical MPC comparison records and render representative B04 projections."""

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import b04_native_smoke_projection as projection


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--attempts", required=True, type=Path,
                        help="runner stdout JSONL, retained as a cross-check against record events")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--host-load", default="unavailable",
                        help="load averages and sampling point for the run")
    args = parser.parse_args()

    records = read_jsonl(args.records)
    stdout_rows = read_jsonl(args.attempts)
    required_cases = {
        "ts01-exact-v1", "ts02-constant-v1", "ts03-singular-v1", "infeasible-integrator-v1",
        "unbounded-integrator-v1", "double-integrator-421-v1", "b04-reference-v1",
    }
    rows_by_case: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    case_specs: dict[str, dict] = {}
    row_counter: Counter[str] = Counter()
    for record in records:
        if record.get("schema") != "csl.comparison-record/1":
            raise ValueError("unsupported comparison record schema")
        spec = json.loads(record["spec"])
        if spec.get("schema") != "csl.comparison-spec/3" or spec.get("repetitions") != 5:
            raise ValueError("expected a five-repetition comparison-spec/3 record")
        if len(spec.get("arms", [])) != 4 or len(record.get("attempts", [])) != 20:
            raise ValueError("each case must retain four arms and twenty attempts")
        case = None
        seen: set[tuple[int, int]] = set()
        for item in record["attempts"]:
            rep = item["repetition_index"]
            event = json.loads(item["measurement_payload"])
            if event.get("schema") != "csl.mpc01-comparison-event/1" or event.get("repetition") != rep:
                raise ValueError("measurement event repetition does not match its canonical attempt")
            native = event["attempt"]
            case = native["case_id"]
            pair = item["arm_index"], rep
            if pair in seen or item["arm_index"] >= 4 or rep >= 5:
                raise ValueError("duplicate or out-of-range arm/repetition identity")
            seen.add(pair)
            row_counter[json.dumps(native, sort_keys=True, separators=(",", ":"))] += 1
            rows_by_case[case].append((rep, native))
        if len(seen) != 20 or case is None:
            raise ValueError("comparison record has an incomplete attempt matrix")
        case_specs[case] = spec
    if set(case_specs) != required_cases:
        raise ValueError(f"case set differs: {set(case_specs) ^ required_cases}")
    stdout_counter = Counter(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in stdout_rows)
    if row_counter != stdout_counter:
        raise ValueError("canonical measurement events do not match runner stdout attempts")
    if len(stdout_rows) != len(records) * 20:
        raise ValueError("expected twenty native attempts per canonical case")

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    markdown = [
        "# MPC-01 five-repetition native solver comparison",
        "",
        "This is a new comparison on the frozen `b04-reference-v1` article-derived input and six analytic/general-purpose cases. It is not a historical B04 reconstruction. The native solver status is recorded separately from mathematical evidence. Binary64 trajectory diagnostics are inconclusive and do not establish optimality.",
        "",
        "## Run identity",
        "",
        f"- Records SHA-256: `{digest(args.records)}`",
        f"- Runner stdout SHA-256: `{digest(args.attempts)}`",
        f"- Canonical records: {len(records)}; attempts: {len(stdout_rows)}; repetitions per arm: 5.",
        "- Execution alternated which backend ran first on each repetition. Each backend used a fresh workspace for the cold attempt, then a separate fresh workspace seeded from that repetition's cold result when available. Warm fallback remains explicit.",
        "- Reported phases are formulation, setup, warm-start, solve and extraction. This excludes post-run independent proof work; the available binary64 residual diagnostics remain inconclusive.",
        "- No acados or Strategy A/B paired comparison is included. These records do not support a control-strategy or overall solver winner claim.",
        "- See `comparison-records.jsonl` for the canonical, self-contained archives; `runner-attempts.jsonl` preserves the runner's stdout rows.",
        "",
        "## B04 reference case: phase timing, microseconds",
        "",
        "Times are median (minimum–maximum) over five attempts. A performance difference is not an overall algorithm or strategy winner: setup variance and independent optimality evidence remain relevant.",
        "",
        "| Backend / start | Iterations | Formulation | Setup | Warm-start | Solve | Extraction | Outcome / start application |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    phase_names = ("formulation", "setup", "warm_start", "solve", "extraction")
    summaries: dict[tuple[str, str], dict] = {}
    for mode in ("cold", "warm_if_available"):
        for method in ("osqp-sparse-qp", "hpipm-structured-ocp-qp"):
            selected = [(rep, row) for rep, row in rows_by_case["b04-reference-v1"]
                        if row["method"] == method and row["start_mode"] == mode]
            selected.sort()
            if len(selected) != 5:
                raise ValueError(f"expected five B04 attempts for {method}/{mode}")
            summaries[(method, mode)] = {"rows": selected}
            phases = []
            for phase in phase_names:
                values = [row["timings_ns"][phase] / 1000 for _, row in selected]
                phases.append(f"{statistics.median(values):.1f} ({min(values):.1f}–{max(values):.1f})")
            outcomes = ", ".join(sorted({row["mathematical_outcome"] for _, row in selected}))
            applied = sum(bool(row["warm_start_seed_applied"]) for _, row in selected)
            iteration_values = [row["solver_iterations"] for _, row in selected]
            if any(value is None for value in iteration_values):
                raise ValueError(f"missing solver iteration count for completed {method}/{mode} attempts")
            iteration_label = (f"{int(statistics.median(iteration_values))} "
                               f"({min(iteration_values)}–{max(iteration_values)})")
            label = "OSQP" if method == "osqp-sparse-qp" else "HPIPM"
            markdown.append("| " + " | ".join([f"{label} / {mode}", iteration_label, *phases,
                f"{outcomes}; seed applied {applied}/5"]) + " |")

    markdown.extend(["", "## Native solver classification and termination", "",
                     "These are solver-status classifications; they are not independent mathematical outcome claims.",
                     "", "| Case | OSQP classification / termination | HPIPM classification / termination |", "|---|---|---|"])
    for case in sorted(rows_by_case):
        method_outcomes = {}
        for method in ("osqp-sparse-qp", "hpipm-structured-ocp-qp"):
            values = sorted({row["mathematical_outcome"] for _, row in rows_by_case[case]
                             if row["method"] == method})
            terms = sorted({row["termination"] for _, row in rows_by_case[case]
                            if row["method"] == method})
            method_outcomes[method] = f"{', '.join(values)} ({', '.join(terms)})"
        markdown.append(f"| `{case}` | {method_outcomes['osqp-sparse-qp']} | {method_outcomes['hpipm-structured-ocp-qp']} |")

    reference = json.loads(projection.REFERENCE.read_text(encoding="utf-8"))
    exact_norm = float(reference["exact_norm_optimum_decimal"])
    b04_all = [row for _, row in rows_by_case["b04-reference-v1"]]
    objective_values = [row["original_objective"] for row in b04_all]
    residual_values = [max(row["original_data_diagnostics"][key] for key in (
        "max_dynamics_residual", "max_state_bound_violation", "max_control_bound_violation"))
        for row in b04_all]
    markdown.extend([
        "", "## B04 diagnostics", "",
        f"- Exact reference norm: {exact_norm:.12f}.",
        f"- Native original-norm range: {min(objective_values):.12f}–{max(objective_values):.12f}; max absolute difference from exact reference: {max(abs(v-exact_norm) for v in objective_values):.6g}.",
        f"- Largest binary64 dynamics/bound residual across native attempts: {max(residual_values):.6g}; diagnostics remain inconclusive.",
        "- The five cold paths per backend are not averaged. The figure selects the cold repetition whose solve duration is closest to that backend's median cold solve duration. It is a representative trajectory, not a median trajectory.",
        "",
        "## Singular T-S03 analytic reference",
        "",
        "For this fixture, the state recurrence is `x[t+1]=u[t]`, with both controls in `[0,1]`, and the terminal objective is `(x2-1)^2`. Therefore the objective reduces to `(u1-1)^2`: its exact minimum is zero and its complete optimal control face is `{(u0,u1): 0<=u0<=1, u1=1}`. The first control is a singular zero-curvature direction. This exact derivation checks solver objective values without requiring identical witnesses; it does not certify general family completeness for either native QP backend.",
        "",
        "## Limiter and interpretation",
        "",
        f"Solver iteration counts explain work per solve: cold B04 OSQP used 33,125 iterations, while HPIPM used 30. In a separate one-repetition diagnostic process run, the prior six-case runner consumed 0.417 s user CPU and 0.132 s system CPU over 0.550 s elapsed; that profile is not part of this timing sample. `process-profile.txt` in the earlier evidence bundle records those aggregate times. The repeated run did not enforce per-attempt wall or memory caps; its records mark memory as unlimited. It is a local exploratory measurement rather than the enforced-comparison resource profile. These tiny QP cases are microbenchmarks. They do not establish end-to-end planning latency or a control-strategy winner. Host load sampled just after this run was {args.host_load} with 8 logical CPUs.",
        "",
    ])
    (output / "benchmark-summary.md").write_text("\n".join(markdown), encoding="utf-8")

    chosen_rows = []
    chosen_meta = []
    for method in ("osqp-sparse-qp", "hpipm-structured-ocp-qp"):
        selected = summaries[(method, "cold")]["rows"]
        median_solve = statistics.median(row["timings_ns"]["solve"] for _, row in selected)
        rep, row = min(selected, key=lambda pair: (abs(pair[1]["timings_ns"]["solve"] - median_solve), pair[0]))
        chosen_rows.append(row)
        chosen_meta.append({"method": method, "repetition": rep,
                            "solve_ns": row["timings_ns"]["solve"],
                            "median_cold_solve_ns": int(median_solve)})
    attempts_path = output / "b04-representative-cold-attempts.jsonl"
    attempts_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                                 for row in chosen_rows), encoding="utf-8")
    case = json.loads(projection.CASE.read_text(encoding="utf-8"))
    exact_states = [[float(value) for value in state]
                    for state in projection.check_saved_trajectory(
                        case, json.loads(projection.REFERENCE.read_text(encoding="utf-8")))]
    projection.DISPLAY = {
        "exact-reference": "Exact saved witness",
        "osqp-sparse-qp": f"OSQP cold, median-time rep {chosen_meta[0]['repetition'] + 1}",
        "hpipm-structured-ocp-qp": f"HPIPM cold, median-time rep {chosen_meta[1]['repetition'] + 1}",
    }
    svg = projection.render_svg(case, exact_states, chosen_rows)
    svg = svg.replace("Fuel reference case: native solver trajectories in two 2D projections",
                      "B04 fuel case: representative native trajectories in two 2D projections")
    svg = svg.replace("B04 native smoke trajectories projected from four states into two planes",
                      "B04 repeated benchmark trajectories projected from four states into two planes")
    svg = svg.replace("One cold OSQP trajectory and one cold HPIPM trajectory from a single smoke capture are overlaid with the exact saved reference witness.",
                      "Representative cold OSQP and HPIPM trajectories, selected from five repetitions by proximity to each backend median solve time, are overlaid with the exact saved reference witness.")
    svg = svg.replace("This is not a benchmark aggregate or historical B04 reconstruction.",
                      "The paths are representative individual attempts, not averaged trajectories or a historical B04 reconstruction.")
    svg = svg.replace("one cold smoke attempt per solver · not historical B04 or a repeated benchmark",
                      "five repetitions per solver · median-time representative cold paths · not historical B04")
    (output / "b04-repeated-benchmark-projections.svg").write_text(svg + "\n", encoding="utf-8")
    html = projection.render_html("b04-repeated-benchmark-projections.svg", attempts_path.name,
        "exact-optimal-reference.json", chosen_rows, exact_norm,
        digest(projection.CASE), digest(attempts_path),
        case_specs["b04-reference-v1"]["environment"]["build"]["source_revision"])
    html = html.replace("B04 native smoke trajectory projections", "B04 repeated benchmark trajectory projections")
    html = html.replace("Native solver output, shown as a diagnostic illustration",
                        "Repeated native solver runs, shown as a diagnostic illustration")
    html = html.replace("Native B04 smoke trajectories as two projections of the 4D state",
                        "B04 repeated benchmark trajectories as two projections of the 4D state")
    html = html.replace("The same 17 states from each four-dimensional trajectory appear in both panels.",
                        "Each path is one cold run selected because its solve time is closest to the backend's median across five repetitions; paths are not averaged.")
    html = html.replace("Download the two saved native attempt rows", "Download the two representative native attempt rows")
    html = html.replace('</p>\n<div class="scope">',
        ' · <a href="comparison-records.jsonl" download>Download canonical comparison records</a>'
        ' · <a href="benchmark-summary.md">Open timing summary</a></p>\n<div class="scope">')
    html = html.replace("This is one smoke capture, with one cold attempt per solver. It is an illustration of returned solver trajectories, not a repeated benchmark, canonical comparison record, independent optimality proof, or reconstruction of historical B04.",
                        "This figure summarizes a five-repetition comparison through representative individual cold trajectories selected by median solve-time proximity. It is not an averaged path, independent optimality proof, or reconstruction of historical B04.")
    html = html.replace("python3 scripts/reports/mpc01/b04_native_smoke_projection.py",
                        "python3 scripts/reports/mpc01/summarize_repeated_comparison.py --records <records.jsonl> --attempts <runner-stdout.jsonl> --output-dir <output-dir>")
    html = html.replace("Runner source commit:", "Runner source commit:")
    (output / "b04-repeated-benchmark-projections.html").write_text(html + "\n", encoding="utf-8")
    projection.shutil.copyfile(projection.REFERENCE, output / "exact-optimal-reference.json")
    manifest = {
        "schema": "csl.mpc01-repeated-benchmark-figure/1",
        "case_id": "b04-reference-v1",
        "records_sha256": digest(args.records),
        "stdout_attempts_sha256": digest(args.attempts),
        "selected_attempts_sha256": digest(attempts_path),
        "case_sha256": digest(projection.CASE),
        "comparison_spec_id": next(record["comparison_spec_id"] for record in records
            if any(json.loads(attempt["measurement_payload"])["attempt"]["case_id"] == "b04-reference-v1"
                   for attempt in record["attempts"])),
        "selection": chosen_meta,
        "figure_sha256": digest(output / "b04-repeated-benchmark-projections.svg"),
    }
    (output / "figure-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")


if __name__ == "__main__":
    main()
