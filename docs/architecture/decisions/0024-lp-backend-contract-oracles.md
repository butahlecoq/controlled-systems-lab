# ADR 0024: Keep LP backend contract oracles independent

Date: 2026-11-22
Status: Accepted

## Context

An LP backend contract must distinguish mathematical outcomes, feasible
primal witnesses, optional objective bounds, and optional bases. A test that
derives expectations through the same production verifier or provider can
agree with a defect in that implementation. Fixtures also need cases that
exercise offsets, equality substitution, infeasibility, unboundedness, scaling,
and non-unique optima.

## Decision

- Author expected LP cases independently from the runner and product
  verification routines. Include the triangle inequality `x + 2y <=
  2(x + y) <= 2`, whose optimum is attained at `(0, 1)`; objective negation
  must include the offset. Include fixed variables under equalities, a
  contradiction with a redundant row, an improving ray, a degenerate optimal
  face, row scaling, and an offset change. The catalogue JSON is independently
  authored evidence; `--dump-catalogue` exports the runner's actual inputs.
- Recompute primal activities, costs, and residuals with small test arithmetic
  over the public LP views. Do not derive those expectations by calling
  `evaluate_primal` or `multiply`. Check candidate points against fixed literal
  witnesses where the optimum is unique; for an optimal face, check membership
  in the face without requiring one endpoint or claiming family enumeration.
- Treat objective-bound inequalities as necessary sanity checks only. Report
  bounds only when the provider supplies its own bound proof. Report a basis
  only when a dedicated oracle verifies it against the original rows.
- Compute dual stationarity and constants independently. For a negative lower
  multiplier, expect a sign residual when that lower endpoint exists; a
  nonzero multiplier on a free variable is invalid input because that bound
  does not exist.

## Consequences

The contract can verify each selected registration against the same literal
outcome and witness cases while keeping provider-specific proof checks
separate. Numerical residual tolerances remain fixture comparisons, not
certified error bounds or evidence of exact arithmetic.
