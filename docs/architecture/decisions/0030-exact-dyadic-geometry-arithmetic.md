# ADR 0030: Exact dyadic geometry arithmetic and independent hull oracles

Date: 2026-11-25
Status: Accepted

## Context

Hull reduction, containment checks and 2D convex-hull construction compare
geometric predicates on stored `double` coordinates. Rounded subtraction in an
orientation test can change a sign near degeneracy, and a containment oracle
that reuses the hull algorithm's own arithmetic or control flow can confirm a
shared error. These routines therefore use a small private exact-dyadic layer
over the represented binary64 inputs and keep the independent oracle separate
from the production hull algorithm.

## Decision

- Treat each finite stored `double` as the exact dyadic rational denoted by its
  bits, consistent with ADR 0003. Exact comparisons in this layer decide
  properties of those represented values; they do not validate the producer
  that wrote them or a claim about authored decimal reals.
- Accumulate signed products in `Integer`: 128 limbs of 64 bits with a common
  exponent of `-2148`, giving 8192 bits of magnitude.

  The capacity follows from the binary64 format. A significand has at most 53
  bits. A finite value has exponent at most 971 in this representation and at
  least `-1074`, so one product spans fewer than 4200 positions after scaling
  by `2^-2148`. Even summing `size_t::max` such products adds fewer than 64
  bits. Every insertion and carry is checked; an unrepresentable sum fails
  closed instead of wrapping.
- Multiply two at-most-53-bit significands as four 32-bit partial products.
  The largest intermediate is `(2^32-1)^2 + 2(2^32-1) = 2^64-1`, so a
  `uint64_t` accumulator is sufficient, and four words cover the at-most
  106-bit product.
- Compute the orientation determinant as the six expanded products of
  `(b-a) x (c-a)` rather than as rounded coordinate differences. Six binary64
  products fit in the private accumulator. The exact integer is the shared
  arithmetic primitive; the containment oracle remains independent of
  QuickHull's endpoint, side, farthest-point and recursive choices.
- In 2D convex-hull construction, reuse only this private exact arithmetic.
  The hull algorithm never constructs a membership LP or invokes an LP
  workspace. Equal-area ties keep the first candidate in lexicographic order.
- Treat elimination as a proposal of a binary64 inverse, never as proof. Admit
  a direction matrix only when the exact residual check proves
  nonsingularity: `||I - B A||_infinity < 1` implies that `B A`, and therefore
  the square `A`, is invertible by the Neumann series. Each residual and
  absolute row sum is formed from exact dyadics of the original `A` and the
  candidate `B`; no rounded norm comparison authorizes admission.
- A degenerate triangle has zero exact area. Containment then falls back to
  point and segment coverage, because no open side test is meaningful.

## Consequences

Sign decisions and nonsingularity admission are exact for the represented
binary64 inputs and are independent of pivot growth, working precision, or the
floating-point path that produced a candidate. Resource caps and overflow
paths fail closed. The layer makes no claim about the solver, geometry
producer, or conversion that created the inputs, and it does not turn a finite
sample of containment checks into a proof for arbitrary sets.
