# EXT-06: Verify claim-specific certificates with validated arithmetic

GitHub: [#55](https://github.com/butahlecoq/controlled-systems-lab/issues/55).

## Purpose and scope

Add a concrete verifier for selected feasibility/inclusion/objective claims rather than a generic proof flag.

Requirements: EVD-02, EVD-03. Test oracles: T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Choose a certificate class and compatible rounding-aware arithmetic; bind assumptions and problem identity.
- [ ] Separate supported claim coverage from family completeness and model-error certification; reject unsupported validated requests.
- [ ] Check exact/rational or interval reference fixtures and adversarial rounding cases; failed or inconclusive certificates are not accepted.

## Dependencies

Blocked by [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [APP-01 #24](https://github.com/butahlecoq/controlled-systems-lab/issues/24).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
