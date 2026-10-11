# REVIEW-10: Review nonlinear replay adapters and linear-result associations

## Purpose and scope

Review replay implementation and final-artifact associations after code and independent tests exist. Validate simulation assumptions and the boundary between linear optimality and nonlinear evaluation.

Requirements: REV-03, EXP-04, EVD-01, EVD-02. Test oracles: T-REPLAY01, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Record reviewed commits, severity, file/line findings and reproduced timing/identity counterexamples; the implementer cannot self-sign off.
- [ ] Audit plant/input identity, time/hold/integration conventions, objective and unit mappings; preserve historical non-executable limitations.
- [ ] Confirm replay neither mutates primary families nor promotes sampled simulation into nonlinear/global/robust evidence.
- [ ] Check replay workspaces and cost accounting remain independent adapters; linked blocking fixes need independent recheck.

## Dependencies

Blocked by TEST-22, REVIEW-04, REVIEW-07.

Related scientific/architecture issues: [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
