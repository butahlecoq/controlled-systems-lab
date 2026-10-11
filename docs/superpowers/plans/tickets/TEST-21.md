# TEST-21: Expand declared extension profiles with independent quantifier oracles

## Purpose and scope

Add profile-specific mathematical tests only for the implemented extension demonstrations. Robust fixed plans, information-based policies, mixed controls and discretization retain separate capability suites; this does not certify a universal hybrid solver.

Requirements: MOD-04, MOD-06, MOD-07, MOD-08, MOD-09, EVD-03. Test oracles: T-M03, T-V02, T-EXT01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Enumerate a tiny finite-action/vertex-disturbance problem independently, preserve all tied optimal branches, and detect a disturbance path that must not be clipped to a state constraint.
- [ ] Compare the approved slew-memory lift to exhaustive short-history feasibility; distinguish initial-set union versus universal feasibility and observation information available before a decision.
- [ ] For the constant scalar continuous system x_dot=2x+u with zero-order hold, compare the discretization with exp(2h) and (exp(2h)-1)/2; record integration and hold assumptions.
- [ ] Tamper with claim-specific certificate/problem IDs and fail verification; unsupported nonlinear/hybrid or evidence profiles diagnose rather than inherit a guarantee.

## Dependencies

Blocked by EXT-01, EXT-02, EXT-03, EXT-04, EXT-05, EXT-06, OPT-10.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
