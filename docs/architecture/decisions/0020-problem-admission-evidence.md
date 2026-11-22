# ADR 0020: Keep problem-admission evidence independent

Date: 2026-11-22
Status: Accepted

## Context

Problem tests cover strategy admission, resolved mathematical identities, and
resolution from shared immutable model data. These checks can pass for the
wrong reason if a fixture performs extra production work during admission, if
an asserted affine-dimension claim is treated as established evidence, or if
the expected digest is derived from the same serialization code under test.

## Decision

- Keep the test's `scalar-residual-upper-screen` strategy fixture deliberately
  narrow: its capability probe requires a 1-by-1 zero-target residual and
  screens `abs(map[0])` against `sqrt(max_double/2)`. It does not inspect
  residual weights or detect underflow, so it does not guarantee that the
  squared coefficient is representable. The probe performs this arithmetic
  screen without allocating a reformulated objective or invoking an
  eigensolver. This describes the fixture contract, not a production strategy
  profile.
- For the fixture's full-dimensional profile, accept affine dimension only
  when the set representation establishes it by definition and its value
  matches the ambient dimension. A supplied or unverified dimension claim is
  insufficient.
- Resolve two authored requests independently even when they share the same
  immutable dynamics object. Their constraints, controls, objectives, and
  numerical policies remain request-specific, while resolution leaves both
  source requests and the shared model unchanged.
- Keep canonical-identity expectations as fixed outputs from an independent
  struct/hashlib reference over literal mathematical fields, not values
  derived from the product's own serializer or digest helper. Include
  padding-boundary and multi-block inputs in content-digest checks.

## Consequences

Admission tests isolate capability decisions from workspace creation and
reformulation. Identity tests can detect coordinated mistakes in serialization
and hashing, and multi-request tests detect mutation or cross-request leakage
through shared model data.
