# OBS-05: Export detailed module computation tables and raw performance records

## Purpose and scope

Goal: generate readable final scientific tables from ComparisonArtifact without accessing solver workspaces. Requirements EXP-01/02/04/06 and RUN-04 plus updated owner detailed submodule timings. Inputs are OBS-04 artifacts; outputs are versioned machine-readable raw records and shareable tables in documented text/CSV formats. Rows distinguish strategy, LP/simplex variant, convex optimizer including Zoutendijk if implemented, representation/operator, operation and stage/query aggregation. Exclude mandatory intermediate-computation UI and avoid selecting a language binding or table-library dependency in this ticket.

Requirements: OBS-01, OBS-02, EXP-07. Test oracles: T-X02, T-OBS05: hand-calculated nested/parallel table fixture.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Expose per-module/operation call counts, total and distribution of inclusive wall/work durations, explicitly defined exclusive metrics when available, CPU scope/availability, input/output representation sizes, solver iterations when supplied, and memory scope/availability.
- [ ] Report setup/family/first-query/additional-query/verification/end-to-end/plot-export phases with median and a documented tail statistic across measured repetitions; do not sum overlapping inclusive phases into latency.
- [ ] Place objective in its original convention, residuals, justified gaps, feasibility/optimality/completeness evidence and approximation direction alongside timing so differing outputs cannot appear as identical work.
- [ ] A deterministic fixture with nested parallel spans yields independently hand-calculated aggregates and exports unavailable, unsupported and failed values explicitly; unit labels and precision prevent misleading zeros.
- [ ] Raw per-run data, schema version and provenance accompany the table, allowing another tool to recreate it without a live solve; historical reported numbers use a separate provenance-labelled track.

## Dependencies

Blocked by OBS-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
