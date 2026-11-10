# Execute and independently replay affine controls

This optional example-layer harness implements MPC-11 steps 3 and 5 for the two
accepted affine plans. It does not implement NMPC or complete issue #607. The
synthetic equations and physical units come from the canonical scenarios.

Build `csl_mpc11_nonlinear_replay` through the optional directory's CMake project,
using the same `CSL_SOURCE_ROOT` setup as [the affine consumer](AFFINE.md). The
new target links `CSL::simulation`. No core API or required dependency changes.
An equivalent small standalone build compiles `nonlinear_replay_bridge.cpp`
and `src/simulation/nonlinear_replay.cpp`, with the repository include directory,
the pinned JSON include directory, and C++20.

Run in the locked optional environment:

```sh
python benchmarks/reporting/mpc11/run_nonlinear.py \
  --affine-bundle <VERIFIED_AFFINE_BUNDLE> \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay --output <NEW_OUTPUT_DIR>
python benchmarks/reporting/mpc11/check_nonlinear_saved.py --bundle <NEW_OUTPUT_DIR>
CSL_MPC11_REPLAY_BRIDGE=<BUILD_DIR>/csl_mpc11_nonlinear_replay \
  python -m unittest tests.reporting.test_mpc11_nonlinear
```

The source affine witness is rebuilt and checked before any execution. Each
request binds its scenario, physical controls and original witness by SHA256.
Neither integrator consumes affine state predictions as its output. Both use
scaled states `z=x/scale`; controls retain their physical units. The CasADi
CVODES symbolic derivative and C++ CSL callback implement the original nonlinear
equations separately. Each original hold has 20 reporting subintervals. CVODES
integrates each hold once and returns those output samples. CSL restarts its
adaptive RK4 seam at each reporting boundary, repeating the same held control.

Nominal and tighter settings are retained for both integrators. To preserve the
original per-hold attempt ceiling, each CSL reporting interval receives one
twentieth of the declared 100000 attempts. CVODES uses that same conservative
5000-step cap per original hold. A process receives 300 CPU seconds, 300 wall
seconds and 8 GiB address space via POSIX limits and subprocess timeout.
Runs are sequential, with numerical libraries requested to use one thread.
Process startup and execution costs are recorded, not compared as performance.

Each raw process outcome is retained, including timeout or invalid output.
A failed integration retains its available prefix, never substitutes a plan,
and has no complete original objective. CSL cancellation, callback/domain
failure and attempt exhaustion retain their native statuses. CVODES failures
stop before the next hold and retain the previous complete holds. Negative
initial fuel mass has an explicit model-domain status. Analytic fixtures cover
LV coexistence, fuel decay/drain, hold association, cancellation and incomplete
prefixes. The replay seam's local error estimates remain numerical diagnostics.

The original dimensionless objective is recomputed from the final physical
state and original control schedule, with the fixed original interval count.
Physical state violations are sampled at report points, in each component's
physical unit. They are not continuous-time constraint certificates. Saved
checks rebuild source models/programs and validate associations, transforms,
prefixes, costs and sampled violations against raw outputs. They do not prove
that arbitrary substituted trajectory rows solve the ODE; the executable
independent replay and analytic fixtures provide the integration check.

Comparisons retain affine prediction versus nonlinear execution, CVODES versus
RK4, and tolerance sensitivity. Agreement, including identical RK4 rows at two
tolerances when every short report step is accepted, is not a certified error
bound. No nonlinear global optimum, robustness or reachable-set claim follows.
The published evidence remains separate from the later NMPC and figure steps.
