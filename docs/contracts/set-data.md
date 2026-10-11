# Immutable polyhedral and elementary set data

GEO-01 provides `csl::sets` in `<csl/sets/data.hpp>` and the installed target
`CSL::sets`. It depends on `CSL::numeric` and the unchanged revision 1.1 core
contracts. This module stores mathematical descriptions. Geometry operations,
conversion, feasibility, affine-rank computation and approximation belong to
their separate ports and tickets.

## Set definitions and identity

`make_h` stores `{x in R^n : Ax <= b, Ex = f}`. Inequality and equality rows
remain separate, in authored order. Redundant or rank-deficient constraints are
legal. No equality is replaced with paired inequalities. Either matrix may have
zero rows; both still have n columns. Contradictory constraints are legal data
and are not diagnosed as infeasible here. With no rows the formula is all of
R^n, although the H data's feasibility, boundedness and affine dimension remain
uncomputed.

`make_v` stores `conv(V) + cone(R)`, with one vertex/generating point or ray per
row, each of length n. Redundant points, duplicate points, zero rays and opposite
rays are retained; no extremality or hull reduction is implied by the field
name `vertices`. `cone(empty) = {0}` and `conv(empty) = empty`. Thus **zero vertex
rows mean the empty set even when rays are supplied**. Represent a cone with an
explicit origin vertex, and lineality with positive and negative rays. This
convention represents nonempty polyhedra with lineality without a special
implicit-origin rule. A 1-by-0 vertex matrix describes the unique point in R^0;
a 0-by-0 vertex matrix describes the empty set.

`make_empty`, `make_singleton` and `make_universal` preserve distinct elementary
representations. In R^0, the singleton of the empty coordinate vector and the
universal set are mathematically equal but retain different representation
identities; the empty set remains different from both. A missing affine-dimension
claim never means an empty set or a missing port.

Factory-assigned representation IDs are `csl.polyhedron.h`, `csl.polyhedron.v`,
`csl.empty`, `csl.singleton` and `csl.universal`. The caller supplies a nonempty
`SetId`; the module does not allocate IDs, enforce global uniqueness, or infer
that matching IDs prove mathematical equality. Coordinate labels are optional;
when present, there must be n unique, nonempty strings in coordinate order.

## Dimensions, properties and evidence

`Metadata::set.dimension` is the ambient dimension. `affine_dimension` is
optional: absence means unknown. Its value distinguishes `DimensionValue{k}`
from `EmptyAffineDimension`, using the convention `dim(aff(empty)) = -1`
without encoding -1 in an unsigned integer. Nonempty affine dimension zero is
distinct from the empty-set convention.

H/V factories accept an optional `AffineDimensionClaim`. They reject dimensions
above n, and V declarations that contradict the structural empty/nonempty
vertex-row distinction. They **do not verify a supplied rank or feasibility
claim**, including one with a symbolic argument or certificate reference.
Claims are retained with `DimensionOrigin::supplied` and their original
`EvidenceSupport`. Other mathematical inconsistencies can remain in an
unverified claim; a consumer requiring established rank must run its verifier.
Numerical tolerances, residuals and proof references are retained as supplied
provenance, not independently assessed evidence.

Elementary factories establish dimensions from their definitions: empty -1,
singleton 0, and universal n. These have `DimensionOrigin::definition` with a
`SymbolicArgument`. They provide no validated rounding guarantee.

All five representations are convex and polyhedral by definition. Empty and
singleton sets are bounded; universal R^0 is bounded, universal R^n for n>0 is
unbounded. Finite V data without rays, and V data without vertices, are bounded.
H data and other ray-bearing V data report boundedness as unknown. In
particular, a solver flag or an unchecked dimension declaration never upgrades
these properties. These symbolic facts concern the sets defined by the stored
finite doubles interpreted as real numbers.

The data module has no `Assurance` switch and returns no operation/conversion
`SetRelation`. An exact defining formula is not evidence of equivalence to
some separately authored set, validated numerical arithmetic, or an operation
result. Those claims retain the existing request-bound geometry evidence
contracts. Supplying equivalent H/V segment fixtures in tests is not an
implemented H/V conversion.

## Ownership and cost

Author coefficients with CORE-03 `numeric::snapshot` / `snapshot_vector` first.
Those factories validate shape and finite logical coefficients and copy producer
storage once. Set factories accept only their immutable retaining handles;
there is no raw mutable matrix/vector input path. Sparse, strided and dense
storage are preserved without materialization. Every stored coefficient and
bound is finite by the numeric handle invariant.

Set factories snapshot the description, labels and supplied evidence strings,
including when the caller uses `std::move`. Mutable aliases into producer
metadata cannot modify the created set. Numeric handle retention and `SetData`
copies take O(1) time and copy no coefficients. Metadata creation and validation
cost O(total label/ID/evidence text), with expected linear label uniqueness
checking. H/V shape checks and retention cost O(1); no numeric rows are scanned.
Memory allocation failures follow standard C++ allocation exceptions.

`metadata()` returns an aliasing `shared_ptr<const Metadata>` that retains the
set's private storage. Queries allocate nothing, copy no labels/evidence and do
not access numeric payloads. Retain that pointer while borrowing a metadata
reference. It keeps the set payload alive as well as metadata. `representation()`
returns a small typed variant of immutable numeric handles; each can outlive the
original set. Numeric descriptor spans remain borrowed from their corresponding
retained numeric view, as specified in [numeric data](numeric-data.md).

`as_handle()` exports the existing generic `SetHandle`: the immutable payload
is shared, while its small metadata envelope and ID strings are copied.
`from_handle()` accepts only this module's private final payload type and checks
the envelope's ID, dimension, representation and all three property fields
against the retained metadata. A changed envelope returns `invalid_input` at
`sets.handle.metadata`; null or foreign payloads return `unsupported` at
`sets.handle.payload`. Imported native data is retained without numeric copying.
The closed typed variant is for native representation consumers; generic
planners continue using `SetHandle` and registry-selected operation ports.

Construction returns `variant<SetData, Diagnostic>`. Structural input errors
use `invalid_input` with fields `sets.id`, `sets.labels`, `sets.h.shape`,
`sets.v.shape`, `sets.singleton.shape` or `sets.affine_dimension`. Numeric input
errors are diagnosed earlier by CORE-03. SetData has no invalid default state
or public constructor accepting an arbitrary payload.

## Verification scope

The public tests retain the hand-derived segment `y=0, -1<=x<=2` as H data and
the supplied V endpoints `(-1,0),(2,0)`, affine dimension 1 in ambient dimension
2, with named coordinates. Additional cases cover rays and lineality,
zero-dimensional and empty descriptions, elementary definitions, malformed
shapes/labels/claims, producer mutation, metadata/numeric lifetimes, evidence
provenance and core handle import. The source and installed public consumer
exercise the exported header and target using Release-active checks.

This is the representation and elementary-definition portion of T-G01.
Affine-image, sum, intersection, support and preimage operation oracles remain
for the later GEO tickets; none is claimed as executing here.
