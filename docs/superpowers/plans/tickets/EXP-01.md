# EXP-01: Present B04 historical tables alongside restoration diagnostics

## Purpose and scope

Goal: add provenance-labelled B04 reported table rows and restoration status to final comparison exports. Requirements EXP-02/03/04 and T-B04. Sources: b04-tables.md, baselines.md, b04-restoration.md, archive-selected-sources.json and b04-historical.json. Inputs are checked source transcriptions and measured artifacts when available; outputs separate historical reported values, evaluations at printed coordinates and independently reproduced results. Canonical model/control recovery is a separate module/ticket, not work to be guessed by this exporter.

Requirements: EXP-01, EXP-04, EXP-07. Test oracles: T-B04, T-I01, T-X02, T-B04-TABLE: reported/computed/reproduced separation.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [baselines.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/baselines.md), [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [b04-tables.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-tables.md).

## Acceptance criteria

- [ ] Historical B04 loading/export reports non-executable restoration diagnostics for missing canonical control bounds, first-action convention and displayed-model/terminal-result inconsistency; provisional [-1,1] belongs only to a separately identified exploratory scenario.
- [ ] Preserve Table 2 policy labels and all reported terminal/objective rows with source/hash/precision metadata; recomputed printed-coordinate costs use separate columns and rounding-aware interpretation.
- [ ] Display the checked stock-invariant contradiction and unrestricted-plane lower bound as restoration evidence, never as a recovered constrained optimum or solver performance target.
- [ ] The reported 30.899 and 0.4 seconds are historical data, not exact unit-test or modern performance thresholds; corrected/exploratory/reproduced scenario IDs cannot overwrite the transcription identity.
- [ ] A B04 export with no executable run remains useful and truthfully marks current measured fields unavailable; later reproduction columns require a canonical executable manifest and explicit source changes.

## Dependencies

Blocked by OBS-05.

Related scientific/architecture issues: [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
