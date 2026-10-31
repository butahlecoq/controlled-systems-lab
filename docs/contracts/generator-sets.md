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
or constraint feasibility is exposed by the native slice.
An intersection must use a richer representation and must not be returned as
an ordinary zonotope through silent enclosure. Finite and mixed action
catalogues are outside this continuous-factor contract.

The registered `CSL::generator_adapter` target supplies a `GeometryPort` for
affine images, disjoint-ID `MinkowskiSum`, and the explicitly typed
`DependentSum` of native generator handles. Its prepared-provider path retains
IDs and equality rows in the output. A shared ID means the factors are
dependent: `MinkowskiSum` rejects that request, while `DependentSum` admits it
and calls the native synchronized algebra. The latter also accepts disjoint
IDs, with the same set as the independent sum in that case. The `DependentSum`
request is a factor-identity operation, not an operation on physical set points
alone; other set representations have no implicit factor interpretation. The
adapter checks the native handle envelope and matching ordered coordinate
labels before a workspace is created. The registration version is `1.1.0`;
version-pinned `1.0.0` callers must select the new version of this registration.
The adapter also supplies a `ConversionPort` for an explicit, bounded unconstrained zonotope to
`csl.polyhedron.v` conversion. It enumerates every factor-cube corner, maps
each corner into ambient coordinates and returns the resulting V payload
without vertex deduplication or reduction. The caller must set a positive
vertex cap, and admission rejects a factor count whose `2^count` exceeds it.
The V payload has ambient coordinate labels but cannot carry factor identity.
Constrained conversion, intersection and output shapes outside these narrow
closures are unsupported.

### Constrained-generator recovery boundary (TEST-20 / #100)

The current adapter has no constrained-zonotope recovery procedure. This is a
deliberate capability boundary, including for an infeasible constrained
generator: `ConversionPort` rejects the request with an `unsupported`
`generators.convert.equalities` diagnostic before producing an ambient V set,
recovery witness, trajectory or achievable objective. The contradiction is
still represented exactly in the factor-domain H rows, so callers that need an
infeasibility proof must use a future dedicated factor-feasibility operation;
they must not reinterpret this adapter rejection as a proof of the physical
problem's infeasibility. The [generator adapter contract test](../../tests/contract/geometry/generator_adapter_tests.cpp)
checks both the contradictory factor rows and this explicit rejection. This
profile remains unsupported until a separately reviewed recovery operation is
implemented; TEST-20 tracks that remaining acceptance boundary in [issue
#100](https://github.com/butahlecoq/controlled-systems-lab/issues/100).

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

The separate [APP-03 reduction adapters](approximation.md#zonotope-reduction-adapters-app-03)
offer exact zero-column removal and an explicit budgeted outer axis cover. The
second method relaxes omitted `FactorId` dependencies and factor equalities;
the independent approximation policy checks stored-binary64 inclusion. Neither
method silently changes the native algebra above.

The unit tests use independent literal H-polyhedron membership queries for a
box image, the synchronized cancellation singleton, and a constrained sum.
They also check the lifted H form, preserved factor IDs and rows, invalid inputs,
zero-column and contradictory-factor cases. A separate `find_package(CSL CONFIG)`
installed consumer checks both exported public targets. Prepared-provider tests
exercise literal ambient H answers, synchronized shared-factor cancellation,
both constrained equality systems, and V vertices for the registered operations
and conversion. These finite cases establish behavior only for the supplied
coordinates, not general numerical validity.

## Publication gate for the registered dependent sum

This newly registered numerical operation needs a distinct saved report; the
published native and registered-adapter reports do not exercise this request.
Before this source PR can merge, freeze and independently review its source and
a public-API report harness. Build that commit cleanly in MSVC Release. Save
warmups and at least seven measured repetitions for shared-factor cancellation
and constrained shared-factor fixtures, checking literal H oracle answers on
**every** run. Record the exact interval, work count, hardware/OS/compiler
settings, failures, unavailable counters and source/harness commits. Keep raw
records, figures, versioned standalone HTML, offline ZIP and exact-byte
manifest. Review the saved bundle independently, merge and deploy from main,
then open the immutable Pages URL and link it in the PR and issue. Report a
single-adapter exploratory timing without a speedup or unsupported
exact-arithmetic claim. The full issue #32 checklist remains open until that
publication and an issue-level acceptance audit are complete.
