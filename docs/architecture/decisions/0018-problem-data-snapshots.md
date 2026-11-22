# ADR 0018: Preserve problem-data semantics in immutable snapshots

Date: 2026-11-22
Status: Accepted

## Context

Control domains, initial information, external inputs, and temporal constraints
carry mathematical distinctions that can disappear if snapshots normalize
them into superficially similar values. These objects also cross ownership
boundaries and are read by later algorithms, so their stage layout, set
semantics, and retained storage must remain explicit.

## Decision

- Preserve elementary set identity, including `EmptySet{0}` versus
  `UniversalSet{0}`, a zero-dimensional singleton versus no finite action, and
  finite catalogue order and duplicates. Do not convexify a finite catalogue
  or merge it with the continuous part of a mixed domain.
- Flatten joint histories with all state-stage coordinates first, followed by
  all control-stage coordinates. Keep stage offsets explicit and reject
  out-of-range stages and incompatible horizon or dimensions.
- Keep a known initial point distinct from a quantified initial set. Observation
  channels describe measurements and do not convert set-valued initial
  information into a known point.
- Keep known external sequences, exogenous Cartesian factors, and adversarial
  inputs distinct. Reusing the same set identity in two exogenous factors does
  not encode correlation between them. A V representation denotes the convex
  hull of its vertices, not a nonconvex finite-choice set. Cross-factor
  restrictions such as a diagonal fixed-parameter relation require a separate
  relational input model; the current exogenous-factor type does not represent
  them.
- Preserve temporal constraint rows and their coordinate blocks when taking a
  snapshot. A snapshot owns immutable retained data independently of mutable
  producer buffers and remains readable after the producer or outer handle is
  destroyed.

## Consequences

Readers can distinguish missing information from an empty or zero-dimensional
set, preserve time-stage ordering, and evaluate temporal rows against the
correct state/control coordinates. Numerical or serialization layers must not
infer correlation, convexification, or known state from object identity,
vertices, or observation data alone.
