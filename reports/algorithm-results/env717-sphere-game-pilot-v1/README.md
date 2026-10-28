# SphereGame finite-action minimax pilot

Source-attributed finite-game adaptation of the RL differential game. Source reward is `sqrt(y^2+z^2)-4`; the residual-norm minimax value is reduced by 4 for the source reward. The source uses continuous controls over 8 seconds; this pilot uses three stages over 0.3 s and finite catalogues `u={-0.25,0,0.25}`, `v={-0.5,0,0.5}`. It is not an RL reproduction.

The independent checker replays all 27 fixed plans and 27 disturbance sequences per plan. The phase-plane figure shows forward states, a separate causal feedback winning set, and an open-loop worst-case path.

Upstream source: [SphereGame.py](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/SphereGame/SphereGame.py), blob `dd8ff3ce718570f05288dc4d8d343a8784ca2327`. No upstream license is declared; this report re-expresses its equations.
