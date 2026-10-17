# V-representation support queries

`<csl/geometry/polyhedral_support.hpp>` and `CSL::polyhedral` provide the
`make_support_registration()` GeometryPort provider. It accepts `SupportQuery`
requests whose input is a native V representation or the explicit empty-set
representation. H, singleton, universal, and other representations are rejected
as unsupported; callers must select any conversion separately.

For a nonempty `conv(V) + cone(R)`, the provider computes each dot product
exactly for the represented binary64 direction and generators. A positive exact
ray dot product returns `UnboundedSupport` with no maximizer. If all ray dot
products are nonpositive, the maximum exact vertex dot product is returned
rounded to nearest binary64, together with a maximizing vertex, when that rounded
value is finite. If the exact finite value rounds to infinity, the request is
unsupported. An empty representation, including a V representation with no
vertices, returns `EmptySupport` with no maximizer, even if ray rows are present.

Evidence is bound to the complete request identity, ordered input ID, and
`support_value` scope. It describes the mathematical argument for the represented
binary64 data. `Assurance::validated` is unsupported; no claim is made about
authored real values or a real-valued model.

The workspace checks cancellation and deadlines at the start of execution,
before each ray and vertex dot product, and immediately before publishing a
successful result. Provider admission and workspace creation do not receive
the execution context and are not skipped for a stopped request. A dot product
is one native operation and is not interrupted midway; its latency is bounded
by the input dimension and fixed-width exact dyadic arithmetic.
