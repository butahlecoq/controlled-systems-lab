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
V representation. The module selects no converter, LP backend, or hull reducer
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
returns candidate indices and convex-combination removal evidence; this module
checks full candidate coverage, index validity, acyclicity, nonnegative finite
weights, normalization, and reconstruction against the execution tolerance
before publishing retained vertices. Reduction must be complete. Unsupported,
stopped, failed, malformed, or numerically inconsistent dependencies do not
produce a successful set result.

The result uses `SetRelation::equivalent` with `NumericalCheck` evidence under
the caller's tolerance. This is an algorithmic numerical relation only. It is
not exact arithmetic, validated set inclusion, a global Hausdorff/error bound,
or a proof of exact extreme-vertex enumeration. In particular, nearly
dependent candidates may be merged within tolerance, and binary64 overflow is
reported as failure. Validated assurance is rejected.

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
