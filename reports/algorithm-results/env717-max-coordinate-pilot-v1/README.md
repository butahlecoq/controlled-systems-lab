# MaxCoordinateGame finite-action minimax pilot

Source-attributed finite-game adaptation of the RL oscillator. The source reward is `max(|y|,|z|)`; the report combines four signed linear terminal objectives per fixed plan. The source uses continuous controls and a 4 s horizon; this pilot uses three 0.1 s stages with catalogues `{-1,+1}`. It is not an RL reproduction.

The independent checker directly replays all 100 explicit-Euler substeps per stage, all 8 fixed plans, and all 8 disturbance sequences per plan. The SVG shows the phase plane, forward reachable sets, robust backward-winning intersection, and a worst-case path.

Upstream source: [MaxCoordinateGame.py](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/MaxCoordinateGame/MaxCoordinateGame.py), blob `d509a1457023b14516d2789bd3033dbaa4110017`. No license is declared; this report re-expresses the equations. Timings are descriptive only.
