# ADR 0017: Preserve latent factor identity in generator-set operations

Date: 2026-11-22
Status: Accepted

## Context

A constrained generator set represents physical points as `center + G z`,
where the latent factor vector `z` belongs to a polyhedron. Physical points do
not identify their factor vectors uniquely: a noninjective generator map can
send an inadmissible factor tuple to a point that has another admissible
preimage. Tests therefore need distinct oracles for the lifted factor domain
and the physical image.

## Decision

- Treat factor IDs as identities of latent coordinates. An affine image keeps
  those IDs and the factor equalities while transforming the center and
  generator map.
- In a dependent sum, equal factor IDs denote a shared variable. Their
  generator columns are combined, preserving correlation and allowing shared
  contributions to cancel. New IDs create distinct coordinates; equality
  constraints may still couple those coordinates.
- A Minkowski sum denotes independent summands and requires disjoint factor
  IDs. Reject aliases and direct callers to the dependent sum when sharing is
  intended.
- Test lifted membership against the factor polyhedron and physical membership
  against an independently authored H representation. A feasible factor tuple
  witnesses membership of its image. An infeasible tuple alone does not prove
  that the image is outside the set when the generator map is noninjective.

## Consequences

The representation retains correlation information needed for exact set
operations. Generator-operation tests use independent lifted and physical
oracles; the box image test maps `x in [-1,3]`, `y in [-1,5]` through `x+y+4`,
whose corner extrema are 2 and 12. Tuples that satisfy only one summand's
factor constraints are rejected by the dependent sum.
