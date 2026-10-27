# Fuel reachability layers

This bundle reconstructs the deterministic four-state linear model stated in
`papers/Minimax/Constrained/ReachableSets.m` (source SHA-256
`97906077cc799564c5e38053830bbedeba85f4fd962ed6abec46600ccdefc218`). The
local MATLAB source is not redistributed. The checked-in model input contains
the transcribed matrices, bounds, horizon, target, objective and coordinate
metadata; `plot-data.json` binds that input and the capture script by SHA-256.

The state is `(x1,x2,x3,x4)`: oxidizer flow and working-stock balance, then fuel
flow and working-stock balance. The model uses `x[k+1] = A x[k] + B u[k]`,
`u[k] ∈ [-1,1]`, horizon 3, singleton initial state `(30.5,302,19.66,198)`,
and state bounds `28 ≤ x1 ≤ 32`, `18 ≤ x3 ≤ 21` at each stage. There is no
disturbance. The terminal objective is
`(30-x1)^2 + x2^2 + (20-x3)^2 + x4^2 + (x2-x4)^2`.

For each stage `k`, `Rk` is the forward reachable set from the initial point;
`Gk` is the set of states from which an admissible future control sequence can
reach the selected minimizing terminal point; and `Rk ∩ Gk` is computed in the
full 4D state space before projecting. The black path is one selected minimizing
open-loop trajectory. The control-to-terminal map has rank 2, so there are
multiple minimizing control sequences; this path is not the complete optimal
family. Degenerate 2D projections remain lines or points.

The first two figures are the requested oxidizer `(x1,x2)` and fuel `(x3,x4)`
projections. `(x1,x3)` and `(x2,x4)` are supplemental flow/flow and stock/stock
views. The result is a numerical reconstruction of the cited model, not a
reproduction of the paper's historical figure and not the separate B06/L09
minimax record. The saved B06 artifact remains unchanged.

## Reproduce

From a clean checkout with Python and the pinned reporting dependencies:

```sh
python -m venv build/report-env
build/report-env/bin/pip install -r scripts/reports/requirements.txt
build/report-env/bin/python scripts/reports/fuel_reachability_layers.py capture
build/report-env/bin/python scripts/reports/fuel_reachability_layers.py render
```

`capture` writes stage geometry and provenance to
`reports/algorithm-results/fuel-reachability-layers-v1/plot-data.json`.
`render` consumes that saved record only and writes standalone SVG/PNG figures
and an offline page to `docs/examples/fuel-reachability-layers/`. It does not
run a native solver, geometry provider, benchmark or numerical experiment.

The standalone page and eight figure files are checked against the SHA-256
manifest in this directory.
