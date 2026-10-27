# UnequalGame finite-action minimax pilot

This is a source-attributed adaptation of the upstream two-player differential game. The source model is `ẋ = u + v`, initial `(t,x)=(0,1)`, terminal time 2 s, `u ∈ [-2,2]`, `v ∈ [-1,1]`, and terminal reward `x²`. The source uses continuous controls. This pilot uses the exact discrete step `x[k+1] = x[k] + 0.05(u[k]+v[k])`, three stages (0.15 s), control catalogue `{-2,0,2}`, and disturbance vertices `{-1,0,1}`. The controller selects one open-loop plan before the adversary selects its full disturbance sequence.

The minimax solver exhausts 27 plans and 27 disturbance sequences per plan. The saved minimax value is `0.7225`; the selected controls are `[-2.0, -2.0, -2.0]`. This is not a reproduction of the original continuous-action RL run.

Upstream source: [f4d76c60f4003f50954174e96eafd8e514bd5441](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/UnequalGame/UnequalGame.py) (blob `a05c7caafa8c36b44f75a8c3e3355677419af6c4`). Measured CSL source commit: `9a6a2ed10fe8d82f8d0d31124cf85f3354572789`. No upstream license is declared; this report re-expresses the equations and does not copy the code.

## Reproduce

Use the recorded CSL source commit in a separate worktree and choose a fresh output directory:

```sh
git worktree add --detach ../csl-env717-unequal-game 9a6a2ed10fe8d82f8d0d31124cf85f3354572789
cd ../csl-env717-unequal-game
cmake -S . -B build/env717-unequal-game -G 'Unix Makefiles' \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717-unequal-game --target csl_env717_unequal_game --parallel 4
python3 scripts/reports/env717/check_unequal_game.py \
  build/env717-unequal-game/csl_env717_unequal_game \
  --output /tmp/env717-unequal-game-rerun
```

The output contains the complete result JSON, figure data, SVG, HTML, capture environment, and checksums. See `result.json` for raw plan records and timing observations. Timings are single-host descriptive values with no comparator or performance winner claim.
