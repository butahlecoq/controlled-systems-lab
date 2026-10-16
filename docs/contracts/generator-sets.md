# Generator-set algebra and registered adapter: GEO-07 slices

`CSL::geometry_generators` exposes immutable native generator payloads through
`csl/sets/generator_sets.hpp` and three operations through
`csl/geometry/generators.hpp`. A payload denotes

```text
{ c + G ξ : -1 <= ξ_j <= 1, A ξ = b }.
```

Every generator column has a unique nonempty `FactorId`. A factor ID denotes
the same scalar across sets that reuse it. Zero equality rows give the
`csl.zonotope` handle representation; one or more rows give
`csl.constrained-zonotope`. A contradictory equality system is retained and
denotes the empty set, but this slice does not run an emptiness query or assert
an affine dimension. Both forms are bounded convex polyhedra over finite
authored binary64 coefficients. The immutable `SetHandle` round trip checks
that its envelope matches the native payload.

`affine_image` computes `(Mc+d, MG)` and keeps factor IDs and equality rows.
`dependent_sum` forms a **synchronized** sum: one column is used for every
shared factor ID, generator coefficients add into that column, and both input
equality systems remain in the joined factor space. Thus `ξ + (-ξ)` is a
singleton, not the interval `[-2,2]`. `minkowski_sum` implements the
independent sum only when ID sets are disjoint. A collision is explicitly
unsupported; callers must author a distinct factor identity to assert
independence. Summands need matching ambient dimension and ordered coordinate
labels. Neither operation drops zero columns or redundant constraints, so
later steps can recover dependence even when a current output coordinate
cancels.

`factor_polyhedron` gives the equivalent lifted H description in **factor**
coordinates: `ξ_j <= 1`, `-ξ_j <= 1`, and the original equality rows, together
with the affine map `x=c+Gξ` and ordered factor IDs identifying every H axis
and map column. This is an explicit exact representation
conversion in real-set algebra; it is not an ambient H/V materialization.
No general intersection, ambient H conversion, support, membership,
constraint feasibility, or generator reduction is exposed by the native slice.
An intersection must use a richer representation and must not be returned as
an ordinary zonotope through silent enclosure. Finite and mixed action
catalogues are outside this continuous-factor contract.

The registered `CSL::generator_adapter` target supplies a `GeometryPort` for
affine images and disjoint-ID Minkowski sums of native generator handles. Its
prepared-provider path retains IDs and equality rows in the output. A shared
ID means the factors are dependent, so the independent-sum port rejects that
request; use native `dependent_sum` for a synchronized sum. The adapter also
supplies a `ConversionPort` for an explicit, bounded unconstrained zonotope to
`csl.polyhedron.v` conversion. It enumerates every factor-cube corner, maps
each corner into ambient coordinates and returns the resulting V payload
without vertex deduplication or reduction. The caller must set a positive
vertex cap, and admission rejects a factor count whose `2^count` exceeds it.
The V payload has ambient coordinate labels but cannot carry factor identity.
Constrained conversion, intersection and output shapes outside these narrow
closures are unsupported.

The formulas and conversion are equivalent in real-set algebra. Coefficients
are stored and computed in binary64, so arithmetic can round. Input nonfinite
values, malformed shapes/IDs and nonfinite results are rejected; these checks
do not give a validated set inclusion or global error bound. The registered
port offers numerical assurance with a symbolic representation argument and
rejects validated assurance. This argument describes real-set algebra and
does not certify rounded coordinates. There is no performance claim.
Generator and equality storage can grow with repeated sums, and conversion
can grow exponentially in the number of factors. No automatic reduction is
performed.

The unit tests use independent literal H-polyhedron membership queries for a
box image, the synchronized cancellation singleton, and a constrained sum.
They also check the lifted H form, preserved factor IDs and rows, invalid inputs,
zero-column and contradictory-factor cases. A separate `find_package(CSL CONFIG)`
installed consumer checks both exported public targets. Prepared-provider tests
exercise literal ambient H answers and V vertices for the registered operations
and conversion. These finite cases establish behavior only for the supplied
coordinates, not general numerical validity.

## Publication gate

This algorithm produces numerical coordinates. Before this draft can merge,
freeze and independently review its source and a public-API report harness.
Build that commit cleanly in MSVC Release. Save warmups, at least seven
measured repetitions for the box image, shared-factor cancellation and
constrained diagonal fixtures, checking literal H oracle answers on **every**
run. Record the exact interval, work count, hardware/OS/compiler settings,
failures, unavailable counters and source commit. Keep raw records, figures,
versioned standalone HTML, offline ZIP and exact-byte manifest. Review the
saved bundle independently, merge and deploy from main, then open the immutable
Pages URL and link it in the PR and issue. Report a single-adapter exploratory
timing without a speedup or unsupported exact-arithmetic claim.

Issue #32 remains open after these slices. The registered adapter adds a
bounded subset of the requested closure and conversion surface. A separate
fixed-source public-API report and review are required before this numerical
adapter can merge; the native algorithm's report does not cover the new port.
The full acceptance checklist, including broader geometry integration,
remains to be reviewed.
