# Finite polyhedral affine images and Minkowski sums

`CSL::affine_sum` registers `csl.geometry.affine-sum` behind `GeometryPort`.
It implements `AffineImage` (`y = Mx + b`) and `MinkowskiSum` for finite
polyhedral inputs represented by the native set data contract. The operation
returns a finite V representation. It does not implement intersection,
projection, support queries, predecessor operations, or either synthesis
strategy.

## Admission and dependencies

V representations are accepted only when they have no rays. Empty, singleton,
and zero-dimensional representations retain their mathematical definitions.
Positive-dimensional universal sets and unbounded V sets are unsupported. H
representations require a caller-selected `ConversionPort` whose concrete
request is admitted at operation time and whose result is an equivalent finite
V representation with `NumericalCheck` support. Before consuming its vertices,
the module checks every returned vertex against each original H row using the
row scale `max(1, abs(activity), abs(bound))` and the caller comparison
`residual <= absolute_tolerance + relative_tolerance * scale`. It also requires
the provider's reported `max_residual` to be no larger than the largest
caller-compatible threshold among those vertex-row checks (or the base
threshold when there are no rows). Here the provider's residual is interpreted
as the raw maximum inequality violation or equality residual in original H-row units; providers
with other residual semantics are rejected by this operation. This is a
conservative local check, not a proof that the converter enumerated every
vertex. The module selects no converter, LP backend, or hull reducer
implicitly. Generated hull queries go through `RegisteredLPQueryRunner`, which
prepares each request against the frozen selected LP provider before creating
its request-specific workspace.
The LP provider must be prepared for the `csl.program-result.v1` output
representation, matching the native LP result contract.

Minkowski summands must have the same ambient dimension and identical ordered
coordinate labels; the unnamed coordinate system is compatible only with
another unnamed system. Affine image labels are supplied through
`AffineSumOptions`; empty labels mean unnamed output coordinates. Input affine
dimension claims are not copied because singular maps and sums can change them.
Output evidence binds the original ordered input IDs and complete caller
request identity.
The selected hull reducer and LP provider identities are recorded in output
assumptions; the converter identity is also recorded when a dependency is
configured. Conversion assumptions are retained with the operation evidence.
Generated outer LP queries record requested/actual provider identity and
request/outcome. Basis-reuse and recursive reducers also record child LPPort
calls made through reducer-owned workspaces. These records have a 4,096-call
per-workspace cap, with total and omitted counts shown when the cap is reached.
Each record limits raw diagnostics to 1,024 characters and marks truncation.
They describe LPPort calls and outcomes; they do not establish that a native
solver was entered. Reducer aggregate metrics and exact removal certificates
remain separate from these query records.

The API accepts `SetHandle` operands only. It does not accept `FiniteDomain` or
`MixedDomain`; callers must not replace either catalogue by its convex hull to
invoke these operations. Such domains require a separate explicitly modeled
operation/relaxation contract.

## Source-index method path

`SourceIndexHullPort` is a separate proposal interface for methods that return
original point IDs without the exact dyadic barycentric certificates required
by `HullReducerPort`. `make_affine_sum_registration(SourceIndexAffineSumDependencies)`
selects this path explicitly. The built-in adapters are QuickHull2D and the
source-faithful BTULSHOR KPABEP/MODIF profile. The latter preserves its source
epsilon, MODIF status sequence, candidate IDs, pivot counts, and configured
resource/trace limits. It does not claim to provide a second historical
baseline/modified variant.

After candidate generation, affine-sum hashes the ordered binary64 cloud and
independently calls the bounded exact 2D source-index checker on that cloud and
the selected provider's proposed IDs. The operation applies the IDs only when
the checker returns `verified`. The checker proves every generated candidate is
in the hull of the returned source points; since each returned point is drawn
from that cloud, this proves equality of the represented finite hull. It does
not establish vertex minimality or a historical REACH reproduction. The
checker is limited by its configured point and wall budgets and checks
cancellation and the parent operation deadline during enumeration.

Source-method and checker invocations, statuses, elapsed times, configuration,
proposed IDs, and available internal trace facts are recorded separately in
the operation evidence or failure diagnostic. A stopped, malformed, incorrect
or inconclusive proposal fails the source-index operation with the raw proposal
details preserved. It is never replaced by a modern reducer or applied to the
output. This path does not select or invoke a vertex LP; the LP role is
`not_used`. The H-to-V converter remains independently selected when an input
is H-represented. Modern `HullReducerPort` outputs retain the existing exact
dyadic removal-certificate and LP-call accounting gates without change.

Source-index methods reject dimensions other than two before invocation,
including QuickHull2D requests that must not be silently projected. A zero
checker wall budget is permitted to retain an explicit timeout outcome; the
point limit must be positive.

For the known legacy/simplex comparison axis, the available faithful Pascal
KPABEP/MODIF source is one baseline profile. The separately registered ITIS17
A43 and A44 reducers are paper-derived modified methods with their own recorded
adaptation boundaries and exact deletion-certificate gates; they are not
alternate BTULSHOR source listings. The QuickHull profile is a geometric
reference, not a simplex variant. A distinct second Pascal baseline/modified
listing has not been identified, so the catalogue reports only these actual
methods and does not infer a missing implementation from a related MATLAB file.

## Numerical relation and limitations

Candidate coordinates are computed in binary64. The selected hull reducer
returns candidate indices and convex-combination evidence; this module checks
full candidate coverage, index validity, acyclicity, nonnegative finite
weights, normalization, and numerical diagnostics. It applies the retained
indices only when each removal is independently proven by exact dyadic
arithmetic over the represented binary64 coordinates and weights: the weights
are nonnegative, sum exactly to one, and reconstruct the removed point exactly.
Tolerance-based residual checks never authorize deletion. If any structural or
exact check fails, the operation keeps the full generated candidate cloud.
`NumericalCheck.max_residual` records floating-point residual diagnostics; it is
not the deletion proof or an error bound. Unsupported, stopped, failed,
malformed, or numerically inconsistent dependencies do not produce a successful
set result.

The result uses `SetRelation::equivalent` with `NumericalCheck` evidence under
the caller's tolerance. This is an algorithmic numerical relation only. For
direct finite V, singleton, and empty inputs, the operation also reports an
outward-rounded `GeometryEvidence.error_bound` when exact dyadic arithmetic
can represent the post-hoc discrepancy. It also composes that candidate bound
with independently recomputed coverage bounds for bounded ambient-one H
inputs and bounded axis-aligned boxes in supported dimensions when every
converted operand has a verifiable exact stored-dyadic interval or box. Its
metric is L-infinity Hausdorff distance on output coordinates,
and its units are maximum absolute output-coordinate units. For candidate
generation, the bound compares every generated binary64 point with the exact
affine image or Minkowski pair operation on the stored (possibly converted)
binary64 vertices. Let `E_gen` be the largest such coordinate discrepancy and
`E_H` a certified H-to-V coverage bound from either supported exact interval
or box profile. The affine-image bound includes
`max_row(sum_col(abs(M[row,col]))) * E_H + E_gen`. The Minkowski bound includes
`E_H,left + E_H,right + E_gen`; direct finite V operands contribute zero
conversion error. These compositions use exact dyadic accumulation and are
rounded up to representable binary64. They follow by pairing convex
combinations and by the induced L-infinity operator norm / Minkowski sum
inequality. For a box input, the certificate checks every converted point is
inside the exact box and that every distinct box corner is present, capped at
4,096 corners. Exact candidate deletion adds zero error because deletion
preserves the generated hull exactly. For an empty result, the bound is zero
under the empty-to-empty distance convention stated in the evidence units.

This bound says nothing about authored pre-rounding real values or uncertainty
in how input coordinates and coefficients were obtained. H inputs outside the
bounded ambient-one interval or supported axis-aligned-box profiles receive no
operation error bound: checking returned converted vertices against H rows
does not prove that all needed vertices were found. For supported inputs,
affine-sum independently recomputes exact H coverage against returned V
extrema or box corners; it does not trust a converter's numerical relation or
residual as global coverage evidence. If
exact arithmetic cannot produce a finite outward binary64 bound, the operation
fails closed instead of returning an unbounded or rounded-down value.
`NumericalCheck.max_residual` remains a reducer diagnostic and does not supply
this bound. Binary64 overflow is reported as failure; finite underflow and
cancellation are included by the exact post-hoc comparison. Validated
assurance is rejected. The
[scientific audit](../research/geo02-floating-model-audit.md) gives the precise
conditional finite-V error theorem, a counterexample, and the proof required
before a caller can claim real-model inclusion or a global error bound.

`max_candidates` is an optional admission limit on the generated cloud, not an
intrinsic dimension restriction. Products and coordinate storage are checked
before allocation. Cancellation/deadline checks occur before conversion and
generation, during candidate generation, and at dependency boundaries; an
already-running selected dependency controls its own interrupt responsiveness.
The core memory policy is not a hard allocator guarantee, and host allocation
failure may propagate.

Contract tests use literal supports for intervals and squares, rectangular and
singular maps, H equality segments, empty and singleton inputs, and `R^0`. They
also exercise the selected HiGHS and phase-I LP paths. Those floating-point
oracles validate the implemented numerical behavior; they do not validate exact
geometry claims.

## Delivery impact

The public geometry headers add `SourceIndexHullPort` and an explicit
source-index affine-sum registration overload. `CSL::affine_sum` now has a
public dependency on the bounded hull checker and private implementation links
to QuickHull2D and the source-faithful BTULSHOR library for that overload.
Existing `HullReducerPort` call sites retain their current interface. This changes the installed CMake target's dependency graph and
requires installed-consumer validation; it does not add a package registry or
change the project version. Release/package impact for the PR: no release is
prepared here; reviewed consumer validation remains a delivery gate.
