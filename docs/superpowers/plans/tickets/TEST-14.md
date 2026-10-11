# TEST-14: Expand independent trajectory verification and evidence isolation tests

GitHub: [#58](https://github.com/butahlecoq/controlled-systems-lab/issues/58).

## Purpose and scope

Test numerical verifier, original objective recomputation and evidence binding (EVD-01/02/03). Limit: witness feasibility never certifies global optimality, inclusion or complete optimizer coverage.

Requirements: REV-02. Test oracles: T-V01, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Start with analytic valid witnesses, then inject wrong initial state, one transition, violating control/state constraint, wrong horizon and wrong reported original objective; each named residual identifies the stage/quantity.
- [ ] Use original norm 5 versus squared cost 25 and rectangular residual map to detect accidental verifier reuse of transformed solver objective.
- [ ] Check absolute/relative and coordinate-scale policies near boundaries, nonfinite values and tolerance changes; no NaN bypasses comparisons.
- [ ] Give backend-success, sampled-family, relaxed-family and symbolic-floating-point metadata: the verifier must not promote them to global/complete/validated evidence.
- [ ] Reject problem ID mismatches in witnesses, families, bounds and certificates; independently supplied immutable problem data drive checks.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
