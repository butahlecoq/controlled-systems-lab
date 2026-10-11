# SYN-06: Verify trajectories and evidence independently

## Purpose and scope

Recompute original problem residuals and verify evidence bindings without trusting the synthesis result flag.

Requirements: EVD-01, EVD-02, EVD-03. Test oracles: T-V01, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Detect injected wrong transition, bound violation and objective mismatch with named residuals/tolerances.
- [ ] Keep feasibility, optimality, family completeness and validated claims separate; reject evidence for a different problem identity.
- [ ] Retain backend bound provenance and unsupported-verification results without certifying family completeness from sampled witnesses.

## Dependencies

Blocked by MODEL-03, OPT-01.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
