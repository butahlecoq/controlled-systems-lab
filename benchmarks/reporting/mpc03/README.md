# MPC-03 robust minimax formulation pilot

This bounded two-stage scalar case is a formulation and oracle cross-check for
issue #599. It is a new synthetic case, not a B06/B07/B08 reproduction. The
finite action catalogue is the ordered list `(0, 1, 1)`, so duplicate action
indices remain distinct. Each stage disturbance ranges over the full interval
`[-1/8, +1/8]`. The finite oracle and MILP check the four endpoint products.
This is sufficient for this fixture because every state and safety inequality
is affine in the disturbance vector, and the terminal objective is linear;
the extrema over each disturbance box occur at endpoint products. This
vertex-sufficiency argument is specific to this affine, polyhedral case. The
model is `x[t+1] = x[t] + u[t] + w[t]`, with
`x[0] = 0`; the terminal objective is to minimize the worst `x[2]`, subject to
`-10 <= x[0], x[1] <= 10` and `1.5 <= x[2] <= 10` for every disturbance
history.

The finite-action reference enumerates all nine control-index plans and all
four disturbance histories. Four plans are tied at value `2.25`; five plans
are rejected by robust terminal safety. The extensive-form MILP has one-hot
control selectors shared across all four histories, separate states for each
history, and one epigraph variable for the worst terminal cost. Its MIP
incumbent, best bound and gap are compared with the exhaustive reference. The
continuous relaxation leaves those same one-hot selectors continuous, giving
a lower bound of `2.0`; the finite optimum supplies the feasible upper bound
`2.25`. The interval `[2.0, 2.25]` is a bound comparison, not an equal-problem
speed ranking.

The verified output is saved in
`reports/algorithm-results/mpc03-open-loop-pilot-v1/`, with the raw result,
build provenance, and a standalone English HTML report. The existing report
workflow stages a versioned route, adds it to the archive index and links it
from the examples gallery; the live Pages URL is pending merge and deployment.
The report records numerical outcomes only; it makes no performance claim. Its
HTML and SVG are deterministic renderings of `record.json`; publication checks
both renderings against the saved record before writing the staged route.

Run the non-timed smoke check with an optional Release build configured using
`-DCSL_ENABLE_HIGHS=ON -DCSL_BUILD_MPC03_REPORT=ON`; the target is
`csl_mpc03_robust_minimax_report --smoke`. The build reuses the repository's
source-pinned HiGHS 1.11.0 dependency. This pilot adds no installed API or new
dependency.

The labelled 2D state projection at
`docs/examples/mpc03-open-loop-disturbance-tube.svg` shows all four terminal
history points for the finite upper-bound plan, the convex hull of their
endpoints, the robust terminal safety threshold, and the worst-cost history.
The polygon visits the endpoints in perimeter order, preserves each history's
identity, and represents the full continuous disturbance box through vertex
sufficiency; the hull is a visual projection, not the disturbance set itself.

## B08 displayed-data MIQCP

`scripts/reports/mpc03/b08_miqcp.py` adds an optional PySCIPOpt 6.3.0 / SCIP
10.0 report-only run for the L04 displayed rounded linear B08 fixture. It
builds one shared binary selector per stage/action and one quadratic epigraph
constraint for each of the 256 disturbance histories. The companion
continuous-control model uses `conv(U)=[-0.6,0.6]`; it supplies a numerical
lower bound, not a catalogue-feasible plan. Both formulations use one solver
thread and a 300 s limit. Each is captured once; those elapsed values are not a
performance comparison.

The saved bundle is independently checked by
`docs/research/tools/check_b08_displayed_exact.py`, which enumerates all 625
finite plans and 256 disturbance corners per plan using rational arithmetic.
The solver's returned plan must be among the three exact minimizers, and its
objective must match the exact displayed-data result. The report retains the
historical `67.12` as a separate value: treating the printed decimals as exact
gives norm `67.150601101404892...`. Original unrounded arrays, the nonlinear
plant and the historical generator are unavailable, so this is not a
reproduction claim.

Run the optional solver into a scratch directory so the frozen report is not
overwritten:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install pyscipopt==6.3.0
.venv/bin/python scripts/reports/mpc03/b08_miqcp.py --output-dir /tmp/mpc03-b08-l04-miQCP-v1
```

The B08 report adds a stage-by-stage 2D `(x1,x3)` projection of the four-state
disturbance tube, with the exact displayed-data worst terminal corner and
projected target marked. It shows every corner history for the returned fixed
plan and does not claim a nonlinear or historical trajectory.

PySCIPOpt is optional and isolated to this report driver; no library dependency,
public API, CMake install target or package surface is added. PySCIPOpt is MIT
licensed, while the bundled SCIP version is Apache-2.0 (SCIP >= 8.0.3). The
official PyPI wheels support Linux x86-64, Windows x86-64 and macOS x86-64 /
ARM64. See the [installation guide](https://pyscipopt.readthedocs.io/en/stable/install.html)
and [license details](https://github.com/scipopt/PySCIPOpt).

The initial scalar MILP pilot remains a separate synthetic case. Issue #599
remains open for the remaining comparison-record integration and acceptance
work; neither the pilot nor B08 report alone completes that issue.
