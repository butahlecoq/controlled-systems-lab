# DubinsCar finite open-loop pilot

Pinned source: [Environments/DubinsCar/DubinsCar_Terminal.py](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/DubinsCar/DubinsCar_Terminal.py) at `f4d76c60f4003f50954174e96eafd8e514bd5441` (blob `98c7cda22d81248a25e22374e144ce8d605c45c2`). The upstream repository has no declared license. This report re-expresses the equations and does not copy source code.

## Model and adaptation

The recorded state is `(time, x, y, heading)`, initially `(0,0,0,0)`. Each 0.1-second source step uses 20 explicit-Euler updates of `x'=cos(heading)`, `y'=sin(heading)`, and `heading'=u`. The default terminal time is `2*pi`. Because the environment checks termination after each source step, the recorded trajectory ends at 6.3 seconds, after 63 source steps.

The source accepts controls in `[-0.5,1]` at every source step. This pilot divides the 63 steps into three blocks of 21 and holds one control per block. It enumerates the five-point catalogue `[-0.5, -0.125, 0.25, 0.625, 1.0]`, for 125 complete open-loop plans. The objective is the source terminal loss `(x-4)^2 + y^2 + (heading-3*pi/4)^2`.

The selected finite plan is `[-0.5, 0.625, 1.0]` with terminal loss `0.00640125109497`. The result is the exact minimum over the saved finite catalogue after binary64 replay. It is not a claim about the continuous-action problem.

The pinned source also has an `h` method over the three physical coordinates and a `step` method over the four-element state including time. The checked pilot follows the `step` integration and terminal reward. It does not use the alternate one-step `dynamics` helper from `DubinsCar.py`.

## Reproduce

```sh
cmake -S benchmarks/reporting/env717/dubins-car-build -B build/env717-dubins-car \
  -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-dubins-car --config Release --target csl_env717_dubins_car
python3 scripts/reports/env717/check_dubins_car.py \
  build/env717-dubins-car/csl_env717_dubins_car \
  --output reports/algorithm-results/env717-dubins-car-pilot-v1
```

No performance comparison is made. The driver records all 125 candidates, stage states, terminal states, objective values, source identity, and build provenance.
