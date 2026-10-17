# Zoutendijk projection adapter: derivation and limits

## Scope

This adapter minimizes the Euclidean distance to a target over a caller-supplied
nonempty polyhedron described by linear row intervals and variable intervals.
It requires a caller-supplied feasible start and checks that start with the
declared binary64 numerical policy. It does not run a feasibility phase, repair
an infeasible point, or claim exact/validated arithmetic.

The source audit in [the algorithm inventory](algorithm-module-inventory.md)
describes A06 `ZODENTEK` as a projection routine using the norm-to-target,
active-constraint direction LP, and feasible step bound. The Pascal archive
itself is not present in this checkout, so this document records a bounded
modern derivation informed by that audit; it does not claim a line-by-line or
runtime-faithful port. The archived line-search details and tolerances are not
reproduced. In particular, this implementation does not inherit the audited
early-exit step-bound behavior.

## Direction LP

At feasible iterate `x`, let `g = x - y` for target `y`. The projection problem
is the smooth convex quadratic `f(x) = 0.5 * ||x-y||_2^2`; `g` is its gradient.
For every row `a_i x` active at an upper endpoint, the feasible direction must
satisfy `a_i d <= 0`; for an active lower endpoint it must satisfy
`a_i d >= 0`. Active variable endpoints contribute the same signed coordinate
constraints. A two-sided equality contributes both.

The adapter solves

```text
minimize    g^T d
subject to  d belongs to the active linearized feasible cone
            ||d||_1 <= 1
```

using `d = p - q`, `p,q >= 0`, and `sum(p+q) <= 1`. This is a bounded LP sent
through the caller's `LPWorkspace`. A completed direction solve must return a
primal point, report the LP optimum, pass the public result contract, and pass
independent primal residual checks. A nonnegative (within policy) directional
derivative is the numerical stationarity stop. For a convex projection
objective over a convex polyhedron, exact first-order stationarity is globally
optimal; the floating implementation reports numerical evidence only.

## Feasible step and objective evidence

For a descent direction, the exact minimizer of the quadratic along the ray is
`alpha_q = -(g^T d)/(d^T d)`. The maximum feasible step is the minimum of
`(upper_i - a_i x)/(a_i d)` for **every** row with a positive derivative and
`(lower_i - a_i x)/(a_i d)` for every row with a negative derivative, with the
same checks for variable bounds. The applied step is the smaller of this bound
and `alpha_q`. Inactive rows whose derivative is zero or points inward do not
terminate the scan. Each accepted iterate is independently rechecked against
the original row and variable intervals.

Success is a separate result alternative carrying `distance = ||x-y||_2`, the
optimized equivalent quadratic `0.5 * distance^2`, directional stationarity
residual and iteration count. A quadratic objective that overflows cannot form
a success result. Cancellation, deadline, resource stop, iteration limit or
numerical failure returns a distinct stopped alternative containing the last
feasible iterate and stop reason; that type carries no optimality claim. No
convergence theorem is inferred from reproducing the Pascal method name or
line-search family.

## Verification

Unit tests compare interval, box, equality-face and singleton cases against
hand-calculated coordinates and the separate HiGHS convex QP adapter. A row
with zero directional derivative precedes a later row with a finite step bound;
the expected projection demonstrates that the latter is still applied. An
already-feasible target returns zero distance, and an infeasible supplied start
is rejected.
