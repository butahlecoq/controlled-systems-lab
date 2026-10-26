# MPC-01 native solver runner

`CSL_BUILD_MPC01_REPORT=ON` enables a private runner for the four current
comparison fixtures: T-S01, T-S02, #421, and the distinct
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
  docs/research/evidence/b04-reference-v1/canonical-case.json
```

Pass `--reverse` to run HPIPM before OSQP; alternating this flag across
repetitions reduces fixed-order bias. The current executable emits provisional
JSONL attempt rows to stdout. They are functional and diagnostic output, not
yet the immutable `csl.comparison-record/1` artifact required for published
comparisons. The model currently uses binary64 residual checks, labelled
inconclusive; solver optimal status is not itself an independent proof.

The analytic infeasible and unbounded rows exercise outcome handling. OSQP's
precise primal/dual infeasibility statuses map to `infeasible`/`unbounded`;
inaccurate certificates remain `undetermined`. HPIPM returns status 2 on the
current fixtures, which this runner also retains as `undetermined`. Objective
fields are null unless the outcome is `optimal` or `feasible`, so solver
sentinel values and non-optimal iterates are not presented as solution
objectives. Non-optimal primal vectors are labelled candidate iterates, not
feasible trajectories.

This slice does not implement Strategy A/B outcomes, the shared
comparison-record codec, independent report review, or a solver-trajectory
plot backed by a canonical comparison record. The separate
`b04-reference-v1/native-smoke-20261026` projection overlays one cold smoke
trajectory per solver with the exact witness; it is illustrative, not a
repeated benchmark, and its residual checks are inconclusive. The B04 Pages
example remains the exact-witness illustration.
