# OBS-04: Record reproducible comparison runs and instrumentation overhead

## Purpose and scope

Goal: make ComparisonRunner produce a versioned final artifact for the two agreed strategies on one immutable scenario. Requirements EXP-01/04/05/06, RUN-04, INP-03/05. Sources: consolidated specification, performance-and-language.md and baselines.md. Inputs are resolved run configurations, common witness requests and verifier output; output preserves per-repetition data, outcome/evidence, timing/resources and environment. Bind frontend/CLI later through the same runner. Exclude hard real-time claims and historical-runtime pass thresholds.

Requirements: OBS-01, OBS-02, EXP-07. Test oracles: T-X01, T-X02, T-I03, T-R01, T-OBS04: instrumentation on/off analytic result comparison.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Store problem/source hashes, code and backend versions, hardware/OS/compiler/build settings, arithmetic/tolerances, seeds, cold/warm and workspace reuse policy, requested/actual workers/library threads, and requested/returned/distinct witness counts.
- [ ] Separate parsing/validation, capability checks, workspace/setup, family construction, first/additional witness queries, independent verification and end-to-end solve latency. Plot/export and optional nonlinear replay have separately bounded phases.
- [ ] Run instrumentation-enabled and disabled repetitions under the same resolved mathematical configuration; report measured overhead and outcome/residual/family-evidence agreement within declared tolerances without asserting universal zero overhead.
- [ ] Persist failed/unsupported/cancelled runs with evidence and available metrics; failed configurations are not silently omitted from comparisons or reported as zero-time successes.
- [ ] A small analytic comparison validates both strategies and round-trips the final artifact; different witness coordinates remain acceptable when independently verified primary quality and family semantics agree.
- [ ] For measured method choices, alternate at least five tuned release repetitions per side, retain median/range and failures, confirm the timed work actually ran, and identify the limiter from a separate profile. Report inconclusive comparisons when evidence is insufficient.

## Dependencies

Blocked by OBS-03, INP-01, SYN-03, SYN-04, SYN-05, SYN-06.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
