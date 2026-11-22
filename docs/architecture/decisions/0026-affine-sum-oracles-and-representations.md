# ADR 0026: Keep affine-sum oracles independent and representation claims explicit

Date: 2026-11-22
Status: Accepted

## Context

Singular maps can produce lower-dimensional sets inside a higher-dimensional
ambient space. A V representation can also contain non-extreme candidate
points, and binary64 accumulation can differ from the exact-real result for
the stored dyadic inputs. Tests and callers need to distinguish these cases
from the represented set's semantics.

## Decision

- Treat absent affine-dimension metadata as unknown. Tests must derive the
  affine rank from returned points when they need that value; they must not
  infer it from the ambient dimension or from a missing claim.
- An affine-sum V representation may retain non-extreme candidates. The
  mathematical result is the represented set; a provider is not required to
  materialize only extreme points. Exact support checks remain the semantic
  oracle for fixtures where their arithmetic is exact.
- Interpret finite stored binary64 inputs as their exact dyadic values when
  stating the mathematical affine image. Separately test the implementation's
  floating-point accumulation behavior: evaluating `1e16 + 1 - 1e16`
  left-to-right in binary64 yields `0`, while the exact sum of those stored
  dyadic inputs is `1`. Error evidence must account for this discrepancy.

## Consequences

These tests give independent oracles for the stated rational fixtures and
explicitly separate set semantics, representation details, and floating-point
evaluation. They do not establish exact arithmetic for general binary64
geometry or require every affine-sum provider to minimize its vertex list.
