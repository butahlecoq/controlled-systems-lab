# EXP-02: Benchmark module substitutions under common optimal-family outputs

GitHub: [#94](https://github.com/butahlecoq/controlled-systems-lab/issues/94).

## Purpose and scope

Goal: provide reproducible benchmark configurations auditing independent substitution axes, rather than ranking stacks with different mathematics. Requirements ALG-01/02/03/07, EXP-01/04/05 and RUN-04. Sources: modular architecture, performance-and-language.md and baselines.md. Inputs are executable analytic/scaling cases and existing registered implementations; outputs are raw runs and detailed final tables. Compare the two synthesis strategies first. Within a strategy change one LP/simplex variant, supported convex method (including Zoutendijk when separately implemented), exact set representation or equivalent conversion route at a time. New numerical adapters are prerequisites, not implemented here.

Requirements: EXP-01, EXP-04, EXP-07. Test oracles: T-X01, T-X02, T-L01, T-L02, T-C01, T-G02, T-EXP02: one-axis substitution protocol.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [baselines.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/baselines.md), [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [b04-tables.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-tables.md).

## Acceptance criteria

- [ ] Run both agreed strategies on T-S01/02/03 with the same problem/objective/optimal-family scope, tolerances and witness request; independent verification checks analytic optimum, admissibility and family semantics rather than identical witness coordinates.
- [ ] Keep strategy, LP/simplex variant, convex optimization method, set representation, operator/converter and selector as independent configuration fields. Record selected and rejected combinations with assumptions, including basis-diagnostic requirements and convex method differentiability/reformulation support.
- [ ] Where two compatible adapters exist, demonstrate replacement without changing model/objective/frontend contracts; unavailable implementations are explicitly pending and produce no invented timing rows.
- [ ] Sweep dimension/horizon/constraints/representation size with fixed seeds and saved raw repetitions; distinguish cold/warm runs, end-to-end latency and submodule work, and record resource/failure limits.
- [ ] Compare original objective, residuals, completeness/inclusion evidence, output sizes and time/memory together; B04 canonical reproduction activates only after restoration and historical one-witness timings retain different output-scope labels.

## Dependencies

Blocked by [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [OBS-05 #86](https://github.com/butahlecoq/controlled-systems-lab/issues/86), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [OPT-04 #29](https://github.com/butahlecoq/controlled-systems-lab/issues/29), [OPT-06 #37](https://github.com/butahlecoq/controlled-systems-lab/issues/37), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [OPT-09 #39](https://github.com/butahlecoq/controlled-systems-lab/issues/39), [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31), [INP-03 #72](https://github.com/butahlecoq/controlled-systems-lab/issues/72), [TEST-12 #74](https://github.com/butahlecoq/controlled-systems-lab/issues/74), [TEST-13 #77](https://github.com/butahlecoq/controlled-systems-lab/issues/77).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
