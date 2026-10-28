# TimeOptimalSphereGame nominal reachability pilot

The source is pinned to [f4d76c60f4003f50954174e96eafd8e514bd5441](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/TimeOptimalSphereGame/TimeOptimalSphereGame.py) (blob `fd7709a6f8e4196665d36b4ac5d348173599c250`). Its initial state is `(2,-1)`, outer step is `0.1 s`, ten source Euler substeps are used per step, and target is the unit disk. Source dynamics are `x1'=x2+v`, `x2'=u`; source time reward counts the inner substeps until the state enters the disk. The source repository has no declared license; this report re-expresses the equations and does not copy its code.

This pilot fixes the source opponent action at `v=0` and catalogs controller actions `u∈{-1,0,1}`. It runs the CSL finite-feedback table solver over horizons from 1 to 12 stages to find the first horizon whose backward-winning set contains the initial point. The selected finite-state policy's trajectory is replayed through the source update. This is a nominal finite-catalogue reachability result, not the original continuous two-player RL optimum.

## Reproduce

```sh
cmake -S . -B build/env717-time-sphere -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717-time-sphere --target csl_env717_time_sphere --parallel 4
python3 scripts/reports/env717/check_time_sphere.py \
  build/env717-time-sphere/csl_env717_time_sphere \
  --output /tmp/env717-time-sphere-pilot-v1
```

`result.json` stores the complete finite graph, horizon sweep, winning states and selected path. The solver timings are descriptive and make no performance comparison.

`capture.json` records the host processor identity, operating system, compiler, build, thread settings and measured solver-call count. It uses `unavailable` when the host processor cannot be identified.
