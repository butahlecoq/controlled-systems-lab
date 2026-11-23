# ADR 0021: Keep finite-action graph oracles independent

Date: 2026-11-22
Status: Accepted

## Context

The finite-action graph uses continuous predecessor and reachable-set
operations while selecting paths from an authored discrete action catalogue.
Tests must distinguish these continuous operations from the discrete graph's
actual actions and must check objective values independently of the graph's
own ranking implementation.

## Decision

- A point reachable by a continuous control in the convex hull of the action
  catalogue is not necessarily reachable by any authored discrete action. The
  graph must not create a discrete edge from predecessor membership alone. The
  regression target `0.5` lies between actions `0` and `1` but is not in the
  catalogue.
- Check the two-stage viability result by enumerating the authored action
  sequences independently. The stage-1 state constraint fixes the first
  action to `1`; the best feasible history is `(1,0)` with objective `1.5`.
- For the affine-sum reachable-envelope route, each expanded parent performs
  an affine image followed by a Minkowski sum. The fixture checks the resulting
  invocation count along with envelope membership for the selected nodes.
- Preserve a positive edge cost when its ordinary coefficient division
  underflows. The numerical regression independently evaluates the input
  `denorm_min * (1 / 1e-150)^2 / 2` and expects approximately
  `2.4703282292062326e-24`, even though the selected graph path has zero total
  cost.

## Consequences

Continuous relaxations can filter or bound discrete graph transitions, but
they do not replace the action catalogue. Graph tests keep independent
enumeration, operation counts, and input-level arithmetic oracles next to the
selected path assertions.
