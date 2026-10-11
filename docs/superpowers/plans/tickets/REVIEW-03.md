# REVIEW-03: Rigorous review of both strategies and complete optimal-family semantics

## Purpose and scope

Inspect reachability/backward recovery and direct joint optimization as distinct strategies (SOL-01..05, EXP-05). Scientific limit: theoretical completeness, numerical evidence and archival fidelity are distinct; a returned optimizer or finite sample is insufficient.

Requirements: REV-03. Test oracles: T-S01, T-S02, T-S03, T-X01, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Derive the feasible joint relation and optimum for T-S01/02/03 independently; inspect actual relation/coordinate maps and query witnesses, including rejected cross-stage Cartesian combinations.
- [ ] Trace all terminal minimizers into each family: constant objectives, exposed faces, rank-deficient quadratic/residual cases and unique-terminal/multiple-history cases must preserve supported optima or reject unsupported completeness.
- [ ] Review attainment/infeasible/unbounded/unsupported pathways and any inverse-based assumptions; flag tolerance-relaxed sublevels mislabeled as exact optimizer families.
- [ ] Check backward recovery does not lose feasible intermediate histories and direct optimization performs family construction beyond optimizer return; separately document extensions over archival single-witness algorithms.
- [ ] Compare the same mathematical output scope across strategies; turn missing family cases and unsupported assumptions into explicit fixes/capability limits before first comparison approval.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.

## Dependencies

Blocked by SYN-03, SYN-04, SYN-02, SYN-01, SYN-05, TEST-10, TEST-11, TEST-12, TEST-13.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
