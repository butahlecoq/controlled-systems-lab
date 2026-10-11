# SYN-01: Propagate nominal reachable sets with stage constraints

GitHub: [#53](https://github.com/butahlecoq/controlled-systems-lab/issues/53).

## Purpose and scope

Compute the nominal tube for selected exact set operations and preserve recovery information.

Requirements: MOD-02, ALG-03, SOL-01. Test oracles: T-G01, T-S01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Apply (A_t R_t plus B_t U_t plus a_t) intersect X_(t+1) with correct stage order and initial constraints.
- [ ] Check analytic integrators and an LTV sequence independently; cancellation and empty reachable stages have explicit outcomes.
- [ ] Keep selected method/representation and shared factors visible; per-stage marginals are not reported as the complete optimal family.

## Dependencies

Blocked by [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [GEO-04 #41](https://github.com/butahlecoq/controlled-systems-lab/issues/41), [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
