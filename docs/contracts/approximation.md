# Approximation policy and evidence (APP-01 incremental contract)

`CSL::approximation` exposes `geometry::approximation::run_registered` through
`<csl/geometry/approximation.hpp>`. It selects the existing, separate
`ApproximationPort` by method ID/version, checks the requested output
representation and relation against the provider's offer, runs the frozen
request, then audits the returned result. Equivalent representation changes use
`ConversionPort`; an equivalent request to this policy is rejected.

## Result admission

The request identifies the problem, complete request, ideal reference set,
input set, output representation, direction, primitive budget and assurance.
The result must retain the requested relation, ambient dimension and output
representation, and its evidence must bind the full request identity and input
ID. A heuristic result is a distinct `HeuristicApproximation` and carries no
inclusion proof. An inner or outer result is an `EnclosedApproximation` only
when one of these independent structural checks succeeds:

| Basis | Checked relation |
| --- | --- |
| Same immutable set handle and matching envelope | Output equals reference |
| Native empty output, same ordered native coordinates | Output is inside reference |
| Native universal output, same ordered native coordinates | Reference is inside output |
| Native H output and reference, same ordered native coordinates; every reference inequality and equality row occurs unchanged in the output | Output is inside reference (inner) |
| Native H output and reference, same ordered native coordinates; every output inequality and equality row occurs unchanged in the reference | Reference is inside output (outer) |
| Native singleton output and native H reference, same ordered native coordinates; the point satisfies every H row under exact stored binary64 arithmetic | Singleton is inside reference (inner) |
| Native singleton reference and native H output, same ordered native coordinates; the point satisfies every H row under exact stored binary64 arithmetic | Reference is inside output (outer) |
| Native generator source and unconstrained native generator output, same center and ordered coordinates; retained factor IDs have identical columns and independent new axis columns cover each omitted row's exact stored-binary64 absolute sum | Reference is inside output (outer) |
| Native bounded planar V source and native directional ellipsoid output, same ordered coordinates; every vertex projection is within its exact stored-binary64 bound and each radius satisfies `r_i² ≥ 2m_i²` | Reference is inside output (outer) |

Native V data with zero vertex rows is empty under the set contract, including
when ray rows exist. This policy does not infer nontrivial containment from a
provider's `SymbolicArgument`, `NumericalCheck`, certificate reference or
declared capability. It rejects a requested enclosure when none of the checked
bases applies. A structural basis replaces the provider's support claim in the
returned geometry evidence; it does not claim validated arithmetic. Validated
assurance remains unsupported by the registry.

The H check compares stored finite binary64 coefficients and right-hand sides
for exact equality, separately for inequality and equality rows. Row order and
duplicate rows do not matter. It proves inclusion from the defining formulas
by retaining or adding constraints; it does not solve a containment problem,
recognize algebraically equivalent rows, establish nonemptiness, or validate
rounding of coefficients supplied by a provider.

The H/singleton check evaluates each finite stored coefficient-times-coordinate
product and sum as an exact dyadic value. An inequality must hold without a
tolerance, and an equality must be exactly zero. Checked arithmetic failure
rejects admission. This proves containment for the mathematical sets defined
by those particular stored binary64 values, including large cancelling
products; it does not prove that those values approximate a real-world model
or that earlier numerical set construction was outward rounded.

For native output, `size_budget` counts generator factor columns, H inequality plus equality rows, V
vertex plus ray rows, one singleton point, or one directional ellipsoid. Empty and universal forms count
zero. An unknown output size is rejected because the policy cannot verify the
budget. No finite error bound is admitted without a separate bound verifier.
Cancellation, stops and provider rejection remain distinct outcomes.

## Native box and parallelotope adapters (APP-02)

`<csl/geometry/box_parallelotope.hpp>` registers four binary64 methods on the
separate approximation port. `make_box_registration` computes one- or
two-dimensional outer axis-aligned H slabs from every vertex of a bounded
native V input. `make_parallelotope_registration` takes two independent finite
orientation rows and computes the four outer H slabs of a two-dimensional
rotated parallelotope. Its support products are accumulated exactly from the
stored binary64 values and rounded upward into finite binary64 H bounds. No V
rays are admitted by these bounded producers.

`make_inscribed_box_registration` and
`make_inscribed_parallelotope_registration` take four ordered binary64 corners
as explicit candidate constructions. The adapter checks exact diagonal sums,
nonzero area and, for boxes, axis alignment. It returns a native V set only
for a two-dimensional H input. The policy independently verifies **every**
candidate corner against **every** H inequality/equality row under exact
stored-value arithmetic. Convexity of H sets then proves inclusion of the
whole candidate V hull. The same policy checks every V vertex and recession
ray against every output H row for outer admission. Changing a label or a
single bound can invalidate admission; a provider assertion alone cannot pass.

The result evidence records orientation rows or ordered corners, requested
primitive budget, actual input and output row/vertex counts, and an unavailable
finite approximation-error bound. An outer box uses two H rows per coordinate;
a two-dimensional parallelotope uses four H rows; an inner candidate uses four
V vertices. Degenerate bounded V inputs can produce zero-width outer slabs.
Empty V inputs, V inputs with rays, unsupported dimensions, invalid orientation,
insufficient budgets and unsupported output representations receive named
capability results. An H candidate that is not contained receives an
independent-inclusion rejection. These relations concern the sets defined by
stored binary64 values. They are not validated enclosures of prior real-model
computations, an optimizer-family guarantee, or a finite Hausdorff bound.

## Zonotope reduction adapters (APP-03)

`<csl/geometry/zonotope_reduction.hpp>` registers two different methods.
`make_zero_generator_removal_registration` uses `ConversionPort` to remove
columns that are identically zero in an unconstrained native zonotope. The
remaining columns retain their factor IDs and stored coefficients. The physical
set is equivalent; constrained sources are rejected because a zero physical
column can still participate in factor equalities.

`make_axis_cover_registration` uses `ApproximationPort` for an outer native
zonotope. It retains the largest-magnitude source columns that fit with axis
replacement factors under the requested generator-column budget. Replacement
factor IDs include the complete request and source identities, so separate
requests through one registration do not accidentally synchronize. Every omitted
column contributes its absolute stored coefficient to a coordinate radius;
each radius is rounded outward from an exact dyadic sum. Retained IDs stay
unchanged. Removed IDs are relaxed into independent axes, and source factor
equalities are relaxed. The independent policy compares the immutable native
handles, exact retained columns and exact per-coordinate radius inequalities;
a forged provider result cannot establish inclusion by assertion.

The evidence records input, retained and output factor counts, requested
budget, and the dependency/equality relaxation. These are physical-set claims
for mathematical sets defined by stored binary64 coefficients. They supply no
error bound for prior rounded computations, realizable control witness,
optimizer-family enclosure, or comparison to a historical paper. Intersections
remain governed by their resulting representation class; these adapters never
return an intersection as an ordinary zonotope.

## Objective and plan claims

`objective_bound_side` gives the direction for the extremum of the *same*
objective over nested feasible sets. For minimization, an inner set gives an
upper bound and an outer set a lower bound; for maximization, the directions
reverse. Equivalent sets give both sides, and heuristic sets give neither.
This is a direction rule, not a computed bound or proof that an extremum is
finite. A caller must establish the relevant objective, set nesting, bound
value and numerical evidence before publishing a numerical bound.

An inner reachable state is not by itself an achievable plan. A concrete
state/control history must pass the original-problem trajectory verifier before
the caller may report a feasible plan. A reachable-set enclosure says nothing
about enclosure or completeness of an optimizer family. The policy returns no
family or achievable-plan claim, and the synthesis family publication gates
remain separate.

## Stage set and numerical achievable-plan check

`<csl/geometry/reachable_plan.hpp>` exposes `check_inner_state_plan`. The caller
declares a `StageSetReference` with the resolved problem identity, a stage in
`[0,T]`, the exact input set handle, ordered set-to-state coordinate indices,
and the reference ID used as the approximation request's ideal output. The
check matches the stage reference's resolved problem ID to the original
`ResolvedProblem` and the approximation request's problem ID, and matches its
reference ID to the request's ideal-output ID. It also requires the native
input set handle to be the same immutable payload and envelope, and the
coordinate indices to be the full original state order `0,...,n-1`. It does
not independently derive a `RequestId` from the declared stage. Registered
approximation admission separately checks provider evidence against the full
`GeometryRequestIdentity`, including `RequestId`. No projection or relabelling
is inferred. The resolved identity digest already includes the initial
information, external-input and information-pattern
semantics; the currently supported profile is nominal open-loop, a known
initial point, and absent or known external sequence. Uncertain, adversarial,
feedback and partial-coordinate references are unsupported here.

The check first invokes registered approximation admission for an **inner,
numerical** request. An admitted native empty set has no member. Native
singleton membership compares stored values exactly; native H membership
evaluates stored finite binary64 rows with checked exact dyadic arithmetic;
native universal membership accepts finite points. Other representations,
including nonempty V data without an independently verified membership
oracle, are unsupported. These checks concern only the stored set and point;
they do not validate the original model or prove that the caller-declared
reference set is the complete reachable set.

Only after the selected witness state is admitted does the function invoke
`verification::verify_trajectory` with a witness-only request against the
**unchanged** `ResolvedProblem`. `PlanCheck::numerical_achievable_value` is
present only when termination is completed, binding, feasibility and original
objective statuses are all `numerical_pass`, and the independently recomputed
original objective is finite. The value is that recomputed cost, never the
provider's objective or a set extremum. The report retains the approximation
outcome and, when run, the full trajectory report; rejection, violation,
unsupported membership, cancellation and numerical failure publish no value.
Numerical feasibility follows the trajectory verifier's stated binary64
tolerance policy. This is no validated real-model feasible-plan certificate,
global optimum bound, reachable-set completeness claim or optimizer-family
relation. It is a numerically checked, concrete plan value.

## Remaining APP-01 work

The initial APP-01 contract provided elementary structural enclosures, native H
constraint containment, and native H/singleton containment. APP-02 adds the
bounded V/H checks above. APP-03 adds native generator-axis outer admission.
Ellipsoid adapters still need independent claim-specific inclusion verification,
output-size accounting, and contract tests on analytic inner/outer cases.
The planned APP-02/03/04 adapters must not reinterpret numerical residuals or
provider declarations as inclusion proofs. A producer-side proof that a
declared stage reference is the complete reachable set, independent membership
for additional representations, nontrivial error bounds, validated
feasibility, and any optimizer-family enclosure need separate evidence.
None of this changes the current first-comparison synthesis scope.
