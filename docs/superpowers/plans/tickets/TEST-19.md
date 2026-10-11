# TEST-19: Expand historical optimizer and hull-variant differential tests

GitHub: [#57](https://github.com/butahlecoq/controlled-systems-lab/issues/57).

## Purpose and scope

Expand independent tests for phase-I, within-solve basis classification, grouping, recursive reduction, warm starts and Pascal-derived Zoutendijk projection. Each implementation already ships minimum acceptance tests.

Requirements: ALG-01, ALG-02, OPT-02, RUN-02. Test oracles: T-L01, T-L02, T-C01, T-R01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Check barycentric certificates and hull support against the trusted LP baseline for degenerate bases, signed/flat clouds, permutations and pivot ties; basis membership alone is not extreme-point evidence.
- [ ] Check all positive directional constraint derivatives when bounding a Zoutendijk step; include a row with nonpositive derivative before a later finite limiting row.
- [ ] Projection onto [0,1]^2 of (2,-1) is (1,0), distance sqrt(2); include already-feasible points, zero gradient, infeasible constraints and numerical limits.
- [ ] Counters include every child LP call; warm-state isolation and fallback tests compare mathematical answers rather than expected speedups.
- [ ] QuickHull agrees with an independent 2D monotone-chain/orientation oracle on vertical, collinear, repeated, empty-side and rotated fixtures; no slope division assumes nonvertical edges.

## Dependencies

Blocked by [OPT-04 #29](https://github.com/butahlecoq/controlled-systems-lab/issues/29), [OPT-06 #37](https://github.com/butahlecoq/controlled-systems-lab/issues/37), [OPT-07 #38](https://github.com/butahlecoq/controlled-systems-lab/issues/38), [OPT-09 #39](https://github.com/butahlecoq/controlled-systems-lab/issues/39), [OPT-11 #45](https://github.com/butahlecoq/controlled-systems-lab/issues/45), [OPT-12 #46](https://github.com/butahlecoq/controlled-systems-lab/issues/46), [GEO-06 #23](https://github.com/butahlecoq/controlled-systems-lab/issues/23).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
