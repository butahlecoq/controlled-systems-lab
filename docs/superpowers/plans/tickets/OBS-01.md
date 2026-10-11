# OBS-01: Define versioned module and operation statistics artifacts

GitHub: [#49](https://github.com/butahlecoq/controlled-systems-lab/issues/49).

## Purpose and scope

Goal: extend final-result observability for detailed submodule computation times. Requirements EXP-01/04/06, RUN-04, ALG-01/03/04/05; the owner's updated detailed timing request extends the summary accounting in the consolidated specification. Sources: C++ contracts, modular architecture and performance-and-language.md. Propose RunStatistics, OperationSpan and ModuleIdentity value contracts in artifacts/execution. A span identifies run, parent/task, module/algorithm/backend and pinned version, operation, stage/query, input/output representation and size, requested/applied guarantee, status/evidence, clock metric and duration. No intermediate-set retention, solver iteration dump or interactive trace viewer is required. Contract review must settle schema versioning and bounded collection behavior before producers and exporters implement it.

Requirements: OBS-01, OBS-02, EXP-07. Test oracles: T-X02, T-I03, T-OBS01: statistics schema identity and missing-metric contract.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Round-trip a final result containing nested module/backend spans, strategy identity, selector identity, resource settings and raw backend diagnostics references without any solver-library container in the schema.
- [ ] Record exact/equivalent, inner, outer and heuristic operation relations separately from numerical versus validated evidence; a missing metric is null/unavailable with a reason, never a fabricated zero.
- [ ] Every timing record binds to the immutable problem ID and resolved configuration ID; two backend configurations retain the same mathematical problem identity.
- [ ] Collection limits report dropped-detail counts or aggregate mode without changing the mathematical solve outcome, and final artifacts remain usable without intermediate geometry payloads.
- [ ] Provide a schema example and compatibility rules; review/merge requires artifact-contract and execution owners to agree field meaning and lifetime.

## Dependencies

Blocked by [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11), [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28), [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
