# BrokenTriangleGame finite minimax and reachability pilot

This finite four-stage adaptation uses the source RL notebook's documented initial state, action catalogues, dynamics, and terminal polygon. It is not an RL training reproduction. The report compares a fixed open-loop plan with an exact observed-state causal Bellman policy under the source signed-distance terminal cost. The backward winning nodes answer a separate robust target-reachability question over the finite forward state graph; no continuous boundary is claimed.

## Findings

- Open-loop minimax terminal signed-distance value: `0.318198051534`.
- Causal Bellman terminal signed-distance value: `0.294241174638`.
- Finite feedback target-winning nodes by stage: `[0, 0, 1, 2, 7]`. The documented initial state is not winning in this four-stage game.
- Forward state catalogue sizes: `[1, 4, 9, 16, 25]`.

## Scope and evidence

The stage map is the source Euler step with `dt=0.4`, controls `u ∈ {-0.25,+0.25}`, disturbances `v ∈ {-1,+1}`, and four decisions. Open-loop plans are exhaustively checked against all 16 disturbance histories. Causal values are computed by the finite state Bellman recursion. Reachability uses the finite forward catalogue and enumerates the listed disturbance vertices; it does not describe continuous-state boundaries or interior disturbance values. One warmup and one timed minimax solve are recorded; the timing is descriptive for this fixture and supports no performance comparison or scalability claim.

Upstream game notebook: <https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/BrokenTriangleGame/BrokenTriangleGame.ipynb> (blob `91771d55f6f868bb31d871cb0ad8a5d2af521c2a`). The separate DCEM notebook is provenance only (blob `2ba6b9d73040caf2c98017ecc7bcee3d41c1be8a`). The upstream repository declares no license in its repository metadata; this bundle contains independently computed result data and does not redistribute notebook contents.
