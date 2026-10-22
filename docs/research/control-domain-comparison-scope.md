# Control domains and comparison scope

**Status:** owner decision recorded 2026-10-23. This note records modeling scope; it authorizes no numerical run and does not change published results or frozen manifests.

## Preserve the domain of each problem

The control set is part of a problem's definition. It is not a project-wide normalization that may be copied between unrelated models.

- The B04 fuel-management task uses admissible controls `u ∈ [-1,1]`.
- The L05 Lotka–Volterra task uses its separate `u ∈ [-0.3,0.3]` interval. There is no conversion or inferred relationship between the intervals.
- In B06/B07 minimax tasks, controls come from a finite action set and disturbances belong to their own polytopes. Those disturbance sets have no implied relationship to B04's interval.
- The historical B04 manifest remains frozen. Its recorded interval remains a recollection and is not promoted to a canonical historical input by this decision.

The owner recorded this decision in [issue #535](https://github.com/butahlecoq/controlled-systems-lab/issues/535#issuecomment-6352028390). It settles the scope questions in [#4](https://github.com/butahlecoq/controlled-systems-lab/issues/4), [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10), and [#517](https://github.com/butahlecoq/controlled-systems-lab/issues/517) only as they concern these domain relationships. It does not settle their remaining source recovery, reproduction, or model-correction work.

## Comparison program direction

The intended comparisons will cover classic and minimax control problems, open-loop and closed-loop policies, and reachability representations including exact polytopes and approximate zonotopes, ellipsoids, parallelotopes, and boxes. The comparison records and reports must retain each task's own admissible control, disturbance, and state sets. Comparisons must state which problem, policy class, objective, and set representation each result uses.

This is a program direction, not a claim that every combination is implemented, mathematically interchangeable, or currently supported by a strategy. Approximation guarantees and error bounds remain specific to the method, source problem, and operation. A change of representation must not silently change a problem's admissible controls or disturbances.

## Execution and archive boundary

No run is authorized by this scope decision. Do not edit historical B04 manifest values or change published results on its basis. New comparison scenarios must use their own identities and explicitly record their source-backed or owner-decided domains. See the [cross-cutting API decisions](../superpowers/specs/2026-10-12-cross-cutting-api-decisions-proposal.md) and [class-level architecture](../superpowers/specs/2026-10-12-class-level-system-architecture.md) for the comparison record and capability boundaries.
