# TEST-10: Expand reachability and nominal predecessor mathematical tests

GitHub: [#65](https://github.com/butahlecoq/controlled-systems-lab/issues/65).

## Purpose and scope

Test exact nominal propagation and predecessor module composition (ALG-03/05, MOD-05, SOL-01). Limit: existential nominal reachability does not establish robust feedback or preserve histories by itself.

Requirements: REV-02. Test oracles: T-G01, T-M03, T-S01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] For x0=0, x+=u, u in [0,1], R1=[0,1], R2=[0,2]; adding X1=[0,1/2] gives R2=[0,3/2], detecting missed stage intersections.
- [ ] Include an affine offset and LTV stage with hand-derived intervals; compact LTI and expanded providers agree.
- [ ] For x+=x+u and target {1}, predecessor under u in [0,1] is [0,1]; validate using explicit one-step witnesses and rejection outside the set.
- [ ] Singular transitions exercise a supported projection predecessor or explicit inverse-only rejection; empty target/admissibility stays empty.
- [ ] Test that reaching a terminal point alone is not treated as a complete trajectory history and that all operation guarantees/assumptions are propagated.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [SYN-01 #53](https://github.com/butahlecoq/controlled-systems-lab/issues/53), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51), [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31), [GEO-04 #41](https://github.com/butahlecoq/controlled-systems-lab/issues/41), [MODEL-01 #15](https://github.com/butahlecoq/controlled-systems-lab/issues/15).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
