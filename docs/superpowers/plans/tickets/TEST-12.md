# TEST-12: Expand direct joint-trajectory family tests

GitHub: [#74](https://github.com/butahlecoq/controlled-systems-lab/issues/74).

## Purpose and scope

Test direct sparse feasible-relation assembly and supported optimal-family construction (SOL-01/02/03, EXP-05). Limit: exact symbolic family identities on fixtures do not validate arbitrary floating-point completeness.

Requirements: REV-02. Test oracles: T-S01, T-S02, T-S03, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Use T-S01 with independent relation u0+u1=1, 0<=u<=1 and x1=u0,x2=1: recover (0,1),(1,0),(1/4,3/4), reject (1,1) and (0,0) as primary optima.
- [ ] T-S02 with constant objective preserves every feasible history and multiple terminal states; T-S03 distinguishes a unique terminal minimizer from infinitely many histories.
- [ ] For T=1, A=2, B=3, a=-1, x0=4, the relation is x1=7+3u; independently check stage/block indexing and state/control bounds.
- [ ] Use a stage state constraint that cuts histories and a singular A case supported by direct assembly; expected constraints must be found from neutral relation data.
- [ ] Backend optimizer alone, sampled witnesses and tolerance-sublevel candidates cannot become a complete exact family; termination and mathematical outcome stay distinct.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
