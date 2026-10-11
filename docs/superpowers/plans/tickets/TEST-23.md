# TEST-23: Expand batch sweep isolation and provenance tests

## Purpose and scope

Expand independent scenario-sweep tests for job ownership, resource allocation, failures, cancellation and saved provenance. RUN-02 ships minimum tests before this expansion.

Requirements: REV-02, RUN-02, RUN-03, EXP-04. Test oracles: T-R01, T-R02, T-I03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] A barrier-controlled backend detects shared mutable workspaces across jobs; compare sequential/parallel mathematical answers under declared tolerances.
- [ ] One failed or cancelled job cannot corrupt sibling results; whole-batch cancellation preserves each job outcome and genuine partial evidence.
- [ ] Check deterministic job/result association and ordering, scenario/settings hashes, seed and algorithm identity under deliberately reordered completion.
- [ ] Nested native threads and outer jobs obey the declared common resource policy; report admission-only or unsupported enforcement and test without wall-clock deadlines.

## Dependencies

Blocked by RUN-02, OBS-04.

Related scientific/architecture issues: [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
