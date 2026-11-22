# ADR 0015: Preserve objective arithmetic representability

Date: 2026-11-22
Status: Accepted

## Context

Objective evaluation and residual-norm squaring use binary64 arithmetic. A
finite request can produce an overflow, or a nonzero product can round to zero.
Either result can change the represented objective. An arbitrary small-value
cutoff would also reject valid subnormal coefficients. Quadratic PSD checking
scales a matrix before eigensolving, so that scaling must not erase authored
nonzero entries.

## Decision

- Report nonrepresentable objective arithmetic as `numerical_failure`, distinct
  from malformed input.
- Keep the original residual norm available when its squared reformulation
  fails. Decline the reformulation if it overflows or if a nonzero product in
  `Q`, `q`, or `c` rounds to zero; identify the affected coefficient group in
  the diagnostic.
- Preserve nonzero subnormal products when binary64 can represent them. Do not
  use a blanket magnitude threshold to discard small coefficients.
- If PSD-check scaling erases a nonzero quadratic coefficient, stop numerical
  validation instead of certifying the altered matrix. The policy for negative
  eigenvalues and clipping is recorded in [ADR 0002](0002-native-integrations.md).
- Tests of arithmetic failure assert the specific `Q`, `q`, or `c` diagnostic
  so a later failing coefficient group cannot mask a missing earlier guard.

## Consequences

An unusable square does not replace or invalidate its original norm objective.
Representable subnormal quadratics remain available to callers, while arithmetic
that loses a nonzero coefficient cannot be reported as a usable transformation.
