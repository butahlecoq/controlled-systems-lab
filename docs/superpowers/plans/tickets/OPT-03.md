# OPT-03: Integrate a reference native LP adapter

GitHub: [#21](https://github.com/butahlecoq/controlled-systems-lab/issues/21).

## Purpose and scope

Run geometry and recovery LPs through the native dependency selected by CORE-01.

Requirements: ALG-01, ALG-05, EVD-02. Test oracles: T-L01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Register the adapter and translate real statuses and residuals. Feasibility/finite optimum/infeasible/unbounded analytic fixtures pass.
- [ ] Reuse compatible native workspaces without sharing mutable solver state between workers.
- [ ] Retain raw diagnostics and version identity; do not fabricate certificates unavailable from the backend.

## Dependencies

Blocked by [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
