# GEO-02: Compute polyhedral affine images and Minkowski sums

GitHub: [#40](https://github.com/butahlecoq/controlled-systems-lab/issues/40).

## Purpose and scope

Provide exact mathematical affine/sum operations used by forward propagation.

Requirements: ALG-03, ALG-04, MOD-06. Test oracles: T-G01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Check support identities on analytic intervals/squares, singular maps and rectangular control maps.
- [ ] Preserve empty/singleton and coordinate/evidence metadata; reduce generated candidates through the chosen HullReducer.
- [ ] Finite action sets are not silently replaced by their convex hull.

## Dependencies

Blocked by [GEO-01 #16](https://github.com/butahlecoq/controlled-systems-lab/issues/16), [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
