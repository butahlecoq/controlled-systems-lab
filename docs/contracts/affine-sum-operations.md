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

The API accepts `SetHandle` operands only. It does not accept `FiniteDomain` or
`MixedDomain`; callers must not replace either catalogue by its convex hull to
invoke these operations. Such domains require a separate explicitly modeled
operation/relaxation contract.

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
the caller's tolerance. This is an algorithmic numerical relation only. For a
finite V input, the source set is the convex hull of stored binary64 vertices,
interpreted as exact dyadics; the intended exact-real image or sum of that set
can still differ from the hull of rounded, generated candidates. Exact
candidate deletion preserves only that latter hull. For an H input, even the
input-to-vertex correspondence depends on the selected converter's numerical
coverage claim: checking each returned vertex against H rows does not prove
that all needed vertices were found. The operation reports no bound between
its output and either exact stored-input model or an authored pre-rounding real
model. `NumericalCheck.max_residual` does not supply such a bound. Binary64
overflow is reported as failure; finite underflow/cancellation can still alter
candidate coordinates. Validated assurance is rejected. The
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
