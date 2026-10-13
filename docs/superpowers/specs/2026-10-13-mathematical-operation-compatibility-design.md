# Mathematical Operation Substitution and Guarantee Composition

> Status: draft for owner and scientific review. This document proposes an architecture contract for the first supported profile; it does not approve numerical thresholds, claim a complete-family verifier, or assert universal module interchangeability.

**Related issues:** [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8), [#40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [#43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [#155](https://github.com/butahlecoq/controlled-systems-lab/issues/155), [#157](https://github.com/butahlecoq/controlled-systems-lab/issues/157).

## 1. Purpose

The architecture already names replaceable modules for set representations and operations, conversions, approximations, LP and convex backends, family construction, and witness queries. It also defines typed requests, evidence, and operation identities. What remains unclear is how a caller can determine before execution whether a specific adapter satisfies a strategy's needs, and how a mathematical guarantee survives a composed route through multiple adapters.

This proposal makes substitution testable for the first agreed workflow. It builds on the current C++20 contracts and adds no implementation dependency. The public operation model remains a small runtime seam; specialized numerical kernels remain internal to adapters.

## 2. Scope and established decisions

The first profile remains nominal discrete-time optimal control with continuous actions. It compares forward/backward reachability with recovery against direct joint-trajectory optimization and requests the dependency-preserving optimal state/control relation, with individual witness queries. The two-step scalar integrator remains the analytic dependence oracle.

The design retains the established distinctions between:

- the mathematical outcome and execution termination;
- a complete optimal relation, a proven optimal subset, and a candidate relation;
- equivalent, inner, outer, and heuristic set relations;
- numerical evidence and validated evidence;
- capability rejection before execution and an operation failure after execution has retained evidence.

Finite and hybrid actions, temporal constraints in the initial experiments, robust/adaptive strategies, continuous-time models, new approximation families, distributed network services, and validated arithmetic are outside this slice.

## 3. Contract model

Every replaceable mathematical operation has an interface that states more than its C++ type. Its contract includes:

1. **Input and output meanings:** operation identity, ordered operand identities, coordinate and representation requirements, mathematical preconditions, and the set or proposition represented by the output.
2. **Capability conditions:** supported operation, representations, dimensions or structural restrictions, scalar/arithmetic profile, requested assurance and guarantee direction, and any required backend features.
3. **Guarantee:** the relation of the produced result to the operation's ideal mathematical result, its assumptions, and the rule that justifies that relation.
4. **Execution behavior:** whether capability admission is side-effect free, the typed outcome for unsupported requests, resource/cancellation behavior, and which independently supported evidence is retained after a late stop or rejection.
5. **Identity and provenance:** stable module ID/version, request ID, ordered inputs, output identity, and the operation's place in the execution lineage.

The current `OperationRequest`, `GeometryEvidence`, `ConversionRequest`, and `ApproximationRequest` already carry much of this information. The proposal is to complete and test their shared semantics, not to add a second registry or generic orchestration framework.

### 3.1 Capability admission

Before workspace creation, the strategy admits the immutable resolved problem, effective request, and statically knowable route requirements. Admission returns either a compatible prepared route or typed `Unsupported` diagnostics. It identifies the missing operation, representation, assurance, or precondition. It does not silently select a different adapter, add a relaxation, or alter the requested output scope.

Some operation requests are generated only after earlier results are available. Each generated request is admitted against the selected provider before that operation executes. Such a late rejection is distinct from pre-solve route rejection: the strategy returns a result with the typed rejection, actual request provenance, completed operation lineage, and retained-evidence scope. It must not relabel the rejection as infeasibility, numerical failure, or pre-solve `Unsupported`.

A capability is a bounded statement. “Supports polyhedra” is insufficient; it identifies the operation and relevant representation/structural class. Capability declarations do not prove a result correct; they state where an implementation claims to satisfy its operation contract.

### 3.2 Guarantee and evidence are independent axes

Each set-valued operation describes both its **mathematical relation** and its **evidence support**. The existing `SetRelation` vocabulary (`equivalent`, `inner`, `outer`, `heuristic`) expresses the asserted relation; `GeometryEvidence.support` expresses support for that assertion. There is no fifth `unestablished` relation. When composition cannot justify an inclusion direction, the route reports `heuristic` with `Unestablished` support; it never invents an `inner`, `outer`, or `equivalent` relation:

| Relation | Meaning relative to the ideal result | Permitted interpretation |
|---|---|---|
| `equivalent` | The represented output equals the ideal result under declared semantics | Exact operation result only to the strength of its evidence |
| `inner` | The represented output is a subset of the ideal result | Candidate members may be feasible if membership is supported; it does not establish full coverage |
| `outer` | The ideal result is a subset of the represented output | May support a bound or enclosure; membership in the output does not imply feasibility |
| `heuristic` | No inclusion relation is established | Exploratory result only |

The relation does not imply the evidence level. For example, a binary64 computation labelled `equivalent` is not validated arithmetic. Evidence separately states whether support is unestablished, numerical, symbolic under assumptions, or validated by an executed verifier.

For a common minimization objective `f`, proved inclusions `S_in ⊆ S ⊆ S_out` imply the extended-real inequality `inf_{S_out} f <= inf_S f <= inf_{S_in} f`. A finite usable upper bound additionally requires a nonempty `S_in` and a finite objective value there; a finite lower bound requires the objective to be bounded below on `S_out`. Writing `min` instead of `inf` also requires attainment on the corresponding set. These statements require supported inclusions, the same objective, and the stated domain conditions. They do not convert a reachable-set approximation into an optimizer-family approximation, and they do not produce a control witness unless a consistent history is retained or recovered.

## 4. Composition rules

A composed route carries an ordered operation lineage. Each step binds its request, inputs, output, implementation ID/version, assumptions, asserted `SetRelation`, and evidence support. The final relation and support are derived from the steps; they are never caller-selected labels.

Composition is operation-specific:

- An adapter declares whether its mathematical operator is monotone or antitone in each set-valued input under the declared semantics.
- Its guarantee rule maps the input inclusion directions to an output inclusion direction.
- The route composes those rules in order. If a step lacks a justified propagation rule or has unsupported assumptions, the derived relation is `heuristic` and its support is `Unestablished`. If support is insufficient for the requested assurance, the relation claim remains distinct from that assurance failure.
- Equivalent transformations preserve the relation only under their explicit preconditions and supported evidence.
- Heuristic steps cannot be promoted by a later exact step.
- Conversion and approximation remain distinct operations. A conversion claims equivalence; an approximator claims an explicit inner or outer direction. A size budget or low residual alone does not justify either relation.

There is no universal rule that an inner input always yields an inner output or that two approximate steps can be combined by simply taking the weaker label. For example, affine image is monotone in its set operand, while a containment query and an affine preimage have different output semantics. Each operation adapter must bind the applicable rule and tests. Until that rule is available, the pipeline cannot claim propagated completeness or optimality.

The minimum direction-composition fixture is the affine map `T(x)=2x+1`, exact interval `S=[0,2]`, and supported inner interval `S_in=[0,1]`. The independent oracle expects `T(S)=[1,5]` and `T(S_in)=[1,3]`; therefore the transformed subset remains `inner`. The test checks both literal endpoints and the inclusion direction, and it requires the output evidence to retain the input support and operation identity.

## 5. First-profile module chain

The following matrix is a capability checklist, not a claim that every operation is implemented or required by both strategies.

| Seam | Contract presented to its caller | Substitution check |
|---|---|---|
| `SetRepresentation` | Owns set meaning, coordinate schema, boundedness/emptiness facts, and supported query/operation capabilities | Same analytic set supplied in two admitted representations decodes to the same tested membership/support facts |
| `SetOperator` | Applies one operation to ordered operands and returns output plus request-bound relation/evidence | Literal analytic oracle checks for affine image, Minkowski sum, intersection, projection, preimage, support, or containment, as each strategy requires |
| `RepresentationConverter` | Converts between named representations with an equivalence claim under explicit preconditions | Round-trip or independent membership/support oracle; unsupported degeneracy is explicit |
| `SetApproximator` | Produces a requested inner or outer relation with budget, assumptions, and evidence | Independent inclusion witnesses/oracles in the declared direction; no conversion-style equivalence claim |
| `LPBackend` / `ConvexBackend` | Solves a canonical program with declared problem classes, objective type, statuses, numerical policy and optional diagnostics | Backend contract suite checks literal objectives, feasible points, residuals, bounds, multiple minimizers, and typed statuses against independent analytic oracles |
| `OptimalFamilyBuilder` | Constructs the requested dependency-preserving relation and separates complete, partial, and candidate output | Caller-visible family oracle verifies the full joint relation and its evidence; samples or marginals cannot satisfy a complete-family request |
| `SolutionFamily` query | Returns selected witnesses or relation queries bound to an immutable source family | Every result retains the source-family identity and cannot upgrade its target or assurance |
| `SynthesisStrategy` | Admits and composes a route, preserving the effective request and ordered lineage | Run both strategies on the same scenario/request; compare only when output scope and evidence are aligned |

The first-profile routes require the following minimum semantic capabilities. These requirements do not select a representation or claim that a backend currently provides them.

| Route | Required operation capabilities | Required result behavior |
|---|---|---|
| Reachability with backward recovery | Affine images of state/control sets; Minkowski sum for state/control contributions; intersection with each declared state-admissibility set; terminal objective optimization over the resulting reachable terminal set; nominal existential predecessor compiled as a joint state/control relation and projection onto predecessor states; joint-history recovery/query | Retain cross-stage dependencies, bind each projection and other set operation/conversion to its inputs/outputs, and return a candidate/partial relation with honest direction/evidence if complete coverage is unavailable |
| Direct joint-trajectory optimization | Translate the admitted affine discrete-time model, initial/state/control constraints, and selected objective into one canonical joint-state/control program; invoke an LP or convex backend only when its declared problem/objective class admits that program; retain an optimizer relation or face description when supported | Bind program-to-original-problem translation and objective bounds; an optimizer witness alone yields at most a candidate, never the complete family |
| Shared strategy/query path | Admit the effective `FamilyRequest`; validate original-model witnesses; preserve ordered operation lineage; answer queries against the immutable source-family identity | Return pre-solve `Unsupported` for inadmissible routes; preserve accepted evidence and precise lineage on later rejection; do not upgrade family target or assurance |

For every row, representation-specific preconditions and guarantee-propagation rules remain part of each concrete adapter's contract. The predecessor requirement uses the typed existential construction in the current predecessor contract: compile the joint relation over `[x,u]`, then request a `Projection` over state coordinates. It does not require a separate `AffinePreimage` adapter. A route is not admitted merely because a registry contains an adapter with a matching operation name.

### 5.1 Analytic dependence oracle

For `x₀ = 0`, `xₖ₊₁ = xₖ + uₖ`, `0 <= u₀,u₁ <= 1`, and terminal cost `(x₂ - 1)²`, the complete optimal histories satisfy
`x₁ = u₀`, `x₂ = 1`, and `u₀ + u₁ = 1`.

The family is a joint segment. Its control marginals are both `[0,1]`; their Cartesian product incorrectly admits `(0,0)` and `(1,1)`. This fixture checks that a substitute family builder and query adapter preserve temporal dependence, terminal ties, identity, and requested scope.

### 5.2 Fail-closed complete-family publication

A complete family requires a checked coverage argument bound to the resolved problem, effective request, joint-coordinate schema, strategy identity, and actual ordered operation lineage. A witness residual, backend “optimal” status, agreement of two solvers, symbolic text, or unchecked certificate reference does not establish coverage.

Until a verifier contract and procedure are scientifically reviewed and implemented, the shared `StrategyPort` interface continues to reject complete-family publication. The first-profile contract tests must verify this rejection and retention of other supported evidence. This document does not set an arithmetic mode, tolerance, or acceptance threshold.

This focused contract slice does not satisfy issue #8's central acceptance requirement for a complete optimal state/control family with explicit coverage and optimality evidence. `StrategyPort` deliberately continues to reject complete-family publication until that verifier contract and procedure have been reviewed and implemented. Follow-on work remains tracked in SYN-07 #155 for the shared boundary and evidence contract, SYN-06 #43 for independent verification, and TEST-24 #157 for caller-visible strategy tests and mathematical oracles. This PR therefore cannot close issue #8.

## 6. Test and review requirements

Tests exercise the public seam used by the strategy, not private workspace counters or solver internals. Each operation contract has:

- one analytic positive case with a literal expected mathematical result;
- one precondition/capability rejection with a caller-visible diagnostic;
- one malformed identity/provenance or insufficient-evidence case;
- one guarantee-direction case where applicable;
- a separate verifier test before any validated claim is accepted.

The shared strategy suite then checks pre-solve admission, late generated-operation rejection with retained evidence, family identity and lineage, and no mutation or publication of a previously accepted immutable result. TEST-24 #157 owns expanded caller-visible coverage; SYN-07 #155 owns result and family validation. Per-module suites remain in the existing backend/geometry/test tickets.

Comparisons between substitute routes use the same immutable problem and effective `FamilyRequest`. They compare the relation represented, feasible histories, original objective and evidence scope, not an exact byte-for-byte output or a particular witness coordinate unless the algorithm contract requires that exact output.

## 7. Decisions intentionally left open

This draft does not decide:

- which numerical or validated coverage verifier will establish a complete optimal family;
- numerical acceptance thresholds, arithmetic policy, or tolerance semantics for family coverage;
- which general polyhedral operation backend to select beyond the currently bounded H/V conversion;
- whether a given approximation route is admissible for either first-profile strategy;
- hard process-wide enforcement of native thread and memory budgets;
- a universal capability schema covering future nonlinear, robust, finite-action, hybrid, or distributed profiles.

Those decisions remain in their named issue/review tracks. A future implementation plan may cover only decisions approved here and must preserve fail-closed behavior for the rest.

## 8. Acceptance criteria for this architecture slice

- A reviewer can state, before execution, which operation and assurance capabilities a selected first-profile route requires and why an adapter is admitted or rejected.
- A reviewer can trace the relation direction and evidence support from each operation through a composed route without relying on implementation-specific behavior.
- Capability rejection and late operation rejection have distinct caller-visible outcomes and preserve the agreed evidence/provenance semantics.
- The route matrix enumerates the minimum semantic capabilities for both selected strategies and their shared family/query path.
- A literal affine-image fixture verifies that a proved inner input remains an inner output under the declared affine-image contract.
- The two-step integrator exposes the joint-family dependence error that stagewise marginals conceal.
- The spec leaves unreviewed coverage thresholds and unsupported general operation classes explicitly open; it grants no complete-family publication.
