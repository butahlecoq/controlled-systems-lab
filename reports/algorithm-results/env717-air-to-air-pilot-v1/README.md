# AirToAirInterception finite minimax pilot

The upstream environment source is pinned to [f4d76c60f4003f50954174e96eafd8e514bd5441](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/AirToAirInterception/AirToAirInterception.py) (blob `9054c9fcd01e49f3dbfd8b8ee8d12e7365e1d9b5`). The measured algorithm source commit is `aad8ab73f81e57464d4a20b4cdd8b04fc8f576d6`. The report independently replays 125 fixed plans against 125 disturbance sequences, and computes a separate causal finite-state feedback value on the exact reachable graph. Both objective values are in `index.html`; full raw outcomes are in `result.json`.

This adapts the upstream 2-second continuous-action task to three 0.05-second stages and finite five-point action catalogues for both players. It is not a reproduction of the upstream RL experiment. The one timing sample is descriptive only and makes no performance claim.

Reproduce from the repository checkout:

```sh
cmake -S . -B build/env717 -DCMAKE_BUILD_TYPE=Release -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717 --config Release --target csl_env717_air_to_air
python3 scripts/reports/env717/check_air_to_air.py build/env717/csl_env717_air_to_air \
  --build-report reports/algorithm-results/env717-air-to-air-pilot-v1
```
