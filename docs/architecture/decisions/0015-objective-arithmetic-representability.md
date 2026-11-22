# ADR 0015: Preserve objective arithmetic representability

Date: 2026-11-22
Status: Accepted

## Context

Residual-norm squaring forms `Q`, `q`, and `c` through weighted intermediate
products and binary64 arithmetic. A finite request can overflow, or a nonzero
product can round to zero before it reaches a coefficient. Either result can
change the squared objective. An arbitrary small-value cutoff would also
reject valid subnormal coefficients. Quadratic PSD checking scales a matrix
before eigensolving, so that scaling must not erase authored nonzero entries.

## Decision

- When objective evaluation or squaring detects nonfinite arithmetic, report
  `numerical_failure`, distinct from malformed input. Ordinary finite underflow
  while evaluating a point remains part of the numerical evaluation.
- Keep the original residual norm available when its squared reformulation
  fails. During squaring, check both each weight-times-map/target intermediate
  and each product accumulated into `Q`, `q`, or `c`. If both operands are
  nonzero but their product is zero, decline the reformulation and identify the
  affected coefficient group. Nonfinite intermediate and accumulated values
  stop with `numerical_failure`; their diagnostic is not coefficient-specific.
- Preserve nonzero subnormal products when binary64 can represent them. Do not
  use a blanket magnitude threshold to discard small coefficients.
- If PSD-check scaling erases a nonzero quadratic coefficient, stop numerical
  validation instead of certifying the altered matrix. The policy for negative
  eigenvalues and clipping is recorded in [ADR 0002](0002-native-integrations.md).
- Tests of erased products assert the specific `Q`, `q`, or `c` diagnostic so a
  later failing coefficient group cannot mask a missing earlier guard.

## Consequences

An unusable square does not replace or invalidate its original norm objective.
Representable subnormal quadratics remain available to callers, while squaring
that loses a nonzero coefficient cannot be reported as a usable transformation.
