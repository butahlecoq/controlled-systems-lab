# TEST-16: Expand scenario-file and comparison-artifact contracts

## Purpose and scope

Test authored inputs, resolved defaults, problem identity and aligned two-strategy exports (INP-01/02/03/04/05, EXP-02/03/04/05/06). Limit: B04 restoration remains separate; historical reported values are not executable oracles.

Requirements: REV-02. Test oracles: T-I01, T-I02, T-I03, T-X01, T-X02, T-B04.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Each executable minimal/LTI/LTV/state-constrained template loads and runs without C++ changes; invalid shapes, stage counts, schema versions, unknown fields and unsupported capability fields get field-specific distinct diagnostics.
- [ ] Changing strategy/resources/selection leaves mathematical scenario identity stable; changing coefficients, initial data, objective or constraints changes it. Resolved defaults and external-file hashes round-trip.
- [ ] Run both strategies on analytic fixtures under the same problem/tolerance/output/witness scope; exports contain original costs, verifier residuals, family evidence, counts and module/resource provenance.
- [ ] Unknown/new evidence fields follow an explicit schema compatibility policy; partial/unsupported runs serialize without fabricating family or cost data.
- [ ] Current B04 manifest remains non-executable with restoration diagnostics; no guessed control bound, fitted matrix or reported 30.899 is inserted as a verified target.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by INP-01, INP-03, OBS-04, OBS-01, SYN-03, SYN-04, SYN-06.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
