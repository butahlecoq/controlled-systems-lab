# MODEL-03: Validate complete problems and strategy assumptions

GitHub: [#28](https://github.com/butahlecoq/controlled-systems-lab/issues/28).

## Purpose and scope

Validate mathematical inputs separately from configured strategy support.

Requirements: MOD-05, MOD-07, MOD-09, ALG-05, INP-03. Test oracles: T-M03, T-I03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [linear-system-contract.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/linear-system-contract.md).

## Acceptance criteria

- [ ] Report shape/index/criterion errors separately from unsupported, infeasible and solver failure.
- [ ] Keep singular/unbounded/lower-dimensional problems representable while an inverse/compact-set strategy declares its restrictions.
- [ ] Bind resolved problem identity to mathematical data and external content, independent of selected backend settings.

## Dependencies

Blocked by [MODEL-02 #20](https://github.com/butahlecoq/controlled-systems-lab/issues/20), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
