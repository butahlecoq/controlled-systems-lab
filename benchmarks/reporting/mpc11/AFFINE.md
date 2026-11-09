# Public CSL affine producer

This optional harness implements step 2 of [MPC-11](../../../docs/research/mpc11-implementation-plan.md)
for both authored scenarios. It exports physical and scaled affine coefficients,
constructs a joint state/control convex quadratic program, and solves it with
`make_convex_program`, `Registry<ConvexPort>` and `CSL::highs_convex`.
Python computes matrix exponentials and exports coefficients; it does not solve
the optimization problem. The saved formulation is a public joint program,
not a claim that a particular synthesis strategy admits this stage-cost API.

The recommended full-joint capture uses `--objective-multiplier 1000`: every
quadratic, linear and constant objective coefficient is multiplied by the same
positive factor. The complete unscaled program and its hash remain in the
bundle. Native objective values map back by division by 1000, and the checker
independently recomputes the authored physical objective. This conditioning
changes neither minimizers nor constraints. Native objective-unit residuals
and tolerances remain explicitly associated with the scaled program; they are
not certificates of original nonlinear optimality. The unscaled LV programs
reached native active-set time limits even after variable permutation and
state elimination. Both scaled full-joint and condensed probes completed with
the same authored objective; no core backend option or API was changed.

The optional `--condense` diagnostic route substitutes the affine state equalities into
the objective and state bounds, then solves the resulting control-space QP
through the same actual CSL provider. The complete original joint program,
its hash, and the full affine reconstruction map remain in the result bundle.
Every physical state and control is recovered and checked against the original
cost, state/input/trust bounds and affine recurrence. No state constraint or
objective term is dropped. Coefficient substitution is binary64 arithmetic;
this is algebraic equivalence with numerical checks, not validated arithmetic.
The direct joint route (no flag) and equivalent `--controls-first` ordering
remain available to reproduce retained native resource-limit outcomes. The
initial LV full-state programs cycled in the pinned QP active-set solver until
the native 290-second time limit. Reordering alone did not resolve the outcome.
Those attempts are preserved separately from the equality-eliminated capture.

The quadratic objective includes every running penalty and the terminal
quadratic. CSL's convention is `0.5*y'Q*y + linear'y + offset`; its half factor
is included explicitly in the exported diagonal. Variables are scaled physical
states in stage order, followed by scaled physical controls in stage order.
Physical state/input bounds intersect the affine-only trust region. Initial
states are fixed by variable bounds; each transition is a separate equality.
Fuel uses the authored reference-endpoint-matching offset, while LV uses its
frozen coexistence Jacobian and Taylor offset with an exponential discretization.
All coefficient operations use binary64; the exponential is numerical.

Build from a source checkout with CMake 3.31+, Ninja and a C++20 compiler:

```sh
cmake -S benchmarks/reporting/mpc11 -B "$MPC11_BUILD" \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release -G Ninja
cmake --build "$MPC11_BUILD" --target csl_mpc11_affine --parallel 2
OPENBLAS_NUM_THREADS=1 "$MPC11_VENV/bin/python" -m unittest \
  tests.reporting.test_mpc11_affine
OPENBLAS_NUM_THREADS=1 "$MPC11_VENV/bin/python" \
  benchmarks/reporting/mpc11/run_affine.py \
  --bridge "$MPC11_BUILD/csl_mpc11_affine" --output "$MPC11_RESULTS" --objective-multiplier 1000
```

Set these paths to dedicated user-owned directories. Use the
[locked optional environment](environment/README.md); the core library gains
no new dependency. The output directory must be new or empty. A tiny analytic
QP runs before the two full cases: `x0=0`, `x1=u`, minimize
`(x1-2)^2+u^2`, with exact answer `x1=u=1`, cost 2. The tests separately check
constant affine discretization, the quadratic half convention, fuel reference
endpoint reproduction and complete authored objective expansion.

Every pilot retains its input scenario, coefficient model, program, raw bridge
stdout/stderr, independent numerical witness check and process status. The
manifest binds program bytes, executable bytes, output hashes and source
revision. The bridge identifies its provider/version, assurance, termination,
mathematical outcome, numerical residuals, setup/solve durations, complete primal
or explicit refusal. The checker reconstructs physical states/controls,
replays the saved affine recurrence and evaluates the authored terminal and
running cost independently of the QP expansion. A failed or incomplete provider
outcome remains a record and makes the pilot command fail overall.

Each bridge process has a 300-second CPU/wall cap and 8 GiB address-space cap;
its context also supplies a 290-second cooperative deadline. Resource limits
are single-process POSIX limits, not native heap accounting. One native solver
thread is requested. Setup, solve and complete process durations have distinct
scopes. These pilots are correctness evidence; concurrent builds or other host
work exclude performance comparison claims.

An `optimal` native outcome has unestablished evidence support. Affine replay,
cost agreement and numerical KKT diagnostics do not establish validated
arithmetic, a complete optimizer family, nonlinear feasibility, nonlinear
optimality or robustness. This slice has no nonlinear execution or NMPC driver.
The two existing scenarios and their physical identities remain distinct from
historical fuel/LV artifacts. Later independent nonlinear replay and saved-data
figures remain #607 work. No library release is required for this optional
public-API consumer and report tooling.
