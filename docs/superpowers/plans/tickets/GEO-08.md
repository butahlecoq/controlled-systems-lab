# GEO-08: Provide lazy support queries and controlled materialization

GitHub: [#52](https://github.com/butahlecoq/controlled-systems-lab/issues/52).

## Purpose and scope

Let set callers query support and affine/projection expressions without mandatory full vertex enumeration.

Requirements: ALG-03, ALG-04, RUN-03, RUN-04. Test oracles: T-G01, T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Record expression operands, arithmetic/evidence and immutable ownership; support answers match analytic and polyhedral references.
- [ ] Materialization is an explicit budgeted operation with cancellation and representation-growth reporting.
- [ ] Finite direction samples are labelled as samples/enclosures under their stated construction, not a complete exact set.

## Dependencies

Blocked by [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
