# LP-backed finite hull reduction

`<csl/geometry/hull_reducer.hpp>` and `CSL::hull` provide a baseline reducer for
finite point clouds using any existing `LPWorkspace`. Input point positions are
stable identities. The module does not depend on HiGHS or phase-I basis
diagnostics.

When the LP solver is selected through `LPPort`, use
`registry::RegisteredLPQueryRunner` as the reducer's `LPWorkspace` dependency.
It owns the frozen provider and re-admits each generated membership program
before creating a request-specific workspace. Admission rejections create no
LP workspace and make the reduction incomplete. Per-query records retain the
program identity, provider provenance, and bounded outcome metadata. This path
is sequential and forwards the caller's `ExecutionContext` unchanged.

For candidate `p` and the other currently retained points `v_i`, each query
solves

```
sum_i lambda_i*v_i = p,   sum_i lambda_i = 1,   lambda_i >= 0.
```

The zero-objective LP is built independently for each candidate. Its primal
solution is only a candidate witness: residuals, solver status, and numerical
tolerances cannot authorize deletion. A candidate is removed only when the
returned program identity is valid and an exact dyadic check of the represented
binary64 values proves that every weight is nonnegative, the weights sum exactly
to one, and their weighted coordinates reconstruct the candidate exactly.
`RemovalCertificate::evidence` retains floating-point residual diagnostics; it
does not carry the deletion proof. The reducer and every geometry-operation
consumer independently check the exact relation before applying a removal.
If the exact check is unsupported, malformed, or false, the candidate remains.

Candidates that are infeasible, unsupported, stopped, malformed or numerically
uncertain are never removed. A completed result is accepted only when its
program identity matches the query. Unsupported/stopped/uncertain or mismatched
completed results make the reduction `incomplete`; an unsupported request
terminates further calls. A `complete` reduction means all candidates reached
completed, correctly bound LP results, not that retained points are proven to
be precisely the extreme vertices: an LP backend's unestablished infeasibility
claim leaves the candidate retained. `lp_calls` counts calls to the supplied
`LPWorkspace` dependency and `attempts` preserves each candidate's outcome.
With `RegisteredLPQueryRunner`, this includes requests rejected during provider
preflight or stopped before solver creation; count `LPQueryCompleted`,
`LPQueryStopped` and `LPQuerySolverUnsupported` records to distinguish
workspace-backed calls from admission rejections and preflight stops.

The algorithm handles empty and singleton clouds without LP calls, and accepts
zero-dimensional, duplicated and lower-dimensional clouds. It preserves the
convex hull rather than a vertex ordering. A local witness may refer to a point
removed later, so before returning the reducer composes each removal chain to
the final retained cloud and rechecks every removed input point under the same
numerical policy. If composition exceeds tolerance or cannot be checked, the
latest failing support point is restored and the check repeats. This prevents
locally acceptable residuals from accumulating into a final inclusion that
exceeds tolerance. A small-cloud reference test independently rebuilds
membership LPs for every original point against the reduced cloud.

The LP search and its diagnostics use ordinary binary64 arithmetic and the LP
backend's declared policy. Exact verification concerns the finite set of
binary64 values actually returned and stored: each value is interpreted as its
exact dyadic rational. It does not certify the intended real-valued input before
rounding, nor does it establish that an LP backend found every possible
redundancy. Thus retained points may include non-extreme points, but every
removed point is proven to lie in the convex hull of the final retained points
for the represented input cloud. A backend that cannot provide an exact
verifiable witness causes conservative retention, never tolerance-authorized
deletion.

## Ordered hull strategy (OPT-07 bounded adapter)

`make_ordered_hull_reducer_registration()` registers `csl.hull.ordered-membership`;
`reduce_ordered_hull()` provides the direct call. This is a hull-level candidate
ordering strategy. It uses the same LP dependency, exact dyadic deletion check,
original point IDs, removal certificates and final retained-cloud verification
as `reduce_hull()`. The LP pivot rule is unchanged. This adapter does not
implement grouping or recursive QuickHull.

The source anchor is `Scientific Research/QLPHULL.m:7–19` (A29): its active
preprocessing deduplicates points and sorts them by decreasing
`abs(max((p-d)./r))`, where `d` is the bounding-box midpoint and `r` its full
coordinate width. We preserve original IDs and leave duplicates for certified
LP deletion. Equal scores keep original input order. Zero-width coordinates
contribute no score. If a finite input has a width or normalized score that
cannot be represented finitely in binary64, the adapter uses input order.
Neither sorting nor fallback authorizes deletion. The separate Constrained
`QLPHULL.m:6–18` (A33) uses `max(abs((p-d)./r))`, which can rank signed points
differently. The A29 grouping block at lines 44–64 is commented out. A33's
active grouping at lines 50–72 fixes all current C points as Ck, accumulates
nearby Cj points, and uses the constrained `Modified_SM` sibling before
restoring Ck; its final reduction is at lines 73–87. The C++ grouped adapter
below uses the A33 signed max-absolute score, then forms deterministic groups
around the first unassigned point in score order. A point joins a center when
its normalized coordinate distance is at most 0.05 on every nonzero-width
axis. It runs the common certified LP scan over that grouped order. It does not
transcribe the historical trigger or separate `Modified_SM` tableau: grouping
changes query order only, and exact dyadic certificates remain the sole
deletion authority. The archived code is evidence for the ordering/grouping
family, not evidence that the C++ adapter reproduces its historical runtime.

### Contract revision and integration note

`HullReduction` now has an optional `ordered` member. Existing reducers leave
it empty. For this adapter, `processing_order` is the full permutation of
original point IDs before LP calls, `ordered_candidates` equals its length,
`zero_width_coordinates` counts coordinate axes whose finite minimum equals
maximum, and `used_identity_fallback` identifies unsafe normalization. The
existing `lp_calls` counts calls to the supplied `LPWorkspace`; `attempts`
records candidates actually tried, in processing order until a stop. These
counts include no grouping or pivot metric. A successful compilation of the
baseline and ordered reducer tests checks the shared result layout and public
registry adapter. The supported finite input and LP outcome limitations above
apply equally to this strategy; no runtime or speedup is claimed.

### Grouped hull strategy

`make_grouped_hull_reducer_registration()` registers
`csl.hull.grouped-membership`; `reduce_grouped_hull()` is its direct call.
`GroupedReductionMetrics::processing_order` is the full permutation sent to
the shared LP scan. `groups` counts fixed centers and `grouped_candidates`
counts noncenter points assigned to those groups. `zero_width_coordinates`
and `used_identity_fallback` describe ordering arithmetic. `lp_calls` and
`attempts` retain their shared meanings. No LP pivot or recursive QuickHull
counter is reported. Nonfinite, mismatched, or overflow-unsafe input falls
back to input order and is still validated by the shared reducer.
