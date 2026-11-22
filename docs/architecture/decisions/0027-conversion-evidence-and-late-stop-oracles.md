# ADR 0027: Keep conversion evidence outward and late-stop behavior observable

Date: 2026-11-22
Status: Accepted

## Context

Bounded H/V conversion runs through numerical geometry and generated LP
providers. Its error evidence must not round inward, provider ownership must
survive the preparation scope, and a cancellation or deadline reached during
provider admission must stop execution before a native workspace is created.
Tests that merely repeat comments about these properties can go stale when
vertex order or local object lifetimes change.

## Decision

- For the one-dimensional interval fixture, verify the published coverage
  bound against the exact stored-dyadic gap. The exact gap is
  `1/3 - 6004799503160661/2^54 = 1/(3*2^54)`. The least outward-rounded
  binary64 value has bit pattern `0x3c75555555555556`; compare the bits so an
  inward rounding or different representation is detected.
- Treat Qhull vertex order as unspecified. Bounded-square conversion checks
  must validate every returned vertex and find expected corners or support
  values without assigning meaning to a particular row.
- For generated LP ownership checks, prepare the conversion pipeline inside a
  scope that owns the registry and registration sources, then run the prepared
  worker after those sources have been destroyed. Delegating capability and
  factory callables must be captured by value; observation state may outlive
  preparation separately.
- Distinguish provider rejection, cancellation, and expired-deadline scenarios
  explicitly. When cancellation or the deadline arrives during generated-LP
  capability admission, the operation must return the corresponding stop
  reason without invoking the native workspace factory or publishing geometry.

## Consequences

These fixtures pin the stated exact interval arithmetic and numerical Qhull /
HiGHS execution paths. They do not establish a general validated-geometry
guarantee or a hard real-time deadline for arbitrary providers.
