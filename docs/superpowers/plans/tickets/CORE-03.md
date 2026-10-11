# CORE-03: Provide owning numeric data and safe matrix views

GitHub: [#13](https://github.com/butahlecoq/controlled-systems-lab/issues/13).

## Purpose and scope

Allow clients and adapters to share immutable numeric data without exposing an external matrix type.

Requirements: RUN-02, MOD-04. Test oracles: T-M02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Check dense/sparse shape, stride, scalar and owner lifetime at input seams; define zero-sized data behavior.
- [ ] For matrix [[1,2,3],[4,5,6]] and vector [7,11,13], all supported layouts yield [68,161].
- [ ] Retained asynchronous views preserve ownership; workers do not mutate shared input values.

## Dependencies

Blocked by [CORE-02 #12](https://github.com/butahlecoq/controlled-systems-lab/issues/12).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
