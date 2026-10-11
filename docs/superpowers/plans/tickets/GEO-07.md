# GEO-07: Add zonotope and constrained-zonotope exact operations

## Purpose and scope

Register generator-based representations and their supported exact operations with dependency-preserving factors.

Requirements: ALG-03, ALG-04, ALG-06, SOL-01. Test oracles: T-G01, T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Affine images and sums preserve shared factor identities; constrained-generator equalities are not erased.
- [ ] Document closure restrictions and explicit equivalent conversions; unsupported intersections do not become ordinary zonotopes by silent approximation.
- [ ] Use boxes, line segments and constrained-factor examples checked by polyhedral reference queries.

## Dependencies

Blocked by GEO-01, CORE-04, OPT-03.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
