# SYN-05: Extract different complete witnesses without changing optimality

## Purpose and scope

Select controls and their consistent trajectories from either family through one query interface.

Requirements: SOL-04, SOL-05, EVD-02. Test oracles: T-S01, T-S03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Record selection directions/seed and requested/returned/distinct counts; duplicates use explicit tolerance.
- [ ] Extract (0,1) and (1,0) for the analytic integrator and keep primary cost zero; singleton results are distinguished from failure to find more.
- [ ] Query termination and memory are independent of solve termination; no uniform random or uniqueness guarantee is invented.

## Dependencies

Blocked by SYN-03, SYN-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
