# ENV-717 CartPole source and adaptation note

## Pinned source identity

The upstream environment suite is pinned to `imm-rl-lab/optimal_control`
commit [`f4d76c60f4003f50954174e96eafd8e514bd5441`](https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441).
Its [`Environments/CartPole/CartPole.ipynb`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/CartPole/CartPole.ipynb)
is blob `21d1122b701df85e21b5225fdbd42ff9f3bd702e`. The DCEM experiment
[`CartPole_with_DCEM.ipynb`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/CartPole_with_DCEM.ipynb)
is blob `5af9324376c342da177a411394730ccc3f7edd5b` and constructs
`gym.make("CartPole-v1")`. The pinned
[`Solvers/OneAgentSolver.py`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Solvers/OneAgentSolver.py)
is blob `87485e23497e286022d76c6f2e70e0469aa18584`; it expects `reset()` to
return one observation and `step()` to return four values.

The upstream repository does not declare a Gym dependency version. This pilot
adopts Gym v0.21.0 at commit
[`c755d5c35a25ab118746e2ba885894ff66fb8c43`](https://github.com/openai/gym/tree/c755d5c35a25ab118746e2ba885894ff66fb8c43),
whose CartPole source file is blob `e11adcba6f413017e8661e8990dde668a63a129c`
and registry file is blob `a90b0370730e74d783971a1a3f0771c5a2fb572e`. The
legacy four-value API matches the pinned solver call. Gym's `CartPole-v1`
registration supplies a 500-step wrapper limit. The pilot horizon is 14, so
that wrapper limit does not bind. The Gym source identifies its license as MIT
in [`LICENSE.md`](https://github.com/openai/gym/blob/c755d5c35a25ab118746e2ba885894ff66fb8c43/LICENSE.md).
The upstream `optimal_control` repository has no license declared in its
GitHub repository metadata; this pilot independently re-expresses equations
and does not copy its implementation.

## Model and semantics

The four state coordinates are cart position, cart velocity, pole angle, and
pole angular velocity. Gym's source uses gravity `9.8 m/s²`, cart mass `1 kg`,
pole mass `0.1 kg`, half-length `0.5 m`, fixed action forces `-10 N` and
`+10 N`, and a `0.02 s` sample period. It computes cart and pole acceleration
from the current angle, rates, and force, then advances both positions using
the old rates and both rates using explicit Euler. The strict termination
limits are `|cart position| > 2.4 m` or `|pole angle| > 12°`. Each executed
step returns reward `+1`, including the first step that crosses a limit; the
pilot stops immediately after that transition.

Gym reset draws each state coordinate independently from the open interval
`(-0.05, 0.05)`. The finite fixture uses the exact zero vector, the midpoint
of that support, to make all plan replays deterministic. This is one point in
the original initial support, not a claim about random-start expected return.

## Finite catalogue

The report enumerates every open-loop sequence of 14 binary actions: `2^14 =
16,384` plans. Action bit `k` selects the force at step `k`. For each plan,
replay stops at first termination or after step 14. The objective is the
resulting integer reward. Every plan is independently recomputed in Python;
the checker verifies the full plan table, terminal state, executed-step count,
termination flag, transition total, and complete maximizing-plan family.

The figure projects every finite action-prefix state onto `(cart position,
cart velocity)` and `(pole angle, pole angular velocity)`. It shows first
termination points and one deterministic maximizing trajectory. These are
finite-catalogue points, not convex reachability enclosures. The report makes
no continuous-state feedback, robust/minimax, learned-policy, or optimality
claim for the source's 500-step RL problem. The upstream learned episode scores
are not compared because the dependency version and policy semantics are not
fully specified by this pilot.

The Release timing measures only complete enumeration, including allocation,
propagation, termination checks, and reward scoring, and excludes JSON
construction and serialization. It is a single-host descriptive observation;
it does not compare algorithms or establish a speedup.
