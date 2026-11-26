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

- For seeded integer affine images of rational rectangles, construct the
  expected image by enumerating the rectangle corners and applying the
  integer map directly. Do not use production geometry helpers to compute the
  oracle; this reduces the risk of sharing production implementation errors.
- Treat absent affine-dimension metadata as unknown. In the bounded, ray-free
  V-representation fixture, derive affine rank from returned points rather
  than inferring it from ambient dimension or missing metadata. Other
  representations require evidence that accounts for their geometry, such as
  ray directions or H constraints.
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

## Affine-sum implementation decisions (2026-11-26)

- **LP query identity.** Length-prefix each problem, request, and ideal-output
  field when constructing affine-sum hull-membership LP problem IDs so distinct
  concurrent geometry requests cannot alias one another.
- **Certificate error propagation.** Compute each removal certificate's local
  reconstruction residual from the original candidate coordinates. Then
  propagate conservative infinity-norm residual bounds from final retained
  points through the certificate dependency DAG in time and memory linear in
  the certificate edge count; a certificate that depends on another removed
  point is not an independent local claim.
- **Degenerate factor summands.** A zero factor denotes the exact singleton
  `{center}`. A factor-ellipsoid Minkowski sum returns the other summand's
  factor unchanged when one factor is zero, rather than inflating it by an
  arbitrary limiting `beta`.
- **Coordinate labels.** A general affine map does not retain source coordinate
  names in the output. A projection retains the selected source labels.
