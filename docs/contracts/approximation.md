# Approximation policy and evidence (APP-01 prerequisite)

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

For native output, `size_budget` counts H inequality plus equality rows, V
vertex plus ray rows, or one singleton point. Empty and universal forms count
zero. An unknown output size is rejected because the policy cannot verify the
budget. No finite error bound is admitted without a separate bound verifier.
Cancellation, stops and provider rejection remain distinct outcomes.

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

## Remaining APP-01 work

This prerequisite does not close #24. It provides elementary structural
enclosures, native H constraint containment, and native H/singleton
containment. A nontrivial box,
parallelotope, zonotope or ellipsoid adapter needs
an independent inclusion verifier with claim-specific evidence, a compatible
output-size accounting method, and contract tests on analytic inner/outer cases.
The planned APP-02/03/04 adapters must not reinterpret numerical residuals or
provider declarations as inclusion proofs. A public flow connecting an admitted
inner reachable state to a separately verified concrete trajectory and bound
claim is also needed before the full achievable-plan acceptance criterion is
met. That next contract needs a stage-indexed reachable-set reference bound to
a `ResolvedProblem` identity, the exact initial/information/external-input
semantics, and the coordinate map for the inner state. It must accept a concrete
`Witness`, check that the chosen stage state belongs to the admitted inner
result, then require `verification::verify_trajectory` on the unchanged
original problem to report completed numerical-pass bindings, feasibility and
objective with a recomputed original objective. Only then may it publish a
numerical achievable-plan value; validated feasibility and a bound on the
global optimum need separate proof. A follow-up contract PR can establish the
reference and result types, followed by an implementation PR with analytic
positive and negative trajectories, wrong-stage/problem bindings, and
unsupported-profile cases. None of this changes the current first-comparison
synthesis scope.
