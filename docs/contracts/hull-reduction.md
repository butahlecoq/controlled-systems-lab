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
coordinate width. The C++ adapters preserve original IDs and leave duplicates
for certified LP deletion rather than deduplicating as MATLAB does. Equal
scores keep original input order. Zero-width coordinates contribute no score
in the ordered adapter. If a finite input has a width or normalized score that
cannot be represented finitely in binary64, the adapter uses input order.
Neither sorting nor fallback authorizes deletion. The separate Constrained
`QLPHULL.m:6–18` (A33) uses `max(abs((p-d)./r))`, which can rank signed points
differently. The A29 grouping block at lines 44–64 is commented out. A33's
active grouping at lines 50–72 fixes all current C points as Ck, accumulates
nearby Cj points, and uses the constrained `Modified_SM` sibling before
restoring Ck; its final reduction is at lines 73–87. The C++ grouped adapter
below uses the A33 signed max-absolute score and its ten-consecutive-certified-
redundant trigger. It takes all streamed survivors as fixed Ck, then retests the
trigger point and remaining candidates against Ck plus accumulated nearby
survivors Cj. A previous survivor joins Cj when its Euclidean distance from the
current candidate is at most 0.05 times the smallest coordinate width. The
implementation replaces the archived `Simplex_Hull_mod` and constrained
`Modified_SM` tableaus with the shared LP membership query. A candidate is
filtered only when the exact dyadic verifier returns a removal certificate;
uncertain outcomes are kept for the final LP reduction. Degenerate-width or
unsafe box arithmetic falls back to input-order certified streaming without
the grouping trigger. This preserves the archived control-flow shape without
claiming a faithful numerical tableau transcription or historical runtime.

### Contract revision and integration note

`HullReduction` has optional `ordered` and `grouped` members. Existing reducers
leave them empty. For the ordered adapter, `processing_order` is the full permutation of
original point IDs before LP calls, `ordered_candidates` equals its length,
`zero_width_coordinates` counts coordinate axes whose finite minimum equals
maximum, and `used_identity_fallback` identifies unsafe normalization. The
existing `lp_calls` counts calls to the supplied `LPWorkspace`; `attempts`
records candidates actually tried, in processing order until a stop. These
counts describe no grouping or pivot activity. Grouped metrics and their
meanings are specified below. The grouped adapter uses the same stable IDs,
exact-certificate authority, and supported input/LP outcome limits as the
baseline. No runtime or speedup is claimed.

### Grouped hull strategy

`make_grouped_hull_reducer_registration()` registers
`csl.hull.grouped-membership`; `reduce_grouped_hull()` is its direct call.
`GroupedReductionMetrics::processing_order` is the full permutation examined
by the strategy. `streamed_candidates` counts the initial A33-style scan;
`certified_stream_removals` counts candidates proved redundant there;
`grouping_triggered` and `grouping_passes` report whether the ten-candidate
trigger ran; `grouped_candidates` counts candidates retested in that pass,
including its trigger point; and `nearby_supports` counts unique Cj support
points used by those queries. `zero_width_coordinates` and
`used_identity_fallback` describe ordering arithmetic. `lp_calls` and
`attempts` include streaming, grouped and final-reduction calls. No LP pivot or
recursive QuickHull counter is reported. Nonfinite, mismatched, or unsafe
box arithmetic falls back to input-order streaming and is still validated by
the shared reducer.

### Recursive split-and-merge hull strategy

`make_recursive_hull_reducer_registration(lp_provider)` registers the new
`csl.hull.recursive-split-merge` strategy. The supplied LP registration is the
selected membership backend; the strategy creates its own exclusive LP
workspaces from that registration. Its deterministic partition policy sorts
original point IDs by lexicographic coordinate order, using the original ID
only to break coordinate-identical ties, then splits each node at the midpoint
of that order. The leaf threshold is fixed at 16 points. A node with at most
that many points is reduced with the existing exact-certified reducer.

For any finite point sets `A` and `B`, `conv(A union B) =
conv(conv(A) union conv(B))`. A leaf reduction retains a subset with the same
convex hull as that leaf. Applying the identity at each internal node therefore
preserves the input hull through every merge. The merge candidate set is the
union of the child retained IDs; the existing reducer checks its candidates
with exact dyadic convex-combination certificates, so uncertain outcomes remain
retained. Certificate IDs always refer to the original `PointCloud`.

When the common `ResourcePolicy` allows at least two outer workers, the root's
two child subtrees run concurrently, each with a separately created LP
workspace. Deeper recursion within each subtree is sequential; the merge runs
after both children finish and reuses one now-idle child workspace. With one
outer worker, both subtrees still have exclusive workspaces and run in
deterministic left-then-right order. Each workspace receives the unchanged
caller `ExecutionContext`, preserving the shared resource budget, deadline,
cancellation token and numerical policy. No nested parallel scheduling is
used.

`RecursiveReductionMetrics` records leaf and merge node counts, LP calls
separately for leaves and merges, the maximum number of points present in any
merge candidate set, the number of concurrently executed child subtrees, and
measured root-level parallel overhead. Parallel overhead is the root elapsed
wall time minus the longer of the two measured child-subtree wall times,
clamped to zero; it includes scheduling, synchronization and merge work. These
counters describe one execution and do not imply a general speedup. If child
workspace creation or a recursive child returns diagnostics, the strategy
returns diagnostics without publishing a partial reduction.

#### Complexity, representation costs and evaluation

The guarantee assumes a finite point cloud with equal coordinate dimension,
and an LP provider whose completed responses are correctly bound to each
membership request. Exact dyadic certificates authorize removals; uncertain
responses retain points. For any finite input, the convex-hull identity above
preserves the represented hull at each partition and merge. It does not promise
that every non-extreme point is removed, nor a particular retained vertex
ordering.

For `n` points of dimension `d`, each internal node sorts its IDs. With balanced
midpoint splits and leaf size 16, sorting costs `O(d n log^2 n)` coordinate
comparisons in the worst case across all levels. ID partitioning and merging
cost `O(n log n)` total ID operations, excluding the LP reducer. If every point
survives every merge candidate set, the sum of candidate counts across merge
levels is `O(n log n)`; LP call and solver cost therefore depend on that
data-dependent candidate count and the selected backend, and have no
backend-independent time bound. The reported `peak_merge_points` is the largest
single candidate set, bounded by `n`.

The input cloud uses `O(nd)` coordinate storage. Partition ID vectors and
recursive stacks use `O(n)` additional ID storage at a time, excluding result
records. The reducer retains attempts and certificates from leaves and merges;
in the worst case those records can total `O(n log n)` because a candidate may
be reconsidered at each merge level. Two LP workspaces may be live at once for
root children, plus the retained merge result data. Actual workspace memory is
provider-specific and is not included in the point-count metric.

Evaluation compares support and certificate validity with the independent
baseline reducer on signed, duplicate and affine-degenerate fixtures and input
permutations. Performance evidence is reported separately using fixed clean
Release source and harness commits, raw per-repetition records, environment and
resource provenance, and a measured interval that identifies workspace setup,
recursive work and verification. Any recursive-vs-baseline timing comparison
requires alternating tuned repetitions and a separate limiter profile; small
fixture measurements without that evidence remain descriptive, with no
universal speedup claim.
