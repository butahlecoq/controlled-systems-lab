# VIZ-02: Support selectable fuel-state 2D plots with explicit projection guarantees

GitHub: [#91](https://github.com/butahlecoq/controlled-systems-lab/issues/91).

## Purpose and scope

Goal: add a final PlotRequest accepting coordinate pairs, with trajectory-pair views available immediately and mathematical set projections only on explicit request. Requirements EXP-01/06, ALG-03/04/05 and reserved SOL-06 projection capability, refined by the owner's fuel 2D projection request. Sources: set-representation review and B04 restoration. Inputs name state/control relation, stage when applicable, coordinate pair and required guarantee; outputs bind projected data to the same problem, stage and set/family identity. Exclude all-stage intermediate reachable-set viewers and automatic full-dimensional vertex materialization.

Requirements: EXP-08, EXP-06. Test oracles: T-G01, T-G02, T-V02, T-VIZ02: analytic 2D projection and no-query spy oracle.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] The four-state fuel case accepts any distinct in-range state pair, including flow/flow, stock/stock and flow/stock, with correct labels/units; repeated/out-of-range coordinates reject clearly.
- [ ] Without an explicit set-projection query, render only selected trajectory coordinate pairs and terminal samples. Spy operators prove ordinary trajectory export invokes no exact projection or H/V conversion.
- [ ] An explicit final reachable-set or optimal-family projection request calls a compatible registered operator, records query cost and reference identity, and returns unsupported if its required exact/equivalent guarantee cannot be met.
- [ ] Distinguish exact projected geometry under declared arithmetic evidence, inner/outer enclosures, heuristic shapes and finite witness/support samples in plot data and legends; an outer approximation or sampled convex hull is never relabelled exact.
- [ ] Use a hand-derived rectangle and lower-dimensional line projection oracle; test empty/unbounded/unsupported cases according to implemented capabilities, and retain cross-stage dependence claims separately from displayed 2D marginals.

## Dependencies

Blocked by [VIZ-01 #87](https://github.com/butahlecoq/controlled-systems-lab/issues/87), [OBS-03 #79](https://github.com/butahlecoq/controlled-systems-lab/issues/79), [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
