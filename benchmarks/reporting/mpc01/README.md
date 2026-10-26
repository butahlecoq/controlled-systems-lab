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

Strategy A/B paired outcomes remain outstanding from this external-solver
comparison; exact feasibility and candidate objective bounds for its optimal
native attempts are in the r3 bundle. The separate
`b04-reference-v1/native-smoke-20261026` projection overlays one cold smoke
trajectory per solver with the exact witness; it is illustrative, not a
repeated benchmark, and its residual checks are inconclusive. The B04 Pages
example remains the exact-witness illustration.
