# Van der Pol finite-action pilot

Scenario: `env717-vanderpol-equation-replay-finite-catalogue-v1` (`equation-replayed finite-action reference; not direct execution of the upstream class`).

Pinned source: [Environments/VanDerPol/VanDerPol.py](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/VanDerPol/VanDerPol.py) at `f4d76c60f4003f50954174e96eafd8e514bd5441` (blob `4380ec05c9d100d8b4c1cf0b931a111bc5d419db`) and [Environments/VanDerPol/VanDerPol.ipynb](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/VanDerPol/VanDerPol.ipynb) (blob `c1295c110edf68003f93991e531b072af13e5c8f`). The upstream repository declares no license. This report re-expresses the equations and does not copy upstream source code. The source note is [env717-vanderpol-source-notes.md](https://github.com/butahlecoq/controlled-systems-lab/blob/2dbe6a1c0e159fa3cfb39e5e1d1d104d32e8963f/docs/research/env717-vanderpol-source-notes.md).

## Model and objective

The state is `(time, position, velocity)`, initially `(0,1,0)`. The update equations are `time'=1`, `position'=velocity`, and `velocity'=(1-position^2)*velocity-position+u`, with ten explicit-Euler steps per 0.1-second source step. Controls are clipped to `[-1,1]`; the terminal time is 11 seconds. The objective minimized here is the negative of the source reward: nonterminal steps contribute `0.05*u^2*dt`, and the terminal step contributes `position^2+velocity^2` instead of another running penalty.

The source `step()` has a defect: it references undefined `_` in its return tuple after mutating the state, so direct execution raises `NameError`. This artifact independently replays the source equations and reward as documented by the pinned Python file and notebook; it is not a direct run of that class.

The notebook lists a CCEM learning value of `-0.82` and says the true value is unknown. That learned value is not used as ground truth or compared to this finite catalogue.

## Finite adaptation

The source control is continuous. The source's strict horizon comparison remains true after 1,100 binary64 additions of 0.01, so it takes 111 source steps to pass 11 seconds. This report uses five macro stages of 22, 22, 22, 22, and 23 source steps, with one constant action per stage from `[-1.0, 0.0, 1.0]`. It enumerates all 243 open-loop plans. The minimum is `0.621296711077` at plan row `203`, controls `[1.0, 0.0, 0.0, 0.0, 1.0]`. This is a finite-catalogue result only, not the continuous-action optimum or a performance comparison.

## Measured enumeration time

The Release driver had 5 warm-ups and 9 measured repetitions. Median 1.270423 ms (range 1.267491–1.286557 ms). Timing covers allocation, propagation, and objective evaluation for all 243 plans, excluding JSON construction and serialization. These descriptive measurements are not a cross-algorithm comparison or speedup claim. No source-mapped profiler was available for this small pilot.

## Reproduce

```sh
cmake -S benchmarks/reporting/env717/vanderpol-build -B build/env717-vanderpol -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-vanderpol --config Release --target csl_env717_vanderpol
python3 scripts/reports/env717/check_vanderpol.py build/env717-vanderpol/csl_env717_vanderpol --repetitions 9 --output reports/algorithm-results/env717-vanderpol-pilot-v1
```

The Python checker independently enumerates and replays every finite plan. The report contains descriptive enumeration timings but makes no algorithm-comparison or speedup claim.
