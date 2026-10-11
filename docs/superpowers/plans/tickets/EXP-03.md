# EXP-03: Add later exact-versus-approximate reachability comparison artifacts

GitHub: [#99](https://github.com/butahlecoq/controlled-systems-lab/issues/99).

## Purpose and scope

Goal: extend the completed two-strategy comparison protocol with separately implemented compatible inner/outer approximation methods. Requirements ALG-03/04/06, EXP-01/04/05 and RUN-04. Sources: set-representations-and-ellipsoidal-toolbox.md, modular architecture and baseline readiness notes. Inputs are explicitly related exact/reference and approximate sets plus realizability/inclusion evidence; outputs are quality/performance records and labelled final 2D figures. No new approximation algorithm, ET integration, nonlinear reachability proof or mandatory intermediate viewer is implemented by this ticket.

Requirements: EXP-01, EXP-04, EXP-07. Test oracles: T-G02, T-V02, T-X02, T-APPROX01: analytic inclusion/objective-bound comparison.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [baselines.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/baselines.md), [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [b04-tables.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-tables.md).

## Acceptance criteria

- [ ] Schedule this extension after the first two optimization strategies pass their common family acceptance suite; approximation comparisons cannot replace that first comparison.
- [ ] Every conversion/reduction/approximation declares exact/equivalent/inner/outer/heuristic direction, assumptions, budget and evidence. Smaller volume or finitely sampled support agreement alone cannot establish containment.
- [ ] Where assumptions and evidence justify it, report outer-set objective lower bounds and realizable inner-set upper bounds; distinguish terminal reachability bounds from optimizer-family enclosure and retain controls for achievable witnesses.
- [ ] Compare set quality, inclusion/support error under a stated test protocol, representation size and submodule timing; never demand exact and approximate sets have identical coordinates or call finite ellipsoidal directions an exact family.
- [ ] Requested exact final 2D projections use supported query operators; enclosures and samples remain labelled, with query/export costs separated and analytically known low-dimensional inclusion cases serving as independent oracles.

## Dependencies

Blocked by [EXP-02 #94](https://github.com/butahlecoq/controlled-systems-lab/issues/94), [VIZ-02 #91](https://github.com/butahlecoq/controlled-systems-lab/issues/91), [VIZ-03 #96](https://github.com/butahlecoq/controlled-systems-lab/issues/96), [APP-02 #33](https://github.com/butahlecoq/controlled-systems-lab/issues/33), [APP-03 #42](https://github.com/butahlecoq/controlled-systems-lab/issues/42), [APP-04 #34](https://github.com/butahlecoq/controlled-systems-lab/issues/34), [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
