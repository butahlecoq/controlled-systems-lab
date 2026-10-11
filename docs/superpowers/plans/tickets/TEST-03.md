# TEST-03: Expand problem validation and whole-pipeline capability tests

## Purpose and scope

Test problem composition, reusable models and early capability diagnostics (MOD-05/06/07/08/09, ALG-04/05). Limit: future disturbance/feedback/finite/hybrid/temporal/arithmetic capabilities are representable or rejected; this suite does not implement them.

Requirements: REV-02. Test oracles: T-M03, T-G02, T-I02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Reuse one immutable model with two constraints/objectives and compare against distinct hand-derived feasible regions; run settings cannot mutate problem data.
- [ ] Singular A is accepted by the model; a registered inverse-only strategy returns unsupported with the offending stage while a compatible noninverse path is not rejected merely for singularity.
- [ ] Finite/mixed domains remain distinguishable from continuous convex hulls; empty temporal constraints pass and unsupported nonempty coupling, uncertain initial quantifier, disturbance or feedback requests get specific diagnostics.
- [ ] Inject missing downstream operation, incompatible output guarantee, noncompact vertex-only input and validated-evidence requests; a counting backend confirms validation fails before expensive solve/workspace execution.
- [ ] Empty admissibility means mathematical infeasibility; missing unsupported operator means unsupported; nonfinite or malformed numerical data follow documented validation rather than becoming infeasibility.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by MODEL-03, CORE-04, MODEL-01, GEO-01.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
