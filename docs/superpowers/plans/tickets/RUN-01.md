# RUN-01: Execute isolated workspaces with budgets and cancellation

## Purpose and scope

Share immutable inputs while controlling mutable solver resources and partial results.

Requirements: RUN-02, RUN-03, EVD-02. Test oracles: T-R01, T-R02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Give each worker exclusive workspace/warm-start ownership and a shared outer/BLAS/backend thread budget.
- [ ] Cancellation/deadline and documented allocation limits preserve available incumbents and evidence; noninterruptible-call latency is recorded.
- [ ] Parallel and sequential analytic runs agree within stated tolerance; unsupported enforcement is not claimed as a hard limit.

## Dependencies

Blocked by CORE-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
