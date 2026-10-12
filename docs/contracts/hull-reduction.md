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

The zero-objective LP is built independently for each candidate. A candidate is
removed only when the returned primal is finite, its program identity matches,
the generic LP primal checker accepts it, and a fresh nonnegative barycentric
reconstruction passes the requested numerical tolerances. The returned
`RemovalCertificate` binds the program identity, original point IDs, weights,
and numerical residual evidence. It makes no validated-arithmetic claim.

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

These are floating-point, tolerance-based results; they are not exact set
equality or validated global certificates. The reverse inclusion from retained
points to the input cloud is exact because retained points are original input
points. The forward checks establish only the reported per-point numerical
residual policy. Exact boundary classification and validated inclusion are not
promised.

The implementation uses ordinary binary64 feasibility and the LP backend's
declared policy. Conditioning, exact boundary classification and validated
inclusion are not promised. A backend that cannot establish a feasible
combination causes conservative retention, never a false deletion.
