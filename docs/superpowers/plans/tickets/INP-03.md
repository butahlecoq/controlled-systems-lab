# INP-03: Publish simple executable templates with known answers

GitHub: [#72](https://github.com/butahlecoq/controlled-systems-lab/issues/72).

## Purpose and scope

Give users a small selectable template catalogue and instructions for their own files.

Requirements: INP-01, INP-02, EXP-03. Test oracles: T-I01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Provide minimal LTI, state-constrained and LTV cases with linear/quadratic/residual-norm examples.
- [ ] Every executable template has complete data and an independent expected answer; editing requires no build step.
- [ ] Keep B04-historical separate and non-executable until canonical restoration; state stages, coordinates/units and criterion weights are explained.

## Dependencies

Blocked by [INP-01 #44](https://github.com/butahlecoq/controlled-systems-lab/issues/44), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
