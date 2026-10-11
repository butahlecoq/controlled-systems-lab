# GEO-04: Intersect state sets and remove redundant inequalities

GitHub: [#41](https://github.com/butahlecoq/controlled-systems-lab/issues/41).

## Purpose and scope

Apply state constraints without losing newly created intersection vertices.

Requirements: ALG-03, ALG-04, MOD-02. Test oracles: T-G01, T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Test crossing edges with all original vertices outside the constraint, empty intersections and affine equality rows.
- [ ] Remove a halfspace only after an implication LP establishes supported nonpositive maximum violation.
- [ ] Preserve essential bounding rows, equality conventions and T+1 state indexing.

## Dependencies

Blocked by [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
