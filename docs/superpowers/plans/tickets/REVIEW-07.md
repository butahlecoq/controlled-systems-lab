# REVIEW-07: Deep review of fuel projections, timing tables and comparison validity

## Purpose and scope

Inspect mandatory projection visualizations and detailed submodule timing observability for the first two-strategy comparison (EXP-01/04/05 plus new observability requirements). This supersedes earlier summary-only scope for these deliverables. Scientific limit: a 2D view loses dependencies and cannot establish family completeness or higher-dimensional inclusion.

Requirements: REV-03. Test oracles: T-PLOT01 (proposed), T-TIM01 (proposed), T-X01, T-X02, T-B04.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Independently compare exported 2D geometry with analytic projection fixtures and fuel coordinate metadata; inspect axis units, state pairs, witness/strategy identity, targets and exact/numeric/approximate/sample labels.
- [ ] Visually inspect rendered fuel figures for usable bounds, legible labels and overlays; non-executable B04 is clearly restoration-labelled and no sampled polygon is promoted to exact geometry.
- [ ] Audit detailed timing tables against raw nested/parallel spans; distinguish wall/worker and inclusive/exclusive time, phase call counts, not-applicable phases, cold/warm conditions and export cost.
- [ ] Confirm both strategies use the same scenario, objective conventions, tolerances, output/witness scope and resources; unequal family evidence/capability is explicit rather than presented as a speed win.
- [ ] Review raw versions/hashes, dimensions, representation sizes and memory provenance; measure instrumentation/projection overhead and report actual limits without hard-coded timing thresholds.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.

## Dependencies

Blocked by VIZ-02, VIZ-03, OBS-03, OBS-04, VIZ-01, TEST-17, TEST-18, TEST-16, REVIEW-03, REVIEW-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
