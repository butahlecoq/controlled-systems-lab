# Current framework composition

Start with the [development entry point](../build/development.md), the
[installed-package examples](../../README.md#quick-start) and canonical
[glossary](../research/glossary.md). This page describes current implementation;
the [optimal-family architecture](modular-algorithms-and-solution-sets.md) retains
the wider mathematical requirements.

## Modules and public seams

| Responsibility | Public targets / interface | Owning implementation |
| --- | --- | --- |
| Immutable numeric/model/set data | `CSL::numeric`, `CSL::model`, `CSL::sets` | `src/numeric`, `src/model`, `src/sets` |
| Domains, objectives, resolved identity | `CSL::problem`, `CSL::objectives`, `CSL::resolved_problem` | `src/problem`, `src/optimization` |
| JSON scenario intake | `CSL::input`, `load_scenario_file` | `src/input` |
| Capability selection and retained providers | `CSL::registry`, `StrategyRegistry` | `src/registry` |
| LP / convex programs and native adapters | `CSL::optimization`, `CSL::convex`, `CSL::highs_lp`, `CSL::highs_convex`, `CSL::phase_one` | `src/optimization`, `src/adapters` |
| Geometry and conversion | `CSL::hull`, `CSL::polyhedral`, `CSL::affine_sum`, `CSL::qhull_conversion` | `src/geometry`, `src/adapters/polyhedral` |
| Forward reachability, terminal minimizers, recovery | `CSL::nominal_forward`, `CSL::terminal_minimizers`, `CSL::control_recovery` | `src/reachability`, `src/synthesis` |
| Strategy A / B and analytic profile | `CSL::strategy_a`, `CSL::strategy_b`, `CSL::strategy_ts01` | `src/synthesis/strategy_a`, `strategy_b`, `strategy_ts01` |
| Directional witness selection | `CSL::witness_selector`, registered `SelectorPort` | `src/synthesis/witness_selector.cpp` |
| Original-problem trajectory checks | `CSL::verification`, `verify_trajectory` | `src/verification` |
| Execution and portable records | `CSL::execution`, `CSL::artifacts` | `src/execution`, `src/artifacts` |
| Guarded paired application flow | `CSL::application`, `prepare_comparison`, `run_comparison` | `src/application` |
| Numerical report tooling | saved record validation and rendering | `benchmarks/reporting`, `scripts/reports` |

Headers live under `include/csl`. Authoritative contracts cover
[resolved problems](../contracts/resolved-problems.md), [registry](../contracts/registry.md),
[trajectory verification](../contracts/trajectory-verification.md),
[run records](../contracts/run-statistics.md) and [reports](../contracts/algorithm-report-records.md).
Native types stay behind adapters; mutable workspaces are exclusive per solve.

## Supported synthesis profiles

Strategy A composes forward reachability, terminal minimization and backward
joint-history recovery. Strategy B builds and optimizes a direct joint program.
Their general `nominal_open_loop` paths produce numerical candidate relations;
they do not establish general complete-family coverage. See the
[Strategy A implementation scope](../../src/synthesis/strategy_a/README.md).

Both strategies additionally admit the strictly checked `ts01_exact_integrator`
and `ts02_constant_integrator` profiles with compiled complete-family verifiers:

| Profile | Original problem and complete joint relation |
| --- | --- |
| T-S01 | Two-step scalar unit integrator, `x0=0`, independent `u0,u1` in `[0,1]`, unrestricted states, no external/history constraints, terminal cost `(x2-1)^2`. Optimum zero; all histories are `(x0,x1,x2,u0,u1)=(0,s,1,s,1-s)`, `s` in `[0,1]`. |
| T-S02 | Same integrator and domains, constant terminal objective `3` in the admitted linear, zero-quadratic or zero-map residual-norm form. Every feasible joint history is optimal. |

Exact coverage applies only to these reviewed predicates and canonical relations.
It is bound to the original problem, effective request, strategy/version and
executed lineage. It does not extend to changed horizons, dynamics, constraints
or objectives. Outer registry assurance remains numerical; generic validated
numerics are unavailable. The separate `csl.synthesis.ts01-analytic` registration
provides the narrow T-S01 analytic path; it is not a replacement for either
composed strategy.

The implemented `csl.selector.ts01-directions` selector minimizes supplied
`(u0,u1)` directions over its admitted T-S01 source family using a selected LP
provider. It returns consistent witnesses with source bindings. A recorded seed
is provenance, not a stochastic or uniform-sampling promise. Witnesses are not a
substitute for the whole family.

Independent trajectory verification recomputes original initial, dynamics,
domain, temporal and objective checks, with explicit binding expectations for
family claims. Witness feasibility, optimality, whole-family coverage and
validated assurance remain distinct. Compiled profile-specific family authority
does not make every numerical trajectory report a completeness proof.

## Runnable entry points and remaining work

The current [installed examples](../../README.md#quick-start) execute component
workflows, including real LP backend substitution; the two LP providers are not
two synthesis strategies. The scenario examples evaluate supplied controls.
`CSL::application` provides a reusable guarded paired-strategy flow: both
strategies are prepared against one immutable problem/request before either
workspace is created. Preparation is sequential through the registry contract,
so the first strategy planner may run before the second capability check; no
solver workspace or strategy execution starts unless both preparations succeed.
Complete families alone reach the selector, and selected witnesses are checked
against the original problem. Candidate and partial outputs remain typed
without selection if a strategy returns them; the current caller-visible
integration fixtures cover only successful complete-family T-S01/T-S02 flows.
Its result exposes the artifact layer's final
projections and the original-problem verification reports as typed in-memory
values. It does not claim to persist the paired comparison: run-statistics-v4
has no paired-comparison record, and its encoder rejects registered-completeness
payloads. Callers must use the artifact encoder and handle its actual typed
result; this API does not emit substitute JSON.
The delivered
[registered synthesis comparison](../../examples/registered_synthesis_comparison.cpp)
runs both strategies on the same immutable T-S01 problem, selects witness
histories and independently checks them against original problem data. Its JSON
summary identifies the shared problem/request, each strategy and outcome,
selected witnesses and verification status/residuals. It does not serialize the
live optimal-family relation or proof payload. This is a functional guarded
fixture example, not general profile support or paired performance evidence.
The [saved paired T-S01 report](../../reports/algorithm-results/syn-ts01-paired-20261014-b7f1ac0/index.html)
delivers measured records and standalone HTML for this fixture, with an
inconclusive performance conclusion and no general strategy ranking.

A general scenario-to-family-to-export application remains pending. General
family proofs, broader selector profiles, CLI behavior and trusted proof
serialization/replay retain their feature-ticket ownership. JSON run records
preserve metadata; decoding does not mint trusted complete-family authority.
The synthesis-to-report adapter remains missing glue. Saved LP/convex reports and the paired T-S01 fixture report do not supply a
general synthesis comparison.

Applications compose existing strategy preparation, `make_task` and
`Executor::run`, retain immutable resolved owners and actual provider provenance,
and pass original problems and witnesses to independent verification. Export
must consume saved owning results and verification records; rendering must not
invoke solvers. Future numerical algorithms follow the
[published-results process](published-algorithm-results.md). Historical fuel-model
restoration remains unresolved.
