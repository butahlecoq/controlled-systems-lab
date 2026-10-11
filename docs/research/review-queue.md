# Initial scientific review queue

Prepared 2026-10-11 for the public controlled-systems-lab repository. Separate issues keep source restoration, mathematical guarantees and architecture decisions independently reviewable.

| Item | Topic | Evidence / acceptance direction |
|---|---|---|
| [Q01](https://github.com/butahlecoq/controlled-systems-lab/issues/1) | Restore L04/L13 terminal criteria and table consistency | Resolve printed norm vs displayed state/cost discrepancies; retain published numbers; identify actual simulation objective |
| [Q02](https://github.com/butahlecoq/controlled-systems-lab/issues/2) | Restore canonical baseline inputs and missing legacy sources | Obtain complete matrices, constraints, error sets, switching conventions and original MATLAB/Pascal/OpenLoopControl files; explain duplicate minimax-adaptive folder |
| [Q03](https://github.com/butahlecoq/controlled-systems-lab/issues/3) | Audit and replace the minimax worst-case oracle | Archived positive convex-cost example returns zero instead of one; require global maximum/bound under declared assumptions |
| [Q04](https://github.com/butahlecoq/controlled-systems-lab/issues/4) | Verify approximation inclusion and nonlinear residual validity | [Reviewed proof report](reachability-proof-audit.md): affine contracts and conditional error lemma curated; **open**: L05 predicate/code identity, exact references [5]/[6], historical coordinates, certified nonlinear bounds and implementation correspondence |
| [Q05](https://github.com/butahlecoq/controlled-systems-lab/issues/5) | Review robust feedback information pattern and optimality claims | [Reviewed policy report](adaptive-policy-proof-audit.md): fixed/replanning/causal proofs and finite-action counterexample curated; **open**: monograph theorem, observation/surrogate bridge, supported feedback implementation and A08/A09 dependencies |
| [Q06](https://github.com/butahlecoq/controlled-systems-lab/issues/6) | Reproduce published experiments and define corrected references | Start from B04/B07/B08/B09; report rounding, objective, feasibility, bounds and historical-vs-corrected data separately |
| [Q07](https://github.com/butahlecoq/controlled-systems-lab/issues/7) | Review compiled core architecture and backend boundaries before benchmarking | C++20/CMake working proposal; ownership, numerical integration and Python references; benchmarks validate contracts |
| [Q08](https://github.com/butahlecoq/controlled-systems-lab/issues/8) | Specify replaceable mathematical algorithms and complete optimal families | Joint state/control relation, independent solver/operator/conversion/approximation ports, phase-I diagnostics, ellipsoidal references |
| [Q09](https://github.com/butahlecoq/controlled-systems-lab/issues/9) | Audit temporal coupling and legacy compatibility | [Reviewed source audit](temporal-lift-source-audit.md): both-direction history proof, source assumptions, penalty distinction, capability/legacy limits and unchanged first-manifest evidence; closure follows final acceptance review, while EXT-03 implementation is separate |

Review conventions are in [CONTRIBUTING](../../CONTRIBUTING.md). All nine review items are published as linked GitHub issues. Architecture is a primary discussion topic; the first output represents optimal families only.
