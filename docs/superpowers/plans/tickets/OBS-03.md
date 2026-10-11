# OBS-03: Instrument mathematical ports and expose substitutions and rejected capabilities

GitHub: [#79](https://github.com/butahlecoq/controlled-systems-lab/issues/79).

## Purpose and scope

Goal: instrument coarse mathematical boundaries using OBS-02 without embedding plotting or solver internals in shared contracts. Requirements ALG-01/02/03/04/05/07, EXP-01 and RUN-04. Sources: modular architecture and native contracts. Cover propagation/intersection, hull or redundancy reduction, conversion, approximation when implemented, LP/convex calls, terminal optimization, predecessor/recovery, family construction and witness queries. A decorator/helper maps registered identity and operation requests/results to spans. This ticket observes existing modules; it does not implement simplex, Zoutendijk, geometry algorithms or new approximations.

Requirements: OBS-01, OBS-02, EXP-07. Test oracles: T-M03, T-G02, T-L02, T-X01, T-OBS03: substitution identity and zero-call rejection spies.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] For a supported analytic solve, report independent time/count/size records for each actually invoked module and backend, including conversions and first/additional witness operations.
- [ ] Changing an implemented LP/convex adapter or representation/operator changes recorded identities without editing the problem or adding representation-specific switches to synthesis. Spy adapters cover future identities in phase 2; actual Zoutendijk substitution is validated after OPT-09 in EXP-02 and REVIEW-08.
- [ ] Conversion and approximation spans retain source/target IDs, operation reference set, requested/applied relation, assumptions and error/inclusion evidence; an unsupported exact request cannot appear as a successful outer conversion.
- [ ] Preflight rejections identify module/backend, missing capability and requested operation before expensive calls. Missing basis diagnostics cause an explicit compatible algorithm selection or rejection, never a silent claim of historical basis reuse.
- [ ] Tests use instrumented spy adapters to prove unsupported combinations never invoke numerical solve, and failure/cancellation span statuses agree with actual result evidence.

## Dependencies

Blocked by [OBS-02 #60](https://github.com/butahlecoq/controlled-systems-lab/issues/60), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14), [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28), [GEO-01 #16](https://github.com/butahlecoq/controlled-systems-lab/issues/16), [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
