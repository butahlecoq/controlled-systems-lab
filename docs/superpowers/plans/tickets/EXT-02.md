# EXT-02: Preserve all optimal branches for finite and mixed control domains

## Purpose and scope

Provide separate finite/minimax and compatible mixed-domain strategies with complete tie/branch semantics.

Requirements: MOD-06, SOL-01, SOL-02, EVD-02. Test oracles: T-S02, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Stream finite prefixes or use a selected mixed-integer adapter under explicit capabilities.
- [ ] Retain equal-cost branches and continuous families within them; pruning and DAG merges preserve action identity and history.
- [ ] Exhaustive tiny examples independently check all ties; convex-hull relaxation of discrete actions is labelled explicitly.
- [ ] For finite minimax, minimize over fixed control plans the maximum over all admissible disturbance sequences using EXT-01; never replace the global worst case with local minimization of a negated convex cost.

## Dependencies

Blocked by MODEL-02, SYN-05, SYN-06, EXT-01.

Related scientific/architecture issues: [#3](https://github.com/butahlecoq/controlled-systems-lab/issues/3), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
