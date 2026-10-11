# REVIEW-08: Review optimizer variants, structured sets and approximation scalability

## Purpose and scope

Perform independent standards and specification reviews of the later optimizer/representation adapters, proof assumptions, module seams and measured output costs.

Requirements: ALG-01, ALG-03, ALG-06, ALG-07, REV-01, REV-03. Test oracles: T-G02, T-V02, T-EXP02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Record reviewed commits, file/line findings, severity and reproducible counterexamples; the implementer cannot self-sign off.
- [ ] Confirm LP kernels, hull policies, conversion operators and approximations can change independently; test replacement with actual compatible adapters.
- [ ] Audit hull preservation, active-constraint step bounds, inclusion direction, numerical versus validated evidence and witness realizability.
- [ ] Inspect allocation/materialization costs, workspace ownership and benchmark equivalence; linked blocking fixes are rechecked before closure.
- [ ] Include the geometric QuickHull adapter and its independent orientation/degeneracy tests; keep its geometry strategy distinct from the LP-backed recursive reducer.

## Dependencies

Blocked by TEST-19, TEST-20, EXP-03.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
