# T-S01 exact analytic synthesis profile

The separately registered `csl.synthesis.ts01-analytic` StrategyPort implements
one deliberately narrow exact profile, `ts01_exact_integrator`. It admits only
a discrete two-step scalar system with known initial state `x0 = 0`, transitions
`x[t+1] = x[t] + u[t]`, independent closed control intervals `u0,u1 in [0,1]`,
unrestricted state coordinates, no temporal or external constraints, and the
quadratic terminal objective

```text
J(x2) = 0.5 * 2 * x2^2 - 2 * x2 + 1 = (x2 - 1)^2.
```

For every feasible control pair, `x2 = u0 + u1`, so `J >= 0`. The value zero is
attained exactly when `u0 + u1 = 1`. Consequently the complete set of canonical
optimal joint histories is

```text
{ (x0,x1,x2,u0,u1) = (0,s,1,s,1-s) : 0 <= s <= 1 }.
```

The relation is stored as a canonical five-dimensional H-polyhedron with exact
integer coefficients and coordinate labels `(x0,x1,x2,u0,u1)`. The public
membership query checks the affine equalities and control sum using exact
dyadic arithmetic for binary64 coordinates. It rejects the feasible but non-optimal histories
`(0,0,0,0,0)` and `(0,1,2,1,1)`. In particular, the admission check does not
replace the requested squared objective with an absolute residual objective,
even though those objectives share minimizers for this example.

Admission is checked against the immutable `ResolvedProblem` at execution and
again by the strategy registration before workspace creation. The profile also
requires the effective request target, representation, assurance, selected
strategy ID/version, canonical coordinate schema, and an empty transformation
lineage. It constructs its relation and proof internally and uses no solver
samples or caller-supplied certificate references. Strategy A, Strategy B, and
the general publisher remain fail-closed for complete families without this
typed capability.

The outer API still labels this result with `Assurance::numerical`; validated
assurance remains unavailable in the shared registry contract. The dedicated
coverage capability is exact for this one profile and cannot be constructed by
clients. Artifact JSON preserves its binding metadata, but decoding creates an
untrusted capability which the publication boundary rejects. A later artifact
slice must provide a reviewed proof replay/exporter contract before serialized
T-S01 results can be republished as complete families.
