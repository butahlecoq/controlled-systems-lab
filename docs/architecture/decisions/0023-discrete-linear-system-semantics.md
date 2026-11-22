# ADR 0023: Keep discrete dynamics and physical ports explicit

Date: 2026-11-22
Status: Accepted

## Context

A discrete linear system evaluates transitions over an authored time grid and
has declared state, control, and external-input dimensions. Coefficients may be
constant or indexed by transition. Control-domain membership is represented
separately from the system dynamics.

## Decision

- Interpret each discrete transition as
  `x[k+1] = A[k] x[k] + B[k] u[k] + E[k] w[k] + c[k]`. The transition maps
  are applied once per stage; the difference between adjacent time values does
  not scale this discrete update.
- Select indexed coefficients by transition index and require exactly one
  coefficient record per transition. Validate each stage's matrix and offset
  dimensions against the system's declared dimensions.
- Preserve declared control and external-input ports even when their maps are
  zero. A zero map makes the next state independent of that input; it does not
  erase the declared physical input-port dimension.
- Require `step` inputs to have the declared finite vector dimensions. The
  system model validates dimensions and finiteness; membership in a control or
  external-input set belongs to the separate domain object.

## Consequences

Model tests use hand-computed scalar and asymmetric vector transitions across
constant and indexed providers. A nonuniform time grid ensures the discrete
transition is not silently scaled by its interval; distinct stage maps and
offsets expose stage selection and omitted affine terms. Zero-map cases retain
positive-dimensional input ports and reject absent vectors. These checks define
the model boundary and do not assert continuous-time integration semantics.
