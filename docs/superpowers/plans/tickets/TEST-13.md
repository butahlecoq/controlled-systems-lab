# TEST-13: Expand backward recovery and distinct witness-selection tests

GitHub: [#77](https://github.com/butahlecoq/controlled-systems-lab/issues/77).

## Purpose and scope

Test reachability/backward-family recovery and complete witness selection (SOL-01/02/04/05, EXP-05). Limit: failure to discover another witness proves no uniqueness, and selected trajectories prove no completeness.

Requirements: REV-02. Test oracles: T-S01, T-S02, T-S03, T-X01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Apply the same analytic T-S01/02/03 oracles to backward recovery; all terminal minimizers are recovered and cross-stage fibers exclude spurious Cartesian combinations.
- [ ] Verify returned T controls and T+1 states independently against full dynamics; include constrained intermediate states and affine offsets.
- [ ] Request multiple witnesses from a segment, a singleton and a nonunique terminal set; check requested/returned/distinct counts and stated coordinate tolerance.
- [ ] Recorded directions/seed reproduce selection semantics; duplicate or exhausted searches have diagnostics and do not mutate the primary family or primary optimum.
- [ ] Run shared strategy contract cases with direct and backward methods and compare the known relation/evidence, not identical arbitrary witness coordinates; flag capability asymmetry.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71), [SYN-01 #53](https://github.com/butahlecoq/controlled-systems-lab/issues/53), [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
