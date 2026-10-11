# MODEL-02: Represent control domains, constraints and initial information

GitHub: [#20](https://github.com/butahlecoq/controlled-systems-lab/issues/20).

## Purpose and scope

Build problems with explicit stagewise constraints and natural general-model special cases.

Requirements: MOD-04, MOD-06, MOD-07, MOD-08. Test oracles: T-M02, T-M03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [linear-system-contract.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/linear-system-contract.md).

## Acceptance criteria

- [ ] Keep point/set initial information, continuous/finite/mixed domains and external-input semantics distinct; first nominal profile uses a known point.
- [ ] Distinguish universal, empty, singleton and bounded sets. T transitions use T control and T+1 state stages.
- [ ] Retain optional temporal constraints and future hybrid identity without silently relaxing discrete choices or erasing uncertainty quantifiers.

## Dependencies

Blocked by [MODEL-01 #15](https://github.com/butahlecoq/controlled-systems-lab/issues/15), [GEO-01 #16](https://github.com/butahlecoq/controlled-systems-lab/issues/16).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
