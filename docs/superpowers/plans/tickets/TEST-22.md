# TEST-22: Expand independent nonlinear replay and association tests

GitHub: [#97](https://github.com/butahlecoq/controlled-systems-lab/issues/97).

## Purpose and scope

Expand replay adapter and artifact-association tests independently of the linear optimizers. Implementation tickets already ship minimum tests. B04-specific numeric reproduction requires canonical plant/control data; analytic toy plants are available now.

Requirements: REV-02, EVD-01, EVD-02, EXP-04. Test oracles: T-REPLAY01, T-V01, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] For x_next=x+u+u^2, check tied linear controls (0,1) and (0.5,0.5) produce nonlinear terminal states 2 and 1.5; use an independently computed sequence oracle.
- [ ] Inject shifted controls, wrong plant/problem identity, missing hold convention and truncated history; produce named diagnostics rather than silently interpolated replay.
- [ ] Round-trip replay artifacts without changing linear objective/optimality evidence; preserve nonlinear residuals, units, plant versions and integration limits separately.
- [ ] Missing historical parameters leave B04 replay unavailable; no toy-plant result or selected best replay witness becomes a nonlinear global optimum.

## Dependencies

Blocked by [EXP-04 #56](https://github.com/butahlecoq/controlled-systems-lab/issues/56), [VIZ-04 #92](https://github.com/butahlecoq/controlled-systems-lab/issues/92).

Related scientific/architecture issues: [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
