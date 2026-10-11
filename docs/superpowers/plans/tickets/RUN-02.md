# RUN-02: Run independent scenario sweeps within one resource budget

GitHub: [#80](https://github.com/butahlecoq/controlled-systems-lab/issues/80).

## Purpose and scope

Scale independent scenarios/seeds/configurations with bounded output and reproducible provenance.

Requirements: RUN-03, RUN-04, EXP-04. Test oracles: T-R01, T-X02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Do not treat constrained horizon stages as independent jobs; prioritize coarse runs and compatible set queries.
- [ ] Avoid nested oversubscription and copy-heavy immutable payload transfer; record actual workers/backend threads and memory support.
- [ ] Sequential/parallel results retain scenario/configuration IDs, failures and deterministic selection settings.

## Dependencies

Blocked by [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25), [INP-02 #75](https://github.com/butahlecoq/controlled-systems-lab/issues/75).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
