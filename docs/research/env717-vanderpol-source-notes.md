# Van der Pol upstream source notes

Pinned source: [`imm-rl-lab/optimal_control` at `f4d76c60f4003f50954174e96eafd8e514bd5441`](https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441).

## Primary sources and provenance

- [`Environments/VanDerPol/VanDerPol.py`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/VanDerPol/VanDerPol.py), Git blob `4380ec05c9d100d8b4c1cf0b931a111bc5d419db`.
- [`Environments/VanDerPol/VanDerPol.ipynb`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/VanDerPol/VanDerPol.ipynb), Git blob `c1295c110edf68003f93991e531b072af13e5c8f`.
- Root tree at the pinned commit contains no file named as a license (`LICENSE`/`LICENCE`); the tracked tree has no license metadata file. No explicit license grant was found in the root README or these Van der Pol sources. Treat licensing as unspecified pending owner clarification; do not infer a license from GitHub hosting.

## Environment semantics in the Python source

- The three-component state is `[t, x, v]`: `state_dim = 3`; the derivative vector is `[1, v, (1 - x**2) * v - x + u]`. Thus time is included in the state, and the two physical coordinates implement the notebook’s stated Van der Pol equation.
- Defaults are initial state `[0, 1, 0]`, scalar action bounds `[-1, 1]`, terminal time `11`, outer step `dt=0.1`, and `inner_step_n=10`. Each action is clipped, held constant for ten explicit-Euler substeps of size `dt/10`, then the state is returned. `reset()` restores the configured initial-state object.
- After a full outer step, if `t < terminal_time`, `done=False` and reward is `-0.05*u²*dt`. Otherwise `done=True` and reward is `-x²-v²`. Consequently the terminal state cost replaces, rather than adds to, the running control cost for the final outer step. The check is after integration, so a step can cross the horizon and still receive the terminal reward.
- Replaying the source's binary64 time updates (`t += 0.01` ten times per outer step) from zero leaves `t=10.99999999999981` after 110 outer steps, still strictly below 11. The next outer step terminates at approximately `11.099999999999808`, so the finite adaptation follows 111 source steps: 22 in each of the first four macro stages and 23 in the last.
- **Execution defect:** `step()` returns `(state, reward, done, _)`, but `_` is never defined in the module or method. As written, every `step()` raises `NameError` at return, after mutating the state. The four-value return shape is also an older Gym-style API, with no info value actually supplied.
- The notebook is descriptive, not an independent executable specification: its Markdown gives the ODE, interval `[0,11]`, initial physical coordinates `x(0)=1`, `xdot(0)=0`, and objective `||x(11)||² + 0.05∫u²dt`; it shows an empty code cell and no timestep/action discretization. Its table reports a CCEM learning value `-0.82`, but labels the true value unknown.

## Suitability for a bounded finite-action report

**Suitable as a bounded, explicitly discretized report candidate, with caveats.** It is deterministic, scalar-action, bounded, and finite-horizon, so an explicitly chosen finite control grid yields a well-defined finite-action comparison problem. The grid would be a report-level discretization, not an upstream action set. The implementation is not directly runnable because of the undefined `_`, and exact reproduction must also state the integration scheme and terminal-step reward convention above. Keep the report scoped to the pinned dynamics and a clearly documented action grid; do not present the notebook’s `-0.82` as ground truth or as a verified reference result.

## Equation-replay reference variant

The report uses scenario ID `env717-vanderpol-equation-replay-finite-catalogue-v1`. It records these report assumptions separately from upstream facts: controls are restricted to `{-1, 0, 1}`, one control is held for 22 source steps in each of the first four macro stages and 23 in the last to follow the strict binary64 horizon check, and the terminal branch replaces the final nonterminal running penalty. The update and reward equations are re-expressed from the pinned class and notebook; the invalid return expression is not evaluated. These choices affect only the finite-catalogue result and do not establish what a repaired upstream class or continuous-action optimizer would return. The report also records descriptive enumeration timings with raw repetitions; they are not compared against another method.

Direct-execution evidence would require a source revision that supplies a valid return value, plus replay against that exact revision. No author-intent or canonical-model claim is made here. The report leaves the upstream file and notebook unchanged and preserves the discovered defect as a limitation.
