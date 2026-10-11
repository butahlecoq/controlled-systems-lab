# REVIEW-06: Deep review of scenario workflow, application independence and provenance

GitHub: [#90](https://github.com/butahlecoq/controlled-systems-lab/issues/90).

## Purpose and scope

Inspect scenario loader/templates, thin frontend, domain adapters and versioned experiment artifacts (INP-01..05, MOD-01/09, EXP-02/03/04). Scientific limit: a custom fuel scenario is not restored B04; changing data creates a new identified experiment.

Requirements: REV-03. Test oracles: T-I01, T-I02, T-I03, T-X02, T-B04.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Follow a new user's path from minimal template to custom nonfuel case without C++ edits; review stage indexing, matrices, units, defaults and diagnostic clarity.
- [ ] Switch strategy/backend/run settings and prove mathematical identity remains unchanged; alter problem data and prove identity changes; external referenced data hashes and resolved settings persist.
- [ ] Inspect that CLI/plots/domain adapters do not duplicate scientific algorithms or inject fuel dimensions, control bounds, targets, implicit observation/information or continuous-time discretization.
- [ ] Audit provenance separation of historical reported values, reproduced data and corrected/new variants; unresolved B04 stays non-executable with linked restoration diagnostics.
- [ ] Review schema compatibility and unsupported fields/capabilities; produce concrete usability and architectural fixes without broadening the first-slice scientific scope.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.

## Dependencies

Blocked by [INP-01 #44](https://github.com/butahlecoq/controlled-systems-lab/issues/44), [INP-03 #72](https://github.com/butahlecoq/controlled-systems-lab/issues/72), [INP-02 #75](https://github.com/butahlecoq/controlled-systems-lab/issues/75), [VIZ-01 #87](https://github.com/butahlecoq/controlled-systems-lab/issues/87), [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [TEST-16 #84](https://github.com/butahlecoq/controlled-systems-lab/issues/84).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
