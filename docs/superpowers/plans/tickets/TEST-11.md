# TEST-11: Expand terminal minimizer-set construction tests

GitHub: [#69](https://github.com/butahlecoq/controlled-systems-lab/issues/69).

## Purpose and scope

Test entire supported terminal minimizer sets and attainment/capability outcomes (OPT-01/02, SOL-02/03). Limit: unsupported nonpolyhedral minimizer relations are rejected; no numerical uniqueness/completeness claim comes from one optimizer.

Requirements: REV-02. Test oracles: T-S02, T-S03, T-C01, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] On [0,1]^2, linear cost x gives the whole edge x=0; constant cost gives the whole square, not a selected vertex.
- [ ] On [0,2]^2, minimize (x+y-1)^2: the minimizer set is the segment x+y=1 with endpoints (0,1),(1,0); test rank-deficient quadratic/residual construction or explicit unsupported completeness.
- [ ] A strictly convex terminal objective with an analytically unique minimizer is distinguished from unique control history; empty terminal reachability is infeasible.
- [ ] Exercise finite attained, unbounded and undetermined/unsupported attainment results with analytic cases or status contract stubs; do not invent an unattained example in a closed bounded polyhedral slice.
- [ ] Objective tolerances and solver bounds remain separate from exact level-set definitions; a relaxed sublevel is labeled a relaxation.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
