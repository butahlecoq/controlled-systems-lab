# Editable scenario templates

These executable examples use the strict versioned scenario JSON formats and the
public file loader. The original templates remain `csl.scenario/1`; the EXT-03
example uses `csl.scenario/2` to author full-history temporal rows. They demonstrate a minimal LTI model, stage-specific state
constraints, an LTV model, and the supported linear, quadratic and residual-norm
terminal objective forms. The loader validates and publishes problem data; it
does not run an optimizer or claim that the illustrative histories are optimal.

| File | Model and feature | Illustrative controls | State history | Original terminal objective |
| --- | --- | --- | --- | --- |
| `minimal-lti-linear.json` | Scalar LTI, unconstrained states | `(0.5)` | `(0, 0.5)` | `x = 0.5` |
| `state-constrained-quadratic.json` | Scalar LTI, box state set at all three time indices | `(0.25, 0.75)` | `(0, 0.25, 1)` | `x² - 2x + 1 = 0` at `x = 1` |
| `ltv-residual-norm.json` | Scalar two-stage LTV | `(1, 0)` | `(1, 2, 4)` | `||(x - 5, 0)||₂ = 1` at `x = 4` |
| `double-integrator-generality.json` | Two-state position/velocity double integrator, horizon 3, bounded intermediate states | `(0.5, 0, -0.25)` | `((0,0), (0.25,0.5), (0.75,0.5), (1.125,0.25))` | `(p - 1)² + (v - 0.5)² = 0.078125` at `(p,v)=(1.125,0.25)` |
| `temporal-slew-integrator.json` | Scalar two-step integrator with the cross-stage bound `|u1-u0| <= 1/4` | `(0, 0)` | `(0, 0, 0)` | `x2² = 0`; the hand-derived optimal control family is `u1=-u0`, `|u0|<=1/8` |

The first three templates label their scalar state coordinate `x` and control
coordinate `u`; both use normalized, dimensionless units. The double-integrator
template labels position, velocity and acceleration in SI units. The horizons
are discrete stage indices. `minimal-lti-linear` and
`state-constrained-quadratic` use one constant stage `(A,B)=([1],[1])`. The
state-constrained case applies `0 <= x[t] <= 2` at all three state indices
`t=0,1,2`. The LTV case uses `(A[0],B[0])=([1],[1])` then
`(A[1],B[1])=([2],[1])`. Dynamics apply
`x[t+1] = A[t]x[t] + B[t]u[t]` once per transition.

The illustrative inputs make arithmetic and independent checks transparent;
they are not physical coefficients or scientific criterion weights. The linear
coefficient `1` reports the terminal scalar directly. In the quadratic case,
`Q=2`, `q=-2`, and offset `1` give `0.5*Q*x² - 2*x + 1 = (x-1)²`, a simple
nonnegative criterion centered at `x=1`; the state interval `[0,2]` keeps the
listed history within its authored bounds. In the residual-norm case, `L=[[1],
[0]]` and target `[5,0]` produce residual `(x-5,0)`, so at the listed terminal
state `x=4` the original unsquared norm is exactly `1`. The target is chosen for
that easy-to-check value, not as a reference state from a physical system.

The double-integrator fixture is a task-generality example, not historical
reproduction or paired performance evidence. This template and its hand-derived
oracle establish the reusable input; the later resolve/prepare/execute/report
integration is tracked separately in [#421]. It uses a one-second sampling
interval and the already-discrete zero-order-hold transition
`p[t+1]=p[t]+v[t]+0.5*a[t]`, `v[t+1]=v[t]+a[t]`; the `times` field labels stages
and does not rescale these coefficients. Acceleration is bounded by `[-1,1]`
m/s². At the two constrained intermediate stages, position is in `[0,0.5]`
then `[0,1.5]` m and velocity is in `[-1,1]` m/s. The terminal target is
`(1 m, 0.5 m/s)`. `Q=2I`, linear coefficients `(-2,-1)` and offset `1.25`
encode `(p-1)²+(v-0.5)²` in the documented `0.5 xᵀQx + qᵀx + c` convention.
The listed control sequence is a hand-derived feasible example, not an optimal
solution or a solver trace.

Issue #421 connects this non-fuel fixture to the existing scenario CLI with a
`nominal_open_loop` candidate request. The run resolves the authored scenario,
prepares and executes both registered strategies, then saves one
`csl.run-statistics/9` artifact per strategy. In the current tested run,
reach-back is rejected by the convex adapter's `1e-12` matrix-removal threshold;
Strategy B completes with an undetermined candidate and one feasible incumbent
checked against the original model. The integration check verifies that
incumbent's trajectory, residual bound, and zero terminal tracking cost, and
preserves both attempt records. These are observed outcomes for this
configuration; changing the solver or model may change them.
The run makes no optimality, family-completeness, or paired-performance claim.
Exercise it without performance measurement through the installed-package
consumer suite, from the repository root:

```sh
ctest --preset highs -R '^installed_public_client$' --output-on-failure
```

The run request is `nominal_open_loop` with `candidate_relaxation`, numerical
assurance, `csl.polyhedron.h`, `csl.lp.highs`, and `csl.convex.highs`; the
scenario's default numerical tolerances are `1e-8` absolute and relative. This
fixture follows the non-fuel task selected in [decision #401](https://github.com/butahlecoq/controlled-systems-lab/issues/401), as implemented under #421; it does not reproduce a paper or historical run.

The CTest `scenario_cli_run_double_integrator_generality` checks this
resolve/prepare/execute/report path and confirms the candidate result is
reported without upgrading it to a verified complete family.

`temporal-slew-integrator.json` uses `csl.scenario/2` because scenario v1
reserves and rejects temporal data. Its one row is authored in canonical
`[x0,x1,x2,u0,u1]` order and imposes `u1-u0 in [-1/4,1/4]`. The exact feasible
control polygon and optimal segment are shown in the [temporal coupling
illustration](../../reports/algorithm-results/index.html#visual-ext03-slew-memory).
The illustration is derived from the authored inequalities; it is not an
optimizer trace or a claim that every registered strategy supports temporal
constraints. Strategy admission remains responsible for rejecting unsupported
profiles and representations.

[#421]: https://github.com/butahlecoq/controlled-systems-lab/issues/421

The histories and objective values in the table are hand-derived examples used
as independent loader/model/evaluator oracles. They are not solver output,
feasibility certificates for any future semantics, or optimality claims. The
quadratic convention is `0.5 xᵀQx + qᵀx + c`; a residual-norm objective is
`||Lx - target||₂` and is not squared. Omitted objective offsets default to
zero.

The incomplete archival record `benchmarks/scenarios/b04-historical.json` is
intentionally separate and non-executable. Do not copy unresolved historical
values into executable templates or treat the archived objective as replayed.
See [the scenario input contract](../../docs/contracts/scenario-input.md) and
[the schema notes](../../schemas/scenario/README.md) for the full grammar,
defaults and rejection rules.
