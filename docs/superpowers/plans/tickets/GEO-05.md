# GEO-05: Project joint polyhedra and compute nominal predecessors

## Purpose and scope

Compute existential preimages/projections with explicit coordinate maps and no global invertibility restriction.

Requirements: ALG-03, ALG-05, MOD-05, SOL-01. Test oracles: T-G01, T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Implement {x in X: exists u in U, Ax+Bu+a in S}; test singular A, unreachable target and analytic integrator cases.
- [ ] An inverse-based fast adapter may require nonsingular A, but a general projection route remains a separate capability.
- [ ] Projection can remain lazy until a supported query requests materialization; preserve equality/ray and evidence semantics.

## Dependencies

Blocked by GEO-03, GEO-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
