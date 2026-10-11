# Controlled Systems Lab: consolidated requirements and architecture specification

Date: 2026-10-11. Version: 0.6. Status: consolidated draft for owner/scientific review. This document records the conversation's decisions and turns them into traceable requirements. It is not an implementation plan or a claim that the product exists.

## Product intent

Build a convenient, general interface for controlled systems with replaceable mathematical algorithms, efficient native computation, explicit scientific guarantees and scalable execution. The original aerospace application supplies first archival benchmarks; it must not define the reusable core. Scientists should be able to compare methods, review assumptions/results and propose new algorithms through the public repository.

All newly authored artifacts are in English. Owner discussion is in Russian. The public project is [controlled-systems-lab](https://github.com/butahlecoq/controlled-systems-lab); scientific review uses issues with reproducible evidence.

## Authority and decision status

| Topic | Status and origin | Consequence |
|---|---|---|
| Architecture before numerical implementation | Confirmed owner requirement | Define replaceable contracts before implementing archival reproductions |
| Main language | Owner selected C++; C++20 carried forward as working standard | Native core; Python independent references are permitted |
| First workflow | Owner selected nominal optimal-control planning | Initially no process disturbance/second player |
| Control values | Owner selected continuous actions first | Preserve finite/mixed domains and separate future hybrid models |
| Initial time domain | Owner selected discrete models first | Scenario matrices describe stage transitions directly; continuous-time input/discretization is a later module |
| Primary output | Owner selected all optimal solutions | Preserve a joint relation, not only one trajectory or stage marginals |
| First family query | Owner selected different complete witnesses | Visual, numerical and runtime comparison of approaches |
| First method comparison | Owner selected the two optimization approaches; reachable-set approximations later | Reachability/backward-recovery strategy versus direct joint-trajectory optimization |
| Initial comparison presentation | Owner selected final results and trajectories as sufficient | Intermediate reachable sets, optimization-program dumps and step-by-step inspection are later features |
| Primary input workflow | Owner selected selectable scenario files; users create custom files from supplied templates | Basic cases require no C++ code; make the authored form simple and extensible |
| Objective modules | Recorded owner agreement | Linear, convex quadratic, weighted Euclidean residual terminal criteria first |
| Temporal constraints | Owner requested representability, exclusion from first experiments | Future supported lifts/strategies; no default added couplings |
| Verification | Recorded owner agreement | Numerical first; future claim-specific validated certificates |
| Archival baseline | Owner selected B04; later supplied table-file guidance | Preserve historical data and restoration status |
| B04 control bound | Owner said probably u in [-1,1] | Provisional hypothesis, not established canonical input |
| Testing | Owner explicitly requested module unit tests | Include unit, contract, mathematical and integration acceptance evidence |
| Delivery through subagents | Owner proposed specification -> tickets -> subagent implementation | Fix dependencies/ownership before parallel implementation |
| Library API, CMake, double, initial polyhedral strategy | Assistant proposals | Review with owner; do not label them prior owner decisions |
| Specific matrix/solver/test libraries, deployment targets, file syntax and launch interface | Open | Scenario-file input is confirmed; CLI/library packaging and any later graphical interface remain proposals |

The accepted language decision is [ADR 0001](../../architecture/decisions/0001-cpp20-core.md). Concrete native interfaces are in the subordinate [C++ contracts draft](2026-10-11-cpp-core-contracts-design.md). Earlier research/architecture notes remain supporting evidence; this document is the requirements entry point. If a supporting note conflicts with a confirmed requirement, record and reconcile the discrepancy before implementing it.

## Scope and release boundaries

The first proposed implementation slice is nominal discrete affine dynamics with known initial state, continuous convex polyhedral stagewise state/control sets, a supported structured convex terminal criterion, a dependency-preserving optimal family, witness extraction and independent numerical verification.

The model contract is broader than any one solver. Representable disturbances, observation channels, singular transitions, unbounded sets or future domains do not imply that the first algorithm supports them. Unsupported is a capability outcome, distinct from mathematical infeasibility.

The first completed comparison includes two synthesis strategies under the same problem/result contracts: a strategy based on historical reachability and backward control recovery, and direct optimization of the joint trajectory. Both must construct the supported optimal family, beyond finding a single minimizer. This compares end-to-end mathematical strategies; changing an LP backend is an independent replacement axis. Reachable-set approximations are explicitly deferred.

Later slices include extra geometry/solvers, inner/outer approximations, minimax/feedback, estimation, temporal lifts, finite/mixed controls, hybrid/nonlinear/descriptor models, validated arithmetic, bindings and optional remote/GPU execution. Each requires its own mathematical capabilities and acceptance cases. No claim that all these features can be implemented in the initial slice is implied.

## Requirements and acceptance trace

IDs are stable references for future tickets. C means a confirmed requirement; P means a concrete proposal awaiting written-design review; R means a reserved extension. Acceptance statements describe observable behavior, not a mandated internal implementation.

### Model and problem

| ID | Status | Requirement | Acceptance criterion |
|---|---|---|---|
| MOD-01 | C | Separate physical dynamics, observations, problem constraints and algorithm configuration | Reuse the same model with different admissible sets/objectives/backends |
| MOD-02 | C | Affine LTV model x_(t+1)=A_t x_t+B_t u_t+E_t w_t+a_t | Shape/time validation; LTI constant coefficients do not require T copied matrices |
| MOD-03 | C | Separate observation maps, errors, feedthrough and timing | Full/partial/no observation are distinguishable; pre-decision data cannot depend on an unavailable current action |
| MOD-04 | C | Natural absent-input and unrestricted special cases | Zero-dimensional ports, singleton/universal/empty sets retain distinct semantics; no absent observation grants full-state knowledge |
| MOD-05 | C | Solver assumptions do not narrow general model representation | Singular A is representable; inverse-based solver explicitly rejects it when required |
| MOD-06 | C/R | Continuous first, finite/mixed later; hybrid modes separate | Domain identities survive serialization; convexifying finite choices is an explicit relaxation |
| MOD-07 | C/R | Optional linear temporal constraints; absent initially | Empty collection accepted; unsupported coupled request diagnosed; first archival manifests acquire no extra rate limits |
| MOD-08 | P | Known initial point and nominal open-loop information for first slice | Validator rejects unsupported uncertainty/policy semantics rather than assuming an existential or robust quantifier |
| MOD-09 | C | First scenario input is a discrete-time model | Use supplied transition matrices directly; continuous-time coefficients are not silently interpreted as discrete transitions or discretized |

### Objectives and solution families

| ID | Status | Requirement | Acceptance criterion |
|---|---|---|---|
| OPT-01 | C | Linear, convex quadratic and weighted Euclidean residual terminal forms | Rectangular residual maps supported; dimensions and convexity requirements checked |
| OPT-02 | C | Preserve original objective convention and weights | Norm-square reformulation has identical minimizers, while reported cost uses original norm; transformation recorded |
| SOL-01 | C | Represent all optimal controls and consistent trajectories | Joint family or equivalent parametrization preserves cross-stage dependencies; selected samples alone fail this criterion |
| SOL-02 | C | Preserve every supported terminal minimizer | Constant/nonunique terminal objectives do not collapse the family to one chosen terminal point |
| SOL-03 | C | Distinguish infeasible, unbounded, unattained infimum and unsupported | Status/evidence show why an optimal family is absent; no-found-candidate is not an infeasibility proof |
| SOL-04 | C | Obtain different complete witnesses first | Return controls plus states, selection settings, requested/distinct counts and duplicate diagnostics |
| SOL-05 | C | Secondary witness selection retains the primary family | Different selected trajectories have the same primary optimum within declared evidence; selection does not redefine the objective |
| SOL-06 | R | Membership, projection, user-facing secondary optimization, finite enumeration and near-optimal requests later | Each future query has an explicit capability/termination/evidence contract |

Let F denote the feasible joint state/control relation and let v* be an attained finite minimum of phi(x_T). The requested family is Z*={z in F : phi(x_T)=v*}. A set-based strategy must preserve the preimage of the entire terminal minimizer set. A direct optimizer must perform additional family construction beyond producing one minimizer. Initial numerical implementations report the evidence they actually establish; mathematical completeness is not inferred from a solver flag.

### Replaceable algorithms and geometry

| ID | Status | Requirement | Acceptance criterion |
|---|---|---|---|
| ALG-01 | C | Independent LP and convex-programming backend ports | Switch compatible adapters without changing model, objective or frontend data contracts |
| ALG-02 | C | Separate hull/membership/recovery algorithms from LP implementation | Specialized phase-I basis diagnostics are optional capabilities; generic feasibility adapter remains usable with compatible algorithms |
| ALG-03 | C | Independent set representations, operations, conversion and approximation | A new representation registers compatible operators; planners do not gain representation-specific switches everywhere |
| ALG-04 | C | Explicit inner/outer/equivalent/heuristic relation | Unsupported requested guarantee rejected; no silent approximation downgrade |
| ALG-05 | C | Whole-pipeline capability validation | Check domains, objective, inverse/compactness assumptions, arithmetic, output scope and evidence before expensive execution |
| ALG-06 | C/R | Extensible geometry catalog, including owner-mentioned zonotopes and ellipsoidal methods | Include catalog/assumptions now; implement selected backends in later scoped slices, with claim-specific tests |
| ALG-07 | P | Coarse runtime ports, kernel-local templates, compatible in-process registration | Backend replacement stays in-process; no per-scalar virtual dispatch requirement or cross-toolchain C++ ABI promise |

The catalog includes H/V polyhedra, boxes/parallelotopes, zonotopes, constrained zonotopes, ellipsoids/families, lazy support/expression forms, unions/hybrid zonotopes, polynomial forms and ellipsotopes. These are not interchangeable under every operation. The [representation review](../../architecture/set-representations-and-ellipsoidal-toolbox.md) includes Ellipsoidal Toolbox as an external comparison/inspiration; its MATLAB API is not the native contract.

### Evidence, execution and experiments

| ID | Status | Requirement | Acceptance criterion |
|---|---|---|---|
| EVD-01 | C | Independent trajectory verifier and explicit numerical tolerances | Recompute initial/dynamics/constraint residuals and original objective from immutable problem data |
| EVD-02 | C | Separate feasibility, optimality, set inclusion and family completeness evidence | Feasible witness cannot silently certify optimality/completeness; exact symbolic construction does not imply validated rounding |
| EVD-03 | C/R | Numerical first, future validated/certificate verification | Unsupported validated request reported; certificate claims bind to problem, assumptions and verifier |
| RUN-01 | C | C++ core with efficient parallelizable architecture | [Language ADR](../../architecture/decisions/0001-cpp20-core.md) and independent native backend targets; Python references do not own product algorithms |
| RUN-02 | P | Immutable shared inputs and exclusive mutable workspaces | Concurrent workers have isolated solver/warm-start/query state; views retain documented lifetimes |
| RUN-03 | C/P | Shared resource policy, cancellation and partial evidence | Outer/backend threads share budget; cancellation reports incumbent/bounds where available; enforcement limitations recorded |
| RUN-04 | C | Scalability claims must be measured for declared outputs | Record dimensions, representation size, memory, backend versions and output scope; changing language alone does not claim removal of exponential complexity |
| EXP-01 | C | Compare methods visually, numerically and by time | Common scenario/objective/query/tolerance; controls/states, residuals, family evidence and separated setup/solve/query/verification timing |
| EXP-06 | C | First comparison presents final results, controls and trajectories | Include objective/residual/family evidence, detailed module timing tables and final plots; intermediate-computation viewers are not required |
| EXP-07 | C | Detailed submodule comparison tables | Record module/backend/operator identities, call counts, sizes, iterations when available and nested/parallel timing; preserve raw repetitions and separate overlapping work from latency |
| EXP-08 | C | Final scientific plots and selectable 2D fuel projections | Export controls/states and requested coordinate pairs with units; mathematical set projections require an explicit compatible query and retain exact/inner/outer/sample labels |
| OBS-01 | C | Observe independent algorithm and representation substitutions | Record selected module identities, conversions, required/returned guarantees and rejected capabilities without coupling mathematical ports to a viewer |
| OBS-02 | C | Measure execution and instrumentation honestly | Separate inclusive/exclusive wall/work/CPU scope, unavailable metrics, setup/family/query/verification/replay/export costs and collection overhead |
| EXP-05 | C | First compare reachability/backward recovery with direct joint-trajectory optimization | Both strategies run the shared analytic acceptance cases with the same optimum and consistent complete-family semantics; approximation comparison is later |
| EXP-02 | C | Published experiments and figures/tables anchor baselines | Keep reported values separate from independently reproduced results and source variants |
| EXP-03 | C | B04 first archival target; unresolved inputs remain explicit | Historical non-executable manifest cannot be silently promoted by guessed bounds or fitted matrices |
| EXP-04 | C/P | Reproducible versioned artifacts | Scenario hashes, seeds, selection settings, module versions, resources and raw comparison data recorded |
| REV-01 | C | English documentation and public scientific review | Trace assumptions/results to source IDs and review issues; preserve original hashes and avoid publishing unapproved raw archive content |
| REV-02 | C | Separate module-test expansion tickets | Every implementation ships minimum acceptance tests; separate tickets add independently designed unit/contract suites for module seams and mathematical edge cases |
| REV-03 | C | Separate rigorous code-review tickets | Review fixed implemented commits for standards, specification, mathematical assumptions, modular replacement, ownership and measured scalability; blocking findings need fixes and independent recheck |

## Architecture and C++ boundary rules

Use composition across model, problem, sets/geometry, optimization, reachability, synthesis, witnesses/verification, execution and experiment artifacts. Fuel physics and independent nonlinear plants are domain adapters. Plots/CLI/optional UI consume artifacts without duplicating algorithms.

Problem data and immutable set payloads can be shared. Workspaces, caches with mutable state and warm starts belong to a solve/worker and cannot be concurrently borrowed without an explicit synchronization contract. Buffer views declare scalar/storage/stride/lifetime. Initially proposed double arithmetic is not validated arithmetic. Registry IDs remain extensible; closed small objective alternatives may use std::variant.

The first comparison presents final optimal-family results, selected controls/trajectories, independent verification, detailed module timing tables and standalone scientific figures with selectable 2D fuel-coordinate views. The later owner request extends the previous summary-only presentation. Intermediate reachable-set viewers and generated-program dumps remain optional. Operation counters and nested spans record substitutions, sizes and work without requiring every intermediate set or solver iterate to be retained. Explicit mathematical projection queries have separate capability, evidence and cost records.

Public ports return common statuses and evidence while retaining raw backend diagnostics. Backend library containers stay behind adapters. Expected capability/math/numerical failures are represented in results; allocation/programming error policy will be settled in the implementation plan. A future C ABI is distinct from selecting registered native modules at runtime.

The [native contract document](2026-10-11-cpp-core-contracts-design.md) specifies illustrative types, ownership, result/family semantics and an intended user flow. Its code fences remain design sketches. CORE-01 supplies the subordinate [compiled interface revision 1](../../contracts/core-interfaces.md) and [dependency decision/probes](../../architecture/decisions/0002-native-integrations.md), pending integration review; numerical adapters and synthesis remain downstream work.

## Scenario-file workflow

Owner decision: users choose among supplied scenario files or create their own from templates. The project supplies the templates, documentation and validation; users supply custom problem data. Basic supported tasks must not require writing or compiling C++.

| ID | Status | Requirement | Acceptance criterion |
|---|---|---|---|
| INP-01 | C | Scenario files are the primary experiment input | Select an existing file or copy/edit a documented template and run the supported task without product-code changes |
| INP-02 | C | Provide simple templates and an extensible authored form | Minimal supported case is short; optional features do not impose empty disturbance/observation/advanced sections |
| INP-03 | P | Separate mathematical scenario from run configuration, within one file if convenient | Changing strategy does not change mathematical problem identity; resolved run settings are recorded independently |
| INP-04 | P | Validate authored input before expensive work | Syntax/shape/schema errors identify the field and expected value; unsupported capabilities are reported separately; unknown fields cannot silently disappear |
| INP-05 | P | Document, version and record resolved defaults | Optional omissions have explicit stable meanings; a run stores the resolved problem/settings and external-data hashes where used |

Proposed user flow: choose a file -> validate it -> resolve the requested/default comparison configuration -> run the two selected strategies -> obtain final families, controls/trajectories, verification, detailed module performance and final figures. A thin CLI is the proposed first launcher; the input schema must also be usable by later interfaces and the native library.

A scenario describes dynamics, initial information, horizon, admissible sets and the primary criterion. Optional run settings describe methods, witness selection, numerical tolerances and resources. A simple file can contain both without requiring the user to manage multiple files. The default comparison profile is proposed to select the two agreed strategies; advanced backend selection remains optional. Requested capabilities must still be checked.

Provide a small template catalog with explanations of dimensions, stage indexing, units and objective conventions: a minimal LTI case, a state-constrained case, and an LTV case, covering the three initial objective forms. Start every published executable template from complete, verified data. Keep the unresolved historical B04 record labelled non-executable; it is not a ready-to-run user template.

Constant coefficients and bounds should be entered once. Stage-varying values have an explicit separate form. Small matrices can be inline; optional external matrix data can be added under a documented reference/layout contract when needed. Common domain shapes should have concise named forms such as a box, with general polyhedral data available as an advanced form. Defaults must not invent control bounds, targets, uncertainty semantics or full-state observation. If a nominal profile omits external inputs, observations or state restrictions, its resolved meaning is documented and recorded.

Confirmed time-domain scope: the file supplies discrete transitions x_(t+1)=A_t x_t+B_t u_t+a_t for the initial nominal problem. The horizon is T transitions. Optional physical timestamps describe those stages; they do not trigger matrix discretization. Continuous-time input and its integration/hold semantics belong to a later explicit module. Continuous-valued controls remain the selected initial action domain.

File syntax (for example YAML versus JSON) and the concrete schema are still proposals. The [scenario-file design sketch](2026-10-11-scenario-files-design.md) illustrates the intended authoring experience; it is not a parser or an accepted schema. Existing archival JSON manifests do not automatically define the future user-facing format.

## Test specification

Module unit tests are a required deliverable. Use mathematical answers, invariants and independent checks, not tests that merely repeat implementation formulas. Each implementation ticket declares relevant test IDs and adds meaningful cases for its own supported capabilities. A common adapter contract suite can be reused by every compatible backend.

| Test ID | Level | Behavior/oracle | Requirements |
|---|---|---|---|
| T-M01 | Unit | Reject wrong dimensions/stage counts; constant and stagewise providers produce the same model behavior | MOD-01/02 |
| T-M02 | Unit | No external/control port, singleton/universal/empty sets and full/partial/no observations retain their semantics | MOD-03/04 |
| T-M03 | Contract | Singular dynamics accepted by model; inverse-only strategy rejects; unsupported temporal/domain/information/continuous-time request distinguished from infeasible | MOD-05/06/07/08/09, ALG-05 |
| T-O01 | Unit + analytic | Evaluate all three objective conventions; rectangular L; valid/invalid quadratic properties under documented validation policy | OPT-01 |
| T-O02 | Mathematical | Norm versus norm-square has the same minimizers and different correctly reported costs; no unreviewed sum-of-terms reformulation | OPT-02 |
| T-G01 | Unit + analytic | Hand-derived affine image, sum, intersection, support and preimage cases, including lower-dimensional/empty inputs where supported | ALG-03/05 |
| T-G02 | Contract | Equivalent conversion preserves answers on supported analytic cases; approximation direction/evidence and unsupported operations remain explicit | ALG-03/04 |
| T-L01 | Adapter contract | Small analytically solved LPs: finite optimum, infeasible and unbounded; translated evidence and residuals match actual backend support | ALG-01, SOL-03 |
| T-L02 | Unit/contract | Barycentric membership/recovery with feasible, boundary and outside points; optional basis diagnostics unavailable case | ALG-02 |
| T-C01 | Adapter contract | Convex analytic programs including zero norm residual/nondifferentiability and semidefinite nonunique minima where supported | OPT-01, ALG-01 |
| T-S01 | Mathematical integration | Two-step integrator: x_0=0, u_k in [0,1], phi=(x_2-1)^2; v*=0, family u_0+u_1=1; recover (0,1),(1,0), reject (1,1) as optimal | SOL-01/04/05 |
| T-S02 | Mathematical integration | Constant objective over bounded feasible relation: every feasible trajectory belongs to the family; preserve multiple terminal points | SOL-01/02 |
| T-S03 | Mathematical integration | Distinguish unique terminal minimizer from multiple optimal control histories; selecting one witness is not a uniqueness/completeness proof | SOL-01/02/04 |
| T-V01 | Unit/integration | Inject wrong state transition, violating control and wrong objective into witnesses; independent verifier detects each with named residual/tolerance | EVD-01 |
| T-V02 | Contract | Incomplete/sample/relaxed family and backend success do not become complete/validated evidence; evidence problem ID mismatch rejected | EVD-02/03 |
| T-R01 | Integration | Parallel independent runs use separate workspaces; compare mathematical results with sequential runs under explicit tolerance | RUN-02/03 |
| T-R02 | Integration | Cancel at a supported boundary and exhaust a documented resource limit; preserve actual partial evidence without changing outcome claims | RUN-03, EVD-02 |
| T-X01 | Integration + mathematical | Run both selected synthesis strategies on T-S01/02/03; check known optimal relations, objective and independently verified witnesses. Witness coordinates may differ. Backend/representation replacement has additional contract cases when implemented | ALG-01/03/07, SOL-01/02, EXP-01/05 |
| T-X02 | Artifact integration | Round-trip supported final scenario/result metadata; collect setup/family/query/check times and selector/resource provenance without requiring intermediate-set/program dumps | EXP-01/04/06 |
| T-I01 | Input integration | Every executable template loads, validates and runs its supported task without C++ edits; the unresolved B04 record retains its restoration diagnostics | INP-01/02, EXP-03 |
| T-I02 | Unit/contract | Malformed dimensions, invalid stage counts, unknown fields and unsupported schema/capabilities produce actionable distinct diagnostics | INP-04/05, ALG-05 |
| T-I03 | Artifact integration | Strategy change preserves scenario identity; omitted documented defaults resolve reproducibly and are saved; changing problem data changes identity | INP-03/05, EXP-04 |
| T-B04 | Archival regression | Current historical manifest gives restoration diagnostics; later canonical reproduction compares sourced inputs, trajectories and original cost with explicit tolerances | EXP-02/03 |

At the first-slice boundary, every implemented capability has applicable unit/contract tests, T-S01/02/03 and T-V01/02 establish end-to-end semantics, T-X01 verifies the mandatory two-strategy comparison, T-I01/02/03 cover the primary scenario-file workflow, and integration/resource tests cover advertised execution behavior. Tests for later representations or certificate verifiers are added when those capabilities are implemented. Unsupported capabilities are tested as diagnostics now.

Property tests may add random low-dimensional examples with fixed reproducible seeds; compare to independent analytic/exhaustive reference cases where possible. Sanitizer/race-check tooling should cover native ownership/concurrency when supported by the selected compiler platform. The test framework and CI matrix remain planning choices. Performance studies report measurements rather than fragile wall-clock unit-test thresholds.

Archived runtime values are context, not cross-hardware pass/fail limits. B04 matching is gated by canonical restoration, not by ordinary module tests. No product unit tests are currently implemented in this documentation-only repository state.

## Scientific prerequisites and baseline restoration

The [scientific foundations](../../research/scientific-foundations.md), [source map](../../research/source-map.md), [glossary](../../research/glossary.md), [recent research](../../research/recent-research.md) and [representation study](../../architecture/set-representations-and-ellipsoidal-toolbox.md) supply scientific definitions and reading depth. They should be linked from algorithm tickets rather than copied without assumptions.

The [B04 table transcription](../../research/b04-tables.md) is available, including reported nonlinear outcomes for different controls. Canonical matching of model, initial state, controls and reported terminal optimizer remains a separate [restoration issue](https://github.com/butahlecoq/controlled-systems-lab/issues/10). This narrow matching question does not negate the reviewed papers or block architecture/unit-test implementation. Do not tune matrices to force reported outputs. Nonlinear simulation quality is distinct from linear-model optimality and nonlinear global optimality.

The [temporal-coupling note](../../research/temporal-coupling.md) proves a specific exact slew-constraint lift under stated assumptions; it does not certify every historical algorithm or every temporal coupling. Minimax maximum-of-convex objectives need a global worst-case argument, not a generic convex minimizer with negated cost.

## From specification to tickets and subagents

The owner authorized decomposition and GitHub publication. The [implementation backlog](../plans/2026-10-11-controlled-systems-backlog.md) and [machine-readable ticket manifest](../plans/backlog.json) now define the dependency order, acceptance checklists and proposed ownership. Product implementation is a subsequent step:

1. Review this consolidated specification and native contracts; reconcile requirement status and settle the first supported completeness cases.
2. Select native numerical/test/build integrations, freeze the first interface revision, and write the scoped implementation plan.
3. Create tickets with requirement/test IDs and explicit dependencies. Keep archival restoration independently tracked.
4. Implement dependency-ready tickets with subagents in isolated branches/worktrees. Integrate common contracts before downstream work depends on them.
5. Run unit/adapter/integration evidence, review scientific assumptions and changes, then merge coherent slices and compare methods.

Each implementation ticket contains: goal; linked requirement IDs; assumptions/source references; inputs/output contract; included/excluded capabilities; acceptance/test IDs; dependencies; ownership of files/modules; result/evidence expectations; and review/merge criteria. Avoid tickets such as "implement solver" without an output guarantee and independent test oracle.

Suggested responsibility groups are shared model/problem/data contracts, set/geometry adapters, optimization adapters, synthesis/family construction, witness/verification, execution/artifacts, and archival reproduction. Multiple ready adapter/test tickets can run in parallel after common interfaces are fixed. Shared-header redesign, registry/result-schema changes and a strategy's upstream prerequisites are sequential dependencies. One integrator owns cross-module consistency and complete end-to-end checks; scientific review remains distinct from a coding-agent review.

Subagents may propose contract changes but cannot silently alter accepted requirements to make their own ticket pass. They should return changed files/commits, tests run, assumptions and unresolved evidence limitations. Task completion means the stated acceptance evidence is present, not merely that code compiles. Owner/scientist feedback becomes explicit specification revisions and follow-up tickets.

## Change record

- Version 0.1: consolidated conversation decisions, native design references, requirement/test IDs and subagent delivery boundaries.
- Version 0.2: owner selected the initial two-optimization-strategy comparison and deferred reachable-set approximations; EXP-05 and T-X01 record its acceptance obligations.

- Version 0.3: owner selected final results and trajectories as sufficient for the initial comparison; EXP-06 defers intermediate-computation inspection while preserving final evidence and performance summaries.
- Version 0.4: owner selected scenario-file input and user-authored scenarios based on supplied simple templates; input requirements, glossary distinctions and validation tests added.
- Version 0.5: owner confirmed discrete models for the first version; MOD-09 reserves continuous-time input/discretization for a later module.
- Version 0.6: owner authorized concrete tickets, separate test expansions and rigorous code reviews; detailed module observability/timing and final 2D fuel figures extend EXP-06. Archive-backed optimizer variants, new recursive/warm-start strategies and later representations receive separate capability tickets.

## Open decisions for the next review

- Accept the proposed first polyhedral nominal slice and its supported complete-family construction; distinguish mathematical exactness from numerical evidence.
- Select the first matrix, LP, convex solver, CMake packaging and test integrations without exposing their internal types in the public contract.
- Review the scenario-file form, syntax and proposed CLI launcher; select supported compiler/OS distribution targets. No real-time deadline is currently specified.
- Choose compatible backends/representations for the two selected optimization strategies and realistic scale ranges using the supplied experiments. Reachable-set approximation comparison is a later slice.
- Restore B04 canonical inputs separately; the provisional control interval stays labelled provisional until sourced or explicitly adopted as a new scenario.

Changes to these open proposals do not reopen the confirmed C++ choice or silently change archival data. Stable requirement IDs and a dated change record should keep subsequent tickets/reviews traceable.
