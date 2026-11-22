# ADR 0015: Preserve objective arithmetic representability

Date: 2026-11-22
Status: Accepted

## Context

Objective evaluation and residual-norm squaring use binary64 arithmetic. A
finite request can produce overflow, or a checked nonzero product can round to
zero. Either can change the represented objective. An arbitrary small-value
cutoff would also reject valid subnormal coefficients. Quadratic PSD checking
scales a matrix before eigensolving, so that scaling must not erase authored
nonzero entries.

## Decision

- Report detected nonfinite objective arithmetic as `numerical_failure`,
  distinct from malformed input.
- Keep the original residual norm available when its squared reformulation
  fails. During coefficient accumulation, if a checked nonzero product rounds
  to zero, decline the reformulation and identify the affected `Q`, `q`, or `c`
  coefficient group.
- Preserve nonzero subnormal products when binary64 can represent them. Do not
  use a blanket magnitude threshold to discard small coefficients.
- If PSD-check scaling erases a nonzero quadratic coefficient, stop numerical
  validation instead of certifying the altered matrix. The policy for negative
  eigenvalues and clipping is recorded in [ADR 0002](0002-native-integrations.md).
- Tests of erased products assert the specific coefficient-group diagnostic
  so a later failing group cannot mask a missing earlier guard.

## Consequences

An unusable square does not replace or invalidate its original norm objective.
These checks do not guarantee that every exact coefficient survives weighted
intermediate arithmetic or finite accumulation. The known weighted-intermediate
case is tracked in [issue #1241](https://github.com/butahlecoq/controlled-systems-lab/issues/1241).
