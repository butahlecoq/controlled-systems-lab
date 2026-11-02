# Resource-limited saved Strategy A/B T-S02 capture

T-S02 is the two-stage scalar integrator with `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and constant objective `J=3`. Every feasible control pair is therefore an exact minimizer; this fixture checks family plumbing and witness replay, not optimization difficulty.

- Source commit: `2977b95bab581a343c2daba02459f96014e893b0`.
- Scenario SHA-256: `b9bb051c52b6763ceee7a6f7f423fbefd94bea86a0045693b6627a0a0da69ab9`.
- Event/stdout SHA-256: `3c7be42c44533f9032870656a9ea50becc95acea9553ccd573d07ed784d89661`.
- One excluded warmup pair; five measured alternating pairs; all 12 trials passed.
- Each result marked its profile-specific family complete and returned two distinct histories. Original-model bindings, feasibility, and objective checks passed; separate proof fields for optimality and completeness remain unsupported.
- The exact minimizer set is the full unit square. Both strategies returned the same two corner witnesses.

| Strategy | Median end-to-end (ms) | Range (ms) |
|---|---:|---:|
| `csl.synthesis.reach-back` | 5.103343 | 5.014435–6.353442 |
| `csl.synthesis.strategy-b` | 0.554056 | 0.527585–0.725028 |

The process tree completed in 0.060324 s under a 2 GiB cgroup-v2 memory cap, no swap, and a 300-second suite-level watchdog; peak memory was 19841024 bytes with zero OOM/limit events. This wall cap covers the whole capture invocation, not individual trials. The profile is below the default 8 GiB per-attempt cap and does not fulfill the default per-attempt timeout profile.

The timings cover strategy preparation through original-problem witness verification; they exclude process startup, shared setup, JSON I/O, build and rendering. This tiny constant-objective fixture supports no general winner claim.

Report: [`strategy-ab-ts02-summary.html`](strategy-ab-ts02-summary.html); figure: [`strategy-ab-ts02-control-plane.svg`](strategy-ab-ts02-control-plane.svg).
