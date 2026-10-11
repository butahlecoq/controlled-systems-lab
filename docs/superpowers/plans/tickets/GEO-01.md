# GEO-01: Represent exact polyhedral and elementary sets

GitHub: [#16](https://github.com/butahlecoq/controlled-systems-lab/issues/16).

## Purpose and scope

Provide immutable H/V set data and empty/singleton/universal cases with explicit evidence.

Requirements: ALG-03, ALG-04, MOD-04, EVD-02. Test oracles: T-G01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Retain ambient and affine dimension, equality rows, vertices/rays where applicable, coordinate labels and representation ID.
- [ ] Keep algebraic equivalence distinct from numerical/validated evidence. Lower-dimensional sets are not rejected by the data model.
- [ ] Clients can query metadata without copying or materializing payloads.

## Dependencies

Blocked by [CORE-03 #13](https://github.com/butahlecoq/controlled-systems-lab/issues/13).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
