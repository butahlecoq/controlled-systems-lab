# PointOnThePlane finite minimax pilot

The source is pinned to [f4d76c60f4003f50954174e96eafd8e514bd5441](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/PointOnThePlane/PointOnThePlane.py) (blob `2552484d02afca759ff909aca5e5854686a651c4`). Its four physical states are position coordinates `(x1,x2)` followed by velocities `(x3,x4)`, initial state `[0.0, 2.0, 2.0, 1.0]`, and terminal reward `sqrt(x1^2+x2^2)`. The source uses `dt=0.05`, ten explicit-Euler inner steps, a 4-second horizon and action radii `u=[6, 2]`, `v=[2, 4]`. The source repository has no declared license; this report re-expresses equations and does not copy code.

The pilot keeps the source initial state, substep semantics, time-varying coefficients, and action scaling. It adapts the horizon to three stages (0.15 seconds) and the continuous action ellipses to five-point catalogues containing zero and the positive/negative axis endpoints. The minimizer commits to an open-loop control plan before the adversary selects a full disturbance sequence. The finite solver exhausts 125 plans and 125 disturbance histories per plan. It is not an RL reproduction.

The report also computes causal finite-state feedback values on the independently reconstructed finite transition graph. Its backward-winning sets target the open-loop minimax terminal norm; they are not claimed to solve the source continuous-state problem.

## Reproduce

```sh
cmake -S . -B build/env717-point-on-plane -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717-point-on-plane --target csl_env717_point_on_plane --parallel 4
python3 scripts/reports/env717/check_point_on_plane.py \
  build/env717-point-on-plane/csl_env717_point_on_plane \
  --output /tmp/env717-point-on-plane-r1
```

The complete solver record is in `result.json`; independently derived projections, stage states and the selected trajectory are in `figure-data.json`. The one measured solver call is descriptive only; no algorithm comparison or speed claim is made.
