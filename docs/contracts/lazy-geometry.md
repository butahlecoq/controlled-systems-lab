# Lazy V geometry contract

GEO-08 exposes three separately selected registrations through the public
`<csl/geometry/lazy.hpp>` header and installed `CSL::lazy_geometry` target.
Callers retain and pass ordinary `SetHandle` values. The module copies typed
operands into an immutable payload, so expression handles remain usable after
the original request and operand variables are released.

## Expression creation

Select `csl.geometry.lazy-expression` through `GeometryPort`. The request must
name the implementation and a complete `GeometryRequestIdentity`, request an
equivalent set relation with numerical assurance, and ask for representation
`csl.geometry.lazy-v`. Supported operations are affine image, coordinate
projection with distinct indices, and independent Minkowski sum. Leaves are
native V or empty sets; expressions may be nested. The operation's full typed
operands, including map, offset, indices, child handles and ordered source IDs,
are stored. Admission rejects unsupported shapes, dimensions, coordinate
labels, assurance, and source representations before a workspace is created.

Creating an expression never enumerates Cartesian-product vertices. Its
`OperationResult` describes a mathematically equivalent relation, with
`Unestablished` evidence for binary64 arithmetic. Neither this relation nor
the expression handle certifies a validated floating-point enclosure.

## Support queries and samples

Prepare a native V leaf support provider, then supply that prepared provider
to `make_support_registration`. Select `csl.geometry.lazy-support` for
`SupportQuery` on the expression. Affine images transform the direction by the
map transpose and add the offset contribution; projections lift directions
into source coordinates; independent sums add child support values. Finite
answers include a maximizing point. Empty and unbounded answers remain
distinct. The selected leaf provider is consulted for native V leaves. The
result retains the query identity, input ID and numerical evidence limit.
Support admission checks each reached leaf query against the caller-selected
prepared provider before creating a workspace. A provider refusal remains a
rejection rather than a late partial answer.
Affine direction products that underflow to zero are refused. The native V
ray classification is checked against exact signs of the stored binary64
direction and ray coordinates; disagreement with the selected leaf provider
is refused rather than presented as finite support.

`sample_support` evaluates a finite direction list against a prepared lazy
support provider. Its `SampleCoverage::directions_only` label means precisely
those directions were sampled. It does not return a set representation,
complete support function, or inclusion certificate. A failed or stopped
batch publishes no partial sample list.

## Explicit materialization

Register `make_materializer({max_vertices, max_rays})`, select the conversion
provider, and pass a `ConversionRequest` for native `csl.polyhedron.v` to
`materialize_expression` with a caller budget. Both limits are mandatory;
there is no unbounded default. The wrapper reports the selected provider,
expression lineage, source/estimated/peak/realized V row counts and the caller
limits. Affine and projection nodes retain row counts; independent sums can
multiply vertex counts and combine rays. Shared expression nodes are evaluated
once per call. Preflight rejects row-count or cell-count overflow and a limit
breach before output allocation. Execution polls cancellation and deadlines,
rejects nonfinite arithmetic, and returns either a complete native V result or
an explicit failure with no partial set.

The V output retains redundant vertices and rays. A limit is a row-count cap,
not a byte or time budget. The module does not implicitly select an H/V
converter, reduce the hull, or fall back to approximation. Materialized
binary64 output has `Unestablished` evidence: row enumeration is not a
validated coverage or rounding certificate. Callers needing H output or a
stronger guarantee must select a separate admitted route and check its own
evidence.

## Installed consumer

`tests/installed/lazy_geometry_client.cpp` uses only installed headers and
`find_package(CSL CONFIG)` targets. It creates a two-dimensional square,
retains an affine expression, samples support in direction `(1, 1)`, and
materializes the four V rows with an explicit `{4, 0}` budget. The expected
support value is `3`; this is a literal functional check, not a performance
measurement or a validated arithmetic claim.
