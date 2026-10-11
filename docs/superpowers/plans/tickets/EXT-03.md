# EXT-03: Add temporal-constraint strategies and exact memory lifts

GitHub: [#73](https://github.com/butahlecoq/controlled-systems-lab/issues/73).

## Purpose and scope

Support reviewed linear cross-stage constraints through joint relations and specific memory augmentations.

Requirements: MOD-07, SOL-01, ALG-05. Test oracles: T-M03, T-S01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Use #9 temporal-coupling proof and counterexample; define initial memory and original/auxiliary coordinate maps.
- [ ] Test the counterexample that physical-state-only propagation loses coupling, plus both directions of the one-step slew lift.
- [ ] New constrained studies have new scenario IDs; first archival inputs remain unchanged and unsupported robust/geometry combinations are rejected.

## Dependencies

Blocked by [MODEL-02 #20](https://github.com/butahlecoq/controlled-systems-lab/issues/20), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [#9](https://github.com/butahlecoq/controlled-systems-lab/issues/9).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
