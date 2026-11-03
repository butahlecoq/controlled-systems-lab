# MPC-01 native solver runner

`CSL_BUILD_MPC01_REPORT=ON` enables a private runner for the five current
comparison fixtures: T-S01, T-S02, the singular T-S03 profile, #421, and the distinct
`b04-reference-v1` case. Two additional analytic diagnostic cases exercise
infeasible and unbounded outcomes. It builds static OSQP 1.0.0, HPIPM
`e3a56c1caddd7f12d125d84f337b9a9e5c186271`, and BLASFEO
`d6251233923c9b475fe894fb729fb63ab693e301` in a nested build. Archive SHA-256
values and build options are pinned in `native/CMakeLists.txt`.

The report target is opt-in and is not installed or exported by CSL. These
dependencies do not enter the core library or a consumer's `find_package(CSL)`
graph. No package or release is needed for this private comparison work. The
runner is not a redistributable binary. OSQP's source is Apache-2.0; HPIPM and
BLASFEO are BSD-2-Clause. Their source archives retain their license files in
the local build tree.

Build and run the functional smoke profile:

```sh
cmake -S . -B build/mpc01 -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DCSL_BUILD_MPC01_REPORT=ON \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF
cmake --build build/mpc01 --target csl_mpc01_report mpc01_model_tests --parallel 4
ctest --test-dir build/mpc01 -R '^mpc01_(model_contract|native_smoke)$' --output-on-failure
build/mpc01/csl_mpc01_report \
  examples/scenarios/double-integrator-generality.json \
  docs/research/evidence/b04-reference-v1/canonical-case.json \
  --records build/mpc01/comparison-records.jsonl
build/mpc01/csl_mpc01_report --verify-records build/mpc01/comparison-records.jsonl
```

Pass `--reverse` to run HPIPM before OSQP; alternating this flag across
repetitions reduces fixed-order bias. The runner writes native attempt rows to
stdout and, when `--records` names a new file, one self-contained
`csl.comparison-record/1` archive per fixture. Each archive binds the exact
input bytes, all four solver/start-mode arms, run records, measurements,
dependency hashes, source/build/runtime facts, and per-attempt native settings.
`--verify-records` checks saved archives without invoking a solver. Repetition
and cold/warm identity are recorded separately: this functional smoke has one
attempt for each of cold and warm/fallback per solver, not a repeated timing
comparison. The model's binary64 feasibility checks remain inconclusive, and
solver optimal status is not an independent optimality proof.

The five-repetition B04 native comparison, its six canonical comparison
records, timing summary, and representative cold trajectory projections are
preserved under
`docs/research/evidence/mpc01-external-qps-20261026/`. Run
`scripts/reports/mpc01/summarize_repeated_comparison.py` with the saved records
and runner stdout to reproduce the summary and the flow/working-stock figure.
The figure selects one actual cold path per solver, choosing the repetition
whose solve time is closest to that solver's five-run median. Paths are not
averaged. The run records OSQP and HPIPM iteration counts. In this B04 case,
the cold solve medians are 162.5 ms at 33,125 OSQP iterations and 0.994 ms at
30 HPIPM iterations; those microbenchmarks do not establish an overall solver
or control-strategy winner.

The expanded seven-case capture is saved under
[`mpc01-external-qps-20261026-r3`](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/).
It was built from clean Release source commit `943c63a637a260cb7ddcf8a20822e05a32aa228d`
and retains seven canonical records / 140 attempts, a separate one-repetition
process profile, and a regenerated B04 projection figure. The B04 cold solve
medians in this capture are 163.642 ms for OSQP and 1.011 ms for HPIPM; these
are native QP solve-phase measurements, not an end-to-end or strategy winner.
On the new singular T-S03 case, all OSQP cold/warm attempts returned native
`solved` with original objective 0–2.24e-14; HPIPM hit its 1,000-iteration
limit (status 1), retained as `undetermined` with its candidate iterate. The
fixture's exact objective reduction and full optimal face are stated in the
saved summary.

The analytic singular T-S03 case has dynamics `x[t+1] = u[t]`, box controls,
and terminal objective `(x2-1)^2`. Its joint-control Hessian is singular and
its exact minimizing face is `{(u0,u1): 0<=u0<=1, u1=1}`; the runner checks
objective values along that face while retaining native solver witnesses.
The seven-case r3 capture also includes a separate exact-rational checker for
all 90 native attempts classified optimal. It reconstructs states from the
saved binary64 controls as exact dyadic rationals, checks original bounds and
dynamics, and stores exact feasible objective upper bounds beside analytic
lower bounds. This replaces residual-only feasibility evidence for these
saved controls; the solver status itself remains a native classification.
The analytic infeasible and unbounded rows exercise outcome handling. OSQP's
precise primal/dual infeasibility statuses map to `infeasible`/`unbounded`;
inaccurate certificates remain `undetermined`. HPIPM returns status 2 on the
current fixtures, which this runner also retains as `undetermined`. Objective
fields are null unless the outcome is `optimal` or `feasible`, so solver
sentinel values and non-optimal iterates are not presented as solution
objectives. Non-optimal primal vectors are labelled candidate iterates, not
feasible trajectories.

One paired Strategy A/B run on T-S01 is saved in
[`strategy-ab-ts01-summary.md`](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-summary.md), its standalone [saved-data HTML report](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-summary.html), and the T-S01 [control-plane figure](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-control-plane.svg).
It verifies both registered strategies on that small analytic fixture, but
does not cover T-S02, #421, or B04. The broader Strategy A/B matrix remains
open; exact feasibility and candidate objective bounds for the external
solvers' optimal attempts are in the r3 bundle. The separate
`b04-reference-v1/native-smoke-20261026` projection overlays one cold smoke
trajectory per solver with the exact witness; it is illustrative, not a
repeated benchmark, and its residual checks are inconclusive. The B04 Pages
example remains the exact-witness illustration.

Package the saved Strategy A/B attempts as a canonical comparison record:

```sh
python3 scripts/reports/mpc01/build_strategy_ab_records.py \
  --events docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-events.jsonl \
  --scenario examples/scenarios/two-stage-integrator.json \
  --environment docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-environment.json \
  --codec-environment docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-csl-environment.json \
  --output docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-comparison-record.json
```

The record keeps the saved event lines, including warmups, in source order by
strategy and repetition. The capture has no enforced resource cap, so its
timings remain descriptive.

A second T-S01 capture is retained in
[`strategy-ab-ts01-limited-capture/`](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/).
Its [HTML report](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-summary.html)
shows both strategies in the control plane; the [resource profile](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/resource-profile.json)
and [canonical comparison record](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-comparison-record.json)
retain the process-tree cap and all 16 attempts. The [capture supervisor](../../../docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/capture-supervisor.py)
records its exact process-group watchdog behavior. The capture completed in
67.224 ms, peaked at 10,018,816 bytes under a 2 GiB cgroup-v2 memory cap, used
no swap, and recorded no memory-limit events. Seven measured pairs passed per
strategy. Their descriptive end-to-end medians were 5.322090 ms for reach-back
(range 5.254692–5.786888 ms) and 1.281738 ms for Strategy B (range
1.266303–1.402075 ms). This lower-cap profile uses a suite-level 300-second
wall limit, not a per-trial deadline; it is not the comparison-program default
profile and supports no general performance-winner claim.

## Per-attempt resource profile

The follow-up capture in [`mpc01-per-attempt-20261103-r3`](../../../docs/research/evidence/mpc01-per-attempt-20261103-r3/benchmark-summary.md) closes the prior attempt-scope gap. The private runner has a `--single-attempt` mode and `--records-from-attempts` packer. Run every fixture, solver, start mode and repetition in a separate transient systemd user scope:

```sh
python3 scripts/reports/mpc01/run_resource_limited_attempts.py \
  --output-dir docs/research/evidence/mpc01-per-attempt-20261103-r3 \
  --binary build/mpc01/csl_mpc01_report --repetitions 5
python3 scripts/reports/mpc01/run_exact_checker_limited.py \
  --bundle docs/research/evidence/mpc01-per-attempt-20261103-r3
python3 scripts/reports/mpc01/summarize_per_attempt.py \
  --bundle docs/research/evidence/mpc01-per-attempt-20261103-r3
```

The runner serializes the fixtures and runs sequentially. Each scope enforces a 300-second process-tree watchdog, 8 GiB cgroup-v2 memory cap, no swap, 100% CPU quota, and one pinned logical CPU. Warm-start attempts include their cold seed solve in the same scope and retain that seed solve duration separately. Every native result is retained with its individual resource receipt; the seven canonical comparison records embed those receipts in their measurement events. The checker runs separately with a 5-second wall limit and the same memory/no-swap cap. Refused, failed, timed-out and resource-limited attempts remain explicit records.

The run retained 140/140 completed attempts and passed exact record decoding and 90 exact-rational candidate checks. It adds a four-state B04 plot from representative saved cold paths in the `(x1,x2)` oxidizer flow/stock and `(x3,x4)` fuel flow/stock planes, with each subsystem's flow bounds shown. The five-repetition per-fixture solve medians and ranges, attempt resource receipts, raw events, exact checks and checksums are in the linked evidence bundle. These are per-fixture native solver timings; they do not establish a general winner or end-to-end MPC latency.

## Strategy A/B per-attempt capture

For registered Strategy A/B, use `--measure-attempt` to restart the example for each strategy/repetition member. `run_strategy_ab_per_attempt.py` alternates five measured pairs after one excluded warmup pair and places every member in its own 300-second, 8 GiB, no-swap cgroup-v2 process scope. It keeps failures and timeout receipts in the event stream and resource profile. This ensures every individual strategy call has a hard process-tree limit; earlier `strategy-ab-ts01-limited-capture` and `strategy-ab-ts02-limited-capture` bundles are suite-limited historical captures and remain unchanged.

```sh
python3 scripts/reports/mpc01/run_strategy_ab_per_attempt.py \
  --root . \
  --build-dir build/issue597-attempt \
  --binary build/issue597-attempt/examples/registered_synthesis_comparison \
  --scenario docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts02-limited-capture/scenario.json \
  --profile ts02_constant_integrator \
  --binary-source-commit af4aa5cec4c8a9673460da63475698c2bd76a92a \
  --output-dir /var/tmp/mpc01-strategy-ab-ts02-per-attempt
```

The runner writes merged immutable attempt events, capture and codec environments, per-attempt resource receipts, individual stdout/stderr, and exact attempt rows beneath the new output directory. It reads compiler ID/version from the configured CMake compiler metadata, retains the compiler path/banner, and binds the executable to `--binary-source-commit` (default: `HEAD`). The source-tree digest is computed from that Git commit, even when the capture checkout has later documentation or reporting commits. It also writes a build note with the configured CMake metadata, compile/link inputs, object-file digest, and executable digest. Use `build_strategy_ab_records.py` to package the events into a canonical comparison record, then `summarize_strategy_ab_ts02.py` to validate the record and produce the control-plane figure and report. Timing scope remains strategy preparation through two original-problem witness checks; these tiny analytic profiles support no general performance-winner claim.
