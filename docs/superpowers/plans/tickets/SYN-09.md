# SYN-09: Define objective-sense and unbounded-outcome semantics

GitHub: [#204](https://github.com/butahlecoq/controlled-systems-lab/issues/204).

## Purpose and scope

Make objective direction authoritative across the shared LP, convex, synthesis, and adapter contracts. The current public LP, convex, and synthesis objectives are minimization-only; `unbounded` means unbounded below. A source maximization must be explicitly normalized as `g=-f`, including its offset, before program creation. Define finite bound direction and exact objective/program identity, then specify how adapters normalize statuses, translate bounds, and preserve independent supported evidence when checking contradictions.

This ticket records the owner-approved policy for issue #204. It does not claim a public maximize API or global maximization support for convex objectives. The issue's acceptance checklist remains unchanged and includes caller-visible tests; tests and implementation are tracked separately from this documentation/backlog scope.

## Acceptance criteria

- [ ] Specify whether all resolved objectives are normalized to minimization or whether resolved problems carry an explicit objective sense.
- [ ] Define the direction and subject of finite objective bounds for each sense.
- [ ] Define `unbounded` precisely (unbounded below or above), including how solver adapters normalize statuses.
- [ ] Apply contradiction checks only after the objective direction is authoritative; preserve independently supported bounds when sanitizing a contradictory outcome.
- [ ] Add caller-visible tests for minimization and maximization, including finite lower/upper bounds, supported and unsupported evidence, and unbounded/undetermined outcomes.
- [ ] Update the shared contracts and adapter documentation without weakening fail-closed behavior for ambiguous sense or unsupported evidence.

## Dependencies

No backlog implementation prerequisites. Related issues: [#155](https://github.com/butahlecoq/controlled-systems-lab/issues/155), [#157](https://github.com/butahlecoq/controlled-systems-lab/issues/157), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8), and [#203](https://github.com/butahlecoq/controlled-systems-lab/issues/203).

## Delivery and review

Update the shared LP, convex, core-interface, and affected adapter contracts. Keep the backlog ticket and manifest entry aligned with this acceptance checklist. Review the direction map and evidence identity against current result validation before applying it to implementation or caller-visible tests.
