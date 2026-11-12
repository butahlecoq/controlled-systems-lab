# ADR 0005: Numerical membership witnesses for finite-action graph filters

Date: 2026-11-11. Status: accepted for the native finite-action graph under the
delegated #943 implementation decision.

## Context

The graph propagates selected numerical set representations and separately
recomputes each authored discrete action transition. A strict comparison with
the coordinate bounds of a propagated box can reject a child by a few ULPs
even when the selected box membership predicate accepts it under its existing
floating-point tolerance. A strict coordinate-bound test and selected-shape
membership are different predicates, so the first cannot stand in for the
second.

## Decision

- Record the strict coordinate-box result as
  `contained_in_coordinate_outer_box`, including `false` when a child lies just
  outside those bounds.
- Evaluate the selected representation's existing numerical membership
  predicate independently. A successful result is named
  `accepted_by_selected_shape_numerical_membership`; it is not reported as
  literal set containment.
- For the coordinate-scale membership tolerance, record its effective scale,
  value, and rule:
  `max(64*epsilon*global-coordinate-scale, 64*denorm_min)`. The global scale is
  derived from the queried point and coordinate outer bounds. This rule is not
  a caller tolerance and is not a forward-error bound.
- Preserve each representation's own membership method, witness coordinates,
  residual, and predicate behavior. Residual units and acceptance rules differ
  by representation; there is no universal residual-versus-tolerance test.
- Unsupported, inconclusive, non-finite, or outside selected-shape membership
  refuses the edge. No bounding-box proximity fallback is permitted.
- Numerical membership does not replace original discrete transition
  recomputation, stage-set checks, predecessor filtering, or recovery of an
  authored action. Each remains an independent filter before Bellman
  selection. Outer relation metadata does not make numerical membership an
  exact inclusion or safety certificate.

## Alternatives considered

- **Require strict coordinate-box inclusion.** Rejected because it bypasses
  the selected representation's established numerical predicate and can
  reject a child at a floating-point boundary.
- **Expand every shape by a computed roundoff bound.** Rejected because no
  single forward-error bound has been established for all propagation
  providers and representation-specific predicates.
- **Accept any child near the coordinate bounds.** Rejected because proximity
  alone does not establish membership in a selected zonotope, parallelotope,
  or ellipsoid.

## Consequences

Results must distinguish strict coordinate-bound inclusion from numerical
selected-shape acceptance. They must retain the exact predicate metadata and
must not claim validated containment, exact reachability, or a global safety
guarantee from this numerical filter.
