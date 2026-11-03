# Resource-limited saved Strategy A/B T-S02 capture

T-S02 is the two-stage scalar integrator with `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and constant objective `J=3`. Every feasible control pair is therefore an exact minimizer; this fixture checks family plumbing and witness replay, not optimization difficulty.

- Source commit: `af4aa5cec4c8a9673460da63475698c2bd76a92a`.
- Build note: [`build-note.json`](build-note.json) (SHA-256 `a4bb90335a8f3288fb698d554b40c36a36f3b2ac2e25384951e66784d75c06ce`).
- Scenario SHA-256: `b9bb051c52b6763ceee7a6f7f423fbefd94bea86a0045693b6627a0a0da69ab9`.
- Event/stdout SHA-256: `ec0beb321e6acd18aa0f929e77309250ce0bff80da22ea165e8fa2dff06aa262`.
- Binary source revision <code>af4aa5cec4c8a9673460da63475698c2bd76a92a</code> is linked to the configured CMake metadata, object digest, and executable SHA-256 in the retained build note. Executable SHA-256: `dc57e3c16c5b1c356cd86762105f86a913a61c7a60cc6855c86bad083ac86e5e`.
- One excluded warmup pair; five measured alternating pairs; all 12 trials passed.
- Each result marked its profile-specific family complete and returned two distinct histories. Original-model bindings, feasibility, and objective checks passed; separate proof fields for optimality and completeness remain unsupported.
- The exact minimizer set is the full unit square. Both strategies returned the same two corner witnesses.

| Strategy | Median end-to-end (ms) | Range (ms) |
|---|---:|---:|
| `csl.synthesis.reach-back` | 7.419301 | 6.442703–14.480593 |
| `csl.synthesis.strategy-b` | 2.046087 | 1.325808–2.125428 |

Each of the 12 strategy attempts ran in its own Linux cgroup-v2 process scope with a 300-second process-tree watchdog, 8 GiB memory cap, no swap, 100% CPU quota, and one pinned logical CPU. The sum of attempt scope wall times was 0.141024 s; the largest observed process-tree memory peak was 12214272 bytes. Every attempt completed without timeout or memory-limit events. A separate excluded warmup pair records limiter enforcement for both strategies.

The timings cover strategy preparation through original-problem witness verification; they exclude process startup, shared setup, JSON I/O, build and rendering. This tiny constant-objective fixture supports no general winner claim.

Report: [`strategy-ab-ts02-summary.html`](strategy-ab-ts02-summary.html); figure: [`strategy-ab-ts02-control-plane.svg`](strategy-ab-ts02-control-plane.svg).
