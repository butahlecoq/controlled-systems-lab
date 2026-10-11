# REVIEW-04: Deep review of numerical verification and scientific evidence claims

GitHub: [#85](https://github.com/butahlecoq/controlled-systems-lab/issues/85).

## Purpose and scope

Inspect independent verifier, evidence schema, objective transformations and problem binding (EVD-01/02/03). Scientific limit: small residuals, solver success, sample agreement and historical cost agreement cannot certify completeness, global optimality or nonlinear global performance.

Requirements: REV-03. Test oracles: T-V01, T-V02, T-O02, T-R02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Run fault-injected witnesses and trace verifier dataflow to immutable problem inputs; no solver/family feasibility flag substitutes for recalculation.
- [ ] Review original objective weights/units, absolute/relative residual scales, nonfinite handling and numerical conditioning; norm versus squared costs remain explicit.
- [ ] Audit every evidence promotion path for feasibility/optimality/inclusion/completeness/validated arithmetic and mismatched problem IDs; verify bounds reference the exact primary problem.
- [ ] Inspect cancelled/limited/numerical-failure results and relaxed/sample families for honest unknown/partial claims; unsupported validated requests cannot silently become numeric verification.
- [ ] Record claim-by-claim evidence, counterexamples and supported scientific limits; require fixes to overclaims before public result publication.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.

## Dependencies

Blocked by [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [TEST-14 #58](https://github.com/butahlecoq/controlled-systems-lab/issues/58), [TEST-04 #27](https://github.com/butahlecoq/controlled-systems-lab/issues/27).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
