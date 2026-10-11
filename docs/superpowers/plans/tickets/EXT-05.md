# EXT-05: Discretize continuous models through an explicit model adapter

GitHub: [#54](https://github.com/butahlecoq/controlled-systems-lab/issues/54).

## Purpose and scope

Allow later continuous-time input with explicit physical times and input-hold/integration semantics.

Requirements: MOD-02, MOD-09, EVD-02. Test oracles: T-M01, T-V01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Distinguish continuous coefficients from already-discrete transitions in schema and model metadata.
- [ ] Check analytic LTI zero-order-hold examples and reviewed LTV integration references; retain integration/error provenance.
- [ ] Descriptor/singular continuous mass matrices and nonlinear models remain separate capabilities, not one extra optional matrix.

## Dependencies

Blocked by [MODEL-01 #15](https://github.com/butahlecoq/controlled-systems-lab/issues/15), [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
