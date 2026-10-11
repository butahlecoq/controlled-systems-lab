# OPT-12: Add optional cross-query LP warm starts

GitHub: [#46](https://github.com/butahlecoq/controlled-systems-lab/issues/46).

## Purpose and scope

Add compatible-backend warm starts as an optional workspace optimization. The archival basis-reuse method reuses classifications within one completed solve; it does not establish this new cross-query feature.

Requirements: ALG-01, ALG-02, RUN-02. Test oracles: T-L01, T-L02, T-R01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Define basis validity, problem-change compatibility, invalidation and fallback without exposing backend containers.
- [ ] Cold and warm paths give the same independently checked membership/status on changed rows, columns, bounds and degenerate cases; incompatible hints fall back or diagnose.
- [ ] State belongs to one workspace; compare cold/warm setup and solve work with explicit cache state, including a case where reuse costs more.

## Dependencies

Blocked by [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30), [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
