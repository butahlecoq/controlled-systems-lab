# ADR 0025: Keep projection and predecessor oracles independent

Date: 2026-11-22
Status: Accepted

## Context

Polyhedral projection and nominal predecessor code can produce plausible
outputs for the wrong reason: reusing production elimination in a test oracle
can confirm the same error, and a finite collection of samples alone cannot
establish a projection. Contract fixtures therefore use independently derived
inequalities, equalities, parameterizations, and explicit existential
witnesses to check membership and boundary behavior.

## Decision

- Check output membership by directly evaluating the returned H rows and
  equalities. This helper answers whether a supplied point belongs to the
  output; it does not compute the expected projection or call production
  elimination helpers.
- For nominal predecessors, separately check initial-state membership, control
  membership, and successor-target membership for explicit existential
  controls. Include interval clipping by the initial state set, singular state
  maps with a free coordinate, zero-control systems, and impossible targets.
- For H projection, retain requested coordinate order and verify surviving
  equalities as well as projected inequalities. Use rational fixtures with
  known intervals, slices, triangles, and unbounded outputs. For the slice of
  the unit square, each output inequality must be exactly one of the normalized
  endpoints `-x <= 0` or `x <= 1`; duplicates are allowed. For the triangle,
  those endpoints are also required, while zero-row tautologies `0 <= b` with
  `b >= 0` are allowed. A zero-row inequality with `b < 0` witnesses an empty
  set.
- Do not infer a finite V representation for an unbounded affine preimage. A
  V result without rays cannot represent a line unbounded in both directions.

## Literal derivations

For the integrator predecessor `x_next = x + u + 1`, with `u in [-1,1]` and
target `[2,3]`, an existential control exists exactly for `x in [0,3]`.
Intersecting with the authored initial set `X=[-5,2.5]` gives `[0,2.5]`.

For `x_next=(x0+u,0)`, target `{(2,0)}`, and `u in [-1,1]`, the condition
`u=2-x0` gives `1 <= x0 <= 3`; the initial `x1` coordinate is unconstrained.
With no control, `x_next=(2*x0,x1)` and target condition `x0_next=4` give
predecessor `x0=2` with arbitrary `x1`.

For H projection, `z=2x`, `x+y=3`, and `0<=y<=1` imply
`2<=x<=3` and `4<=z<=6`. Projecting ordered coordinates `[z,x]` must retain
`z=2x`. For the unit-square slice `x+y=1`, write `(x,y)=(t,1-t)` with
`0<=t<=1`; its x projection is `[0,1]`. The triangle with vertices `(0,0)`,
`(1,0)`, and `(0,1)` has the same x projection.

For the duplicate-row H projection fixture, `x+y<=5`, `y>=2`, and `x>=-1`
eliminate to `-1<=x<=3`; repeated slack rows must not change those endpoints.
If only `x+y<=1` is constrained and `y` is existentially unrestricted below,
every real x is feasible by choosing y low enough.

Finally, for `f(x,y)=y` and target `{0}`, the affine preimage is the entire
line `{(x,0): x in R}`. Points `(-2,0)`, `(0,0)`, and `(3,0)` illustrate
membership in that line; the test does not evaluate those points or request a
V result. It requests H output and verifies that admission rejects the
unsupported operation before creating a workspace. The line's two-sided
unboundedness explains why a finite vertex list without rays would not be an
equivalent output.

## Consequences

These fixtures establish behavior for the stated rational and binary64 test
inputs. Point-membership samples and numerical row evaluation remain test
oracles under the recorded assumptions; they are not exact-arithmetic
certificates for arbitrary projected sets.
