# REVIEW-01: Deep review of core composition, native contracts and ownership

## Purpose and scope

Inspect implemented C++20 foundations/model/problem/public ports for generality and module depth (MOD-01..09, ALG-07, RUN-01/02). Review architectural/code behavior, not document-only proposals. Scientific limit: no claim of support for future problem classes without implementation/capability evidence.

Requirements: REV-03. Test oracles: T-N01 (proposed), T-M01, T-M02, T-M03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Map actual dependency/include graphs: model/problem types cannot depend on solvers, fuel physics or plots; backend containers stay private; observations/time/information are separate.
- [ ] Perform a substitution exercise with a nonfuel affine scenario and a second test backend/provider; identify every required core edit and reject closed switches/hidden assumptions inconsistent with extensibility.
- [ ] Audit value/view lifetime, zero ports, cache ownership, exceptions and expected result failures; compile public-client fixtures and inspect unsupported versus infeasible paths.
- [ ] Trace generic representation scope versus selected solver restrictions (singular A, finite/mixed, temporal, disturbance/continuous time); record missing diagnostics and accidental defaults.
- [ ] Publish a report with explicit generality/modularity/scalability findings and interface recommendations; resolve blocking API changes before dependent module integration.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.

## Dependencies

Blocked by CORE-03, CORE-04, MODEL-01, MODEL-03, TEST-01, TEST-02, TEST-03.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
