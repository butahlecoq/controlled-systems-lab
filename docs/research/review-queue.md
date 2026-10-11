# Initial scientific review queue

Prepared 2026-10-11 for the public controlled-systems-lab repository. Separate issues keep source restoration, mathematical guarantees and architecture decisions independently reviewable.

| Item | Topic | Evidence / acceptance direction |
|---|---|---|
| Q01 | Restore L04/L13 terminal criteria and table consistency | Resolve printed norm vs displayed state/cost discrepancies; retain published numbers; identify actual simulation objective |
| Q02 | Restore canonical baseline inputs and missing legacy sources | Obtain complete matrices, constraints, error sets, switching conventions and original MATLAB/Pascal/OpenLoopControl files; explain duplicate minimax-adaptive folder |
| Q03 | Audit and replace the minimax worst-case oracle | Archived positive convex-cost example returns zero instead of one; require global maximum/bound under declared assumptions |
| Q04 | Verify approximation inclusion and nonlinear residual validity | L05 volumes differ; clarify exact/inner/outer status and justified model-error bounds |
| Q05 | Review robust feedback information pattern and optimality claims | Separate fixed plans, shrinking-horizon replanning and globally optimized feedback; audit quantifier order |
| Q06 | Reproduce published experiments and define corrected references | Start from B04/B07/B08/B09; report rounding, objective, feasibility, bounds and historical-vs-corrected data separately |
| Q07 | Select implementation stack using compatible workload measurements | Language remains open; evaluate numerical architecture and complexity before language microbenchmarks |

Review conventions are in [CONTRIBUTING](../../CONTRIBUTING.md). GitHub issue links will be recorded here after publication.
