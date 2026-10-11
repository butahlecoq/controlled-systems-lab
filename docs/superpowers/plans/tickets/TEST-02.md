# TEST-02: Expand affine model and observation contract tests

## Purpose and scope

Test compositional immutable LTI/LTV dynamics, zero-dimensional channels and pre/post-decision observation semantics (MOD-01/02/03/04/09). Limit: model representability does not imply initial nominal strategy support.

Requirements: REV-02. Test oracles: T-M01, T-M02, T-M03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Compare compact constant coefficients with explicit stage providers using fixed independent trajectories; x0=2, A=3, B=2, a=-1, controls [1,-2] must give states [2,7,16].
- [ ] Reject wrong A/B/E/offset shapes and stage indices; enforce T transitions versus T+1 states and document the selected zero-horizon policy.
- [ ] Keep absent controls/external channels, zero-valued singleton channels and unrestricted channels semantically distinct; no observation never becomes full-state knowledge.
- [ ] Test separate observation channels, partial/full observations, offsets and measurement errors; pre-decision dependence on unavailable current control produces a causal diagnostic.
- [ ] Discrete matrices are used directly even when timestamps are nonunit; continuous-time data are distinguished and rejected by the initial loader/planner.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by MODEL-01, CORE-03.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
