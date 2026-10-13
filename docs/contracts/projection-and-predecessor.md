# Coordinate projection and nominal predecessor

`CSL::polyhedral` adds `csl.geometry.polyhedral-projection@1.0.0` through
the existing `GeometryPort`, and `csl.geometry.projection-materializer@1.0.0`
through `ConversionPort`. No operation registry, LP backend, numerical
coverage threshold or default dimension limit is added.

This is a provisional analytic regression profile for GEO-05, not owner
approval of the exact-operation/capacity profile proposed in architecture
PRs [#146](https://github.com/butahlecoq/controlled-systems-lab/pull/146) and
[#152](https://github.com/butahlecoq/controlled-systems-lab/pull/152).
The general route does not invert the state matrix. An inverse adapter is
not implemented or selected implicitly.

## Supported projection requests

`OperationRequest` names `Projection`, the immutable native input handle,
ordered zero-based coordinates, request/ideal identities, the selected
implementation, required relation and assurance. The selected provider's
frozen `Requirements` names the output representation. Coordinate indices
must be distinct and in range; both named and unnamed coordinate systems
retain their ordering. Supplied affine-dimension claims are not transferred.

`ProjectionOptions.output` selects one concrete capability:

| Output | Accepted input | Materialization |
|---|---|---|
| `h` / `csl.polyhedron.h` | Native H, singleton, empty, universal | Equality-pivot substitution, then Fourier--Motzkin elimination |
| `v` / `csl.polyhedron.v` | Native V, singleton, empty | Copy selected coordinates of all vertices and rays |
| `lazy` / `csl.polyhedron.projection` | Any native set above, or this module's lazy projection | Retain immutable source and coordinate map; perform no elimination |

Universal sets are supported in H and lazy form; a universal-to-V generator
construction is outside this profile, including `R^0`. Cross H/V conversion
is a separate provider operation. A lazy input can be projected again;
its coordinate map is composed to the original native source and earlier
creation claims remain in ordered lineage. `inspect_lazy_projection`
returns the source, map, ordered labels, current creation evidence and
earlier claims. It validates the public envelope against the owned payload.
`sets::from_handle` intentionally accepts native set storage only; use the
inspection API for this separate representation.

A supported `ConversionRequest` to the materializer requests H or V and
binds the lazy input identity and new ideal output. The same input/output
profile applies. Unsupported requests are rejected before workspace
creation; there is no implicit Qhull enumeration or ray truncation.

H elimination retains inequalities and equalities separately. A nonzero
equality coefficient permits substitution and removal of that pivot
equation. Otherwise, each positive/negative inequality pair generates a
constraint independent of the eliminated coordinate. One-sided rows do
not constrain the remaining coordinates. Only exactly zero tautologies
are removed; no coefficient tolerance decides rank, sign or redundancy.
Surviving equalities remain authored equality rows. Contradictory constant
rows become the H description `0 <= -1`. Projection onto zero coordinates
distinguishes the nonempty point in `R^0` from the empty set.

V materialization preserves every generator, including duplicate vertices
and rays whose selected image is zero. It does not replace an unbounded
set with its finite vertices. `conv(V)+cone(R)` retains the native convention
that zero vertex rows mean the empty set, even if ray rows are present.

## Typed existential predecessor adapter

`NominalPredecessorRequest` records ordered `[X,U,S]` handles, `A[n,n]`,
`B[n,m]`, offset `a[n]`, full identity, relation and assurance. The first
profile accepts H, singleton, empty and universal operands. State and
target coordinates must have identical ordered labels or both be unnamed.
Discrete/finite/mixed control catalogues are outside this API and must not
be convexified to use it.

The adapter compiles the immutable joint H relation in coordinates `[x,u]`:

```text
x in X
u in U
H_S * [A B] * [x,u] <= b_S - H_S * a
E_S * [A B] * [x,u]  = f_S - E_S * a
output = project joint relation onto [0,...,n-1]
```

`prepare_nominal_predecessor` submits that complete concrete `Projection`
to the caller-selected owning `PreparedProvider<GeometryPort>` and creates
no workspace. `PreparedNominalPredecessor::run` creates a fresh exclusive
workspace only after admission. The snapshot owns authored matrices and
handles independently of later caller edits and of registry lifetime.
There is one provider operation in this chain; joint-row assembly models
the request's linear constraints and adds no competing geometry operation.

The result checks the provider's equivalent relation, original child-request
evidence binding, output dimension and ordered state labels. It records
neutral requested/actual provider provenance, child projection identity and
state indices. The original predecessor evidence binds `[X,U,S]`, the
original request identity and original ideal output. Output state labels
remain X's labels; generated control labels avoid collisions in the joint
schema. The opaque projected set identity names the compiled-joint projection
and is distinct from the original predecessor ideal-reference identity.

## Guarantee transfer and limits

`SetRelation::equivalent` identifies the requested projection/predecessor
algebra. It does not establish arithmetic correctness. H elimination uses
binary64 divisions, additions and equality substitutions; its relation
support is **Unestablished**. Finite arithmetic can round, cancel or
underflow. No numerical set-residual verifier, exact inclusion, independent
coverage procedure or error bound is implemented, and no invented zero
residual is returned. Validated assurance and non-equivalent requests are
unsupported. This profile must not satisfy a complete-family geometry gate.

V projection and lazy retention use `SymbolicArgument` for the coordinate
selection theorem relative to the stored input. They do not upgrade the
input's relation to any earlier ideal set. A lazy materialization's claim
binds its own input/request and retains creation-request provenance in its
assumptions; H materialization returns unestablished support. The predecessor
always keeps unestablished support because its original target-row pullback
also uses binary64 arithmetic, even if its child projection is lazy or has
stronger support. Provider error bounds cannot transfer to that original
claim and are removed. The provider's original child claim remains attached
to the immutable lazy payload when present.

`max_rows` is a caller-selected limit on H inequalities plus equalities,
including intermediate rows. It is enforced on H materialization, so lazy
creation can succeed before a later materialization exceeds that policy.
There is no built-in universal dimension or output-size threshold. Counts,
products and matrix storage are checked against `size_t`. With p positive,
q negative and z zero rows, one Fourier--Motzkin step generates `p*q+z`
inequalities; repeated steps may grow exponentially. This implementation
does not minimize or deduplicate those rows. Nonfinite arithmetic and
capacity failures return Unsupported without a successful partial set.
Host allocation failures can propagate; `ResourcePolicy.memory_bytes` is
not a hard allocator limit. Stop/deadline checks occur before execution,
between eliminated coordinates and during generated row/vertex work;
individual copying/substitution operations are not asynchronous.

## Regression evidence and publication status

The contract tests use independent literal oracles for an offset integrator,
singular A with a free state direction, an unreachable equality target,
zero controls, ordered equality projection, V rays, empty/nonempty `R^0`,
one-sided elimination, immutable preparation, lazy composition and explicit
admission/stop/capacity/arithmetic failures. These are functional tests,
not benchmark trials or a numerical completeness policy. The installed
consumer independently checks the integrator interval `[1,3]`.

No GEO-05 numerical report, accepted measurements or deployed report URL is
published by this implementation change. The required sequence remains
fixed-code independent review, clean Release collection, versioned raw
records and saved-data HTML, independent artifact/measurement review,
visual QA, registered publication and live URL/download verification under
the [published-results policy](../architecture/published-algorithm-results.md)
and [report-record contract](algorithm-report-records.md). Existing report
records and catalogues are unchanged. GEO-05 remains open until that
delivery and the reviewed exact-operation/capacity profile are satisfied.
