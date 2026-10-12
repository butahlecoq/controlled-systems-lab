# LP-backed finite hull reduction

`<csl/geometry/hull_reducer.hpp>` and `CSL::hull` provide a baseline reducer for
finite point clouds using any existing `LPWorkspace`. Input point positions are
stable identities. The module does not depend on HiGHS or phase-I basis
diagnostics.

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
uncertain are never removed. Unsupported/stopped/uncertain calls make the
reduction `incomplete`; an unsupported request terminates further calls. A
`complete` reduction means all candidates reached a completed LP result, not
that retained points are proven to be precisely the extreme vertices: an LP
backend's unestablished infeasibility claim leaves the candidate retained.
`lp_calls` counts actual solver invocations and `attempts` preserves each
candidate's returned outcome.

The algorithm handles empty and singleton clouds without LP calls, and accepts
zero-dimensional, duplicated and lower-dimensional clouds. It preserves the
convex hull rather than a vertex ordering: every deletion is witnessed relative
to the other points then retained; chaining these certificates proves the final
retained hull equals the input hull. A small-cloud reference test independently
rebuilds membership LPs for every original point against the reduced cloud.

The implementation uses ordinary binary64 feasibility and the LP backend's
declared policy. Conditioning, exact boundary classification and validated
inclusion are not promised. A backend that cannot establish a feasible
combination causes conservative retention, never a false deletion.
