# MPC-06 exact tube-policy cost extension

This is a new analytic cost evaluation tied to the exact nilpotent double-integrator tube in the adjacent `mpc06-nilpotent-tube-pilot-v1` report. Exact copies of the prior scenario and result are included in this bundle as `base-scenario.json` and `base-result.json`. It defines a three-stage quadratic cost and evaluates one fixed zero nominal plan with the fixed full-state feedback gain `K=[-1,-2]` under stagewise independent disturbances in `[-1/8,1/8]`.

The nominal surrogate cost is exactly `0`; the exact worst-case actual finite-horizon cost is `3/8`. The maximizing disturbance histories are `(1/8,-1/8,1/8)` and its sign reversal. The exact checker enumerates all eight vertices, checks every resulting state and input bound, and uses convexity of the sum-of-squares objective in the complete disturbance vector to establish the same maximum for the continuous box.

This is a cost certificate for one fixed plan and one fixed ancillary policy. It does not optimize the nominal plan or gain and is not a fixed-plan minimax optimum or globally optimal causal policy result. There is no benchmark timing, no terminal invariant set, and no approximation-family comparison; #99/#100 gate approximation claims. The controller assumes the current full state is observed before each input, with disturbance entering after that input.

All calculations use exact rational arithmetic in Python's standard library. No external solver or optional dependency is used. The plotted path is a maximizing witness inside the exact RPI tube, not an optimal trajectory.

## Reproduce

```sh
python scripts/reports/mpc06/build_tube_objective.py
python scripts/reports/mpc06/check_tube_objective.py
```

The staged report is functional evidence, not a performance measurement. There are no public API, dependency, installation, or release/package changes.
