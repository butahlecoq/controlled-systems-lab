# Plaksin et al. (2024): differential-game values and comparability

## Finding

The paper is useful as a source of three analytic terminal-game values and as a qualitative RL comparison. Its published Figure 3 is not a set of certified benchmark scores for CSL: the bars summarize learned policies evaluated by additional RL opponent searches, across only five training runs. Of the two named “GetInto” games, `GetIntoSquare` is the same continuous game as the repository's `MaxCoordinateGame`; `GetIntoCircle` is dynamically equivalent to the repository's `SphereGame` after a factor-of-two time rescaling. Existing CSL artifacts are finite adaptations and do not reproduce the paper's RL training or certify its continuous-game values.

## Game semantics and analytic values

The paper defines a finite-horizon zero-sum positional differential game with payoff

`J = sigma(x(T)) + integral_tau^T f0(t,x(t),u(t),v(t)) dt`.

The first player chooses `u` to **minimize** `J`; the second chooses `v` to **maximize** it. The guaranteed values use the positional-information limit: the minimizing player's guarantee takes `sup` over the maximizing player's measurable controls and then `inf` over the minimizing player's policies; the maximizing player's guarantee is symmetric (`inf` over `u`, then `sup` over `v`). Under the paper's Isaacs condition, these values coincide. These are pure positional policies with deterministic guarantees, not expected payoffs from mixed Markov-game policies. [Paper, §3, eqs. (1)–(6)](https://proceedings.mlr.press/v235/plaksin24a.html).

The exact values relevant to the figures are:

| Game | Payoff and dynamics at the stated initial condition | Published value | Meaning |
| --- | --- | ---: | --- |
| `GetIntoCircle` | `x1'=v`, `x2'=u`; `u∈[-0.5,0.5]`, `v∈[-1,1]`; `x(0)=(0,0.5)`, `T=4`; `J=||x(4)||−4` | `0` | The minimizing player can guarantee terminal radius 4, the boundary of the radius-4 circle. |
| `GetIntoSquare` | `x1'=x2+v`, `x2'=−x1+u`; `u,v∈[-1,1]`; `x(0)=(0.2,0)`, `T=4`; `J=max(|x1(4)|,|x2(4)|)` | `1` | The minimizing player can guarantee terminal max-coordinate norm 1, the boundary of the side-2 square `[-1,1]^2`. |

These values and interpretations are stated in Appendix G; the games' roles and payoff signs are explicit there. [Paper, Appendix G](https://proceedings.mlr.press/v235/plaksin24a.html). In particular, the paper's `GetIntoSquare` prose says “side a = 1,” while the stated value in the max-coordinate norm means the boundary `max(|x1|,|x2|)=1` (a square of side length 2); treat “side a=1” as a likely wording error, not as a different value.

The paper also gives `EscapeFromZero` value `−0.5`, with payoff `−||x(2)||`, so the minimizer (first player) guarantees the point is at least 0.5 from the origin. [Paper, Appendix G](https://proceedings.mlr.press/v235/plaksin24a.html). It does not give exact values for its finite-horizon Homicidal Chauffeur or the other listed learned environments.

## What Figure 3 measures

Figure 3 plots “guaranteed values” of the quality index for eight algorithms and eight environments, with dotted lines for exact values where known. For each trained first-player policy, the authors freeze that policy and use several conventional RL algorithms to search for a maximizing opponent; they take the maximum observed `J` as an approximation to that policy's minimizing-player guarantee. They repeat symmetrically for the second player, using the minimum observed `J`. Five training runs supply the displayed best, mean, and worst run ranges. The paper itself describes these opponent-search extrema as approximations, not exact solves. [Paper, §6 and Figure 3](https://proceedings.mlr.press/v235/plaksin24a.html).

Thus Figure 3 is useful for comparing the paper's algorithms under its own protocol and for seeing distance from the dotted analytic value. It is not a reliable numerical acceptance threshold for another solver: the plotted endpoints depend on learned policies, opponent search, training randomness, and the paper's discretized action sets. Appendix F states that `GetIntoCircle` uses 10-point linear meshes for `u∈[-0.5,0.5]` and `v∈[-1,1]`; `GetIntoSquare` uses 10-point meshes for both `[-1,1]` actions. The paper also discretizes time for DQN and reports five runs, not a certified continuous-action error bound. [Paper, §4, §6, Appendix F](https://proceedings.mlr.press/v235/plaksin24a.html).

## Match to `imm-rl-lab/optimal_control` and CSL evidence

- **Source access.** `imm-rl-lab/optimal_control` is a private GitHub repository, so its source pages are not publicly browsable. The public citations below point to CSL's source-derived records, which preserve the upstream commit, file path and blob hash alongside the re-expressed equations.
- **`GetIntoSquare` ↔ `MaxCoordinateGame`: exact model match.** Both have the same oscillator dynamics, initial state `(0.2,0)`, 4-second horizon, controls in `[-1,1]`, and terminal objective `max(|x1|,|x2|)`. CSL's source-derived result records `y'=z+v`, `z'=-y+u`, the initial state, bounds, horizon, reward, source commit and blob hash. [Pinned CSL source-derived model record](../../reports/algorithm-results/env717-max-coordinate-pilot-v1/result.json). CSL's `env717-max-coordinate-pilot-v1` is only a three-stage, finite-action, fixed-plan adaptation, so it is not an RL or continuous-value replication. [Pilot scope](../../reports/algorithm-results/env717-max-coordinate-pilot-v1/README.md).
- **`GetIntoCircle` ↔ `SphereGame`: exact trajectory family after time scaling.** The paper has `x1'=v`, `x2'=u`, initial `(0,0.5)`, and terminal cost `||x(4)||−4`. The pinned `SphereGame` scenario records `y'=v`, `z'=u`, initial `(y,z)=(0,0.5)`, and cost `sqrt(y²+z²)−4`, but uses horizon 8 and half-sized control bounds (`u∈[-0.25,0.25]`, `v∈[-0.5,0.5]`). Under `s=2t`, its control amplitudes and horizon map to the paper's model, preserving the state trajectories and terminal cost. This is an analytical time-rescaling correspondence, not literal parameter equality. [Pinned CSL source model and provenance](../../benchmarks/scenarios/env717-sphere-game-pilot-v1.json); [finite-action report scope](../../reports/algorithm-results/env717-sphere-game-pilot-v1/README.md).
- **Other Figure 3 games:** CSL's `PointOnThePlane` has second-order 4D dynamics and different control scaling, so it is not `GetIntoCircle`; its “point on plane” name is not evidence of model identity. [CSL source and adaptation](../../reports/algorithm-results/env717-point-on-plane-pilot-v1/README.md). CSL's Homicidal Chauffeur report is a separate source-derived finite adaptation; its source uses an evader heading on the unit circle, while the paper gives the adversary a unit-ball velocity action, so the shared name/topic alone does not establish an exact match. [CSL scenario and scope](../../benchmarks/scenarios/env717-homicidal-chauffeur-pilot-v1.json); [paper Appendix G](https://proceedings.mlr.press/v235/plaksin24a.html).

CSL's environment index describes its archived work as finite adaptations with shortened horizons, finite catalogues and explicit information patterns, and specifically lists `MaxCoordinateGame` and `SphereGame`. It does not present those artifacts as reproductions of Plaksin et al.'s learning curves. [CSL differential-game index](./env717-differential-game-index.md).

## Limits

The paper provides exact analytic values for its specified games, but a value alone does not validate a different discretization, information pattern, reward convention, or numerical integration scheme. Figure 3 should be cited as the paper's experimental result, not imported as a ground-truth table. For a CSL comparison, cite the analytic value together with the exact source model and state clearly whether the result is from the continuous game, a finite-action adaptation, or a learned-policy experiment. No benchmark was run for this research note.
