# TimeOptimalSphereGame finite minimax pilot

Pinned source: `imm-rl-lab/optimal_control` commit `f4d76c60f4003f50954174e96eafd8e514bd5441`, blob `fd7709a6f8e4196665d36b4ac5d348173599c250`. The upstream repository declares no license; this report contains re-expressed equations and parameters only.

The source state is `[x1 position, x2 velocity]`, initially `(2,-1)`, with inner-Euler dynamics `x1 += 0.01*(x2+v)` and `x2 += 0.01*u`. Each source decision holds u and v for ten inner steps (`dt=0.1`, inner step `0.01`). The target is the closed unit disk. Source reward is elapsed inner-Euler time until the target is entered. The upstream two-agent solver trains u on negative elapsed reward and v on positive elapsed reward, giving the finite pilot its minimizing-u/maximizing-v orientation.

This report discretizes each continuous interval `[-1,1]` to `{-1,0,1}`, keeps the source's ten held-action Euler substeps, and uses a 35-decision finite horizon. The source's two state-feedback policies both use the current environment state and neither receives the other player's current action. This finite adaptation changes that information pattern: u selects first, then v observes u's action before choosing a disturbance. The reported value and winning set belong to this sequential-response game, not to the source RL game's policy information pattern. `finite_feedback` finds the first horizon at which the initial state is robustly winning. `finite_causal_minimax` minimizes the worst-case captured time on the same finite graph. The figure shows every forward finite state cloud and each layer's backward-winning intersection, plus one worst-case path under a minimax-optimal causal policy.

The result is a finite-catalogue adaptation. It does not reproduce RL training, certify a continuous-action policy, or establish a continuous-state winning boundary. Timings are one descriptive host capture with no comparison claim.

Reproduce by building `csl_env717_time_sphere_minimax`, running it to JSON, and checking the output with `scripts/reports/env717/check_time_sphere_minimax.py`. See `capture.json`, `environment.json`, and the exact source identities in `result.json`.
