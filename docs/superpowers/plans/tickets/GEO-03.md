# GEO-03: Convert H and V descriptions with equality and ray support

GitHub: [#31](https://github.com/butahlecoq/controlled-systems-lab/issues/31).

## Purpose and scope

Register a reviewed H/V conversion adapter that handles the declared set class.

Requirements: ALG-03, ALG-04, ALG-05. Test oracles: T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [set-representations-and-ellipsoidal-toolbox.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/set-representations-and-ellipsoidal-toolbox.md).

## Acceptance criteria

- [ ] Round-trip square, simplex, embedded segment and singleton by independent membership/support checks.
- [ ] Translate empty/unbounded/equality/ray outcomes honestly; a bounded-only adapter rejects unsupported requests.
- [ ] Record conversion identity, time, input/output sizes and numeric evidence; audit A17/A18 lineage without assuming executable equivalence.

## Dependencies

Blocked by [GEO-01 #16](https://github.com/butahlecoq/controlled-systems-lab/issues/16), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
