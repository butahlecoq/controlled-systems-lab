# CORE-02: Build and run a portable C++20 client with test support

GitHub: [#12](https://github.com/butahlecoq/controlled-systems-lab/issues/12).

## Purpose and scope

Deliver a native client and test entry point that builds selected modules without backend-private headers.

Requirements: RUN-01, ALG-07. Test oracles: T-M01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Provide repeatable configure, build, test and install commands; record initial platform support and dependency versions.
- [ ] Run a small backend-neutral client and a literal numeric fixture in CI. Keep generated builds and vendored sources outside tracked scientific artifacts.
- [ ] Document unavailable sanitizers/platform counters rather than treating a missing tool as a passed check.

## Dependencies

Blocked by [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
