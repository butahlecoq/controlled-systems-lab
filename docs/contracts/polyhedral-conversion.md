# Registered Qhull H/V conversion

`CSL::qhull_conversion` registers `csl.conversion.qhull` version
`1.0.0+qhull.8.0.2` on the existing `ConversionPort`. It consumes native
`csl.polyhedron.h` or `csl.polyhedron.v` sets and publishes the requested native
representation. The adapter owns the selected `Registration<LPPort>` by value;
it retains neither a registry nor a request borrow. Each generated feasibility,
boundedness, and relative-interior query goes through that registration's normal
capability, preparation, factory, and workspace path.

The implemented cross-representation profile is bounded H/V polyhedra over
finite binary64 coordinates. H-to-V checks feasibility, then finite lower and
upper coordinate optima using the selected LP backend. Explicit equalities are
reduced to `x = p + N z`; a selected-LP query searches for a positive relative
interior margin. Qhull enumerates facets of the resulting polar points and those
facets yield candidate vertices. Rank zero and rank one use direct structural
paths. V-to-H finds an affine basis, calls Qhull in that coordinate system for
affine dimension at least two, and restores the ambient affine equalities.
Segments and singletons are handled directly.

Empty H and V cases remain empty. A V input with no vertices is empty under the
repository's `conv(V)+cone(R)` convention, including if ray rows are present.
Nonempty V rays and LP-classified unbounded H inputs return `Unsupported` for a
cross-representation bounded conversion. `R^n` can convert to H directly; it
cannot become a finite V representation for `n > 0`. Same-representation
requests retain the immutable input handle. Validated assurance and other output
representations reject at capability admission.

There are no fixed ambient-dimension or row-count caps. Callers may set optional
`max_ambient_dimension` and `max_input_rows` admission policies. Qhull's signed
integer interface, checked container capacity and available memory remain
implementation limits. No combinatorial cap is silently inferred from the
scientific set class. Qhull has no in-call cancellation guarantee; cancellation
and deadlines are checked at the LP/native boundaries and after Qhull returns.

Every successful conversion includes request-bound `GeometryEvidence` with a
binary64 residual check and explicit assumptions. This is numerical evidence,
not a validated inclusion certificate. The residual audit checks the returned
vertices against the authored H rows/equalities, or the authored V points against
the returned H rows/equalities. Those finite checks do not independently prove
global set equality. Qhull documents empirical floating-point precision
handling; outside the bounded ambient-one H profile below, this module makes
no exact-arithmetic or universal error-bound claim. It makes no validated
containment claim in any profile. A successful `equivalent` relation is the adapter's
numerical algorithm claim under its recorded assumptions, not a proof promoted
by `check_geometry_evidence`.

For **ambient dimension one** H-to-V conversions, an additional independent
checker interprets each stored finite binary64 H coefficient and bound as an
exact dyadic rational. It derives the exact interval from all original
inequalities and equalities, then compares its two endpoints with the minimum
and maximum of the returned finite V vertices. Successful bounded nonempty
conversions publish an outward-rounded L-infinity Hausdorff bound in
`GeometryEvidence.error_bound`, measured in input-coordinate units. An exact
empty H set paired with an empty V output has bound zero by the empty-to-empty
convention. Contradictory nonempty/empty outputs, unbounded exact H inputs,
nonfinite vertices and arithmetic range failures do not publish this bound;
a successful numerical conversion is rejected if its purported one-dimensional
coverage cannot be checked. A returned vertex's small H-row residual alone
cannot hide a missing endpoint. This certificate covers the stored H rows,
not pre-rounding authored real coefficients. It is unavailable for ambient
dimension greater than one, including lines embedded in a higher-dimensional
space, and it does not change validated-assurance admission.

`QhullOptions::observe` receives an owning `ConversionObservation` after each
attempt. It records request identity, converter and LP backend identities,
representation names, row/vertex/ray counts, resolved affine dimension when
known, elapsed conversion time, outcome, diagnostics, and numerical check.
The synchronous callback runs after conversion cleanup and outside the timed
interval; callback synchronization belongs to its owner. Callback exceptions
propagate. This observation can feed the existing artifact/reporting path; it
does not silently create a global collector or a benchmark claim.

`QhullOptions::before_native_call` runs inline immediately before each
synchronous `qh_new_qhull` invocation. It is intended for caller-owned
coordination or instrumentation at the native-call boundary. Distinct
workspaces can invoke it concurrently, so shared callback state requires
caller synchronization. Exceptions propagate before the native call begins.

## Lineage audit: A17 and A18

The archival inventory identifies A17 as
`Scientific Research/GeoCalcLib-master/vertexEnumeration.m` (selected source
digest `d0f4ef…e5fd19`). Its short wrapper calls external `libgeocalc` and returns
vertex/ray data. The archived wrapper does not establish the native library's
algorithm, numerical guarantee, build identity, or executable equivalence to
this adapter.

A18 is `Конференция/ICIE 2018/VertexEnumeration.m` (selected source digest
`0d7089…7bee6`). It homogenizes the constraints, completes rank, chooses an
initial basis with randomized selection, performs inverse-based ray updates,
and divides by the homogeneous coordinate under its own epsilon policy. Qhull
polar facet enumeration is a different algorithm. This implementation neither
ports A18 nor claims output-by-output executable equivalence. Both sources
remain historical evidence only; the adapter is independently tested against
literal geometry cases.

The conversion uses Qhull v8.0.2, archive SHA-256
`8774e9a12c70b0180b95d6b0b563c5aa4bea8d5960c15e18ae3b6d2521d64f8b`, with the
reentrant C API and fixed `Qx` option. The complete upstream `COPYING.txt` is
installed under `share/CSL/notices/Qhull-8.0.2`; it retains the copyright,
redistribution terms, source-availability notice, and no-warranty statement.
No Qhull headers appear in the public CSL include tree.
