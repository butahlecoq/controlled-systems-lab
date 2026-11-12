# MPC-01 five-repetition native solver comparison

This is a new comparison on the frozen `b04-reference-v1` article-derived input and five analytic/general-purpose cases. It is not a historical B04 reconstruction. The native solver status is recorded separately from mathematical evidence. Binary64 trajectory diagnostics are inconclusive and do not establish optimality.

## Run identity

- Records SHA-256: `a66427271b6672c4cd9794364cb80f9d1c432b7da7b9ce036b66569010628a1a`
- Runner stdout SHA-256: `3072aa3fdfbad5031fefcdd9db72e9c314da1114f33760162ceb9301f47c1b87`
- Canonical records: 6; attempts: 120; repetitions per arm: 5.
- Execution alternated which backend ran first on each repetition. Each backend used a fresh workspace for the cold attempt, then a separate fresh workspace seeded from that repetition's cold result when available. Warm fallback remains explicit.
- Reported phases are formulation, setup, warm-start, solve and extraction. This excludes post-run independent proof work; the available binary64 residual diagnostics remain inconclusive.
- No acados or Strategy A/B paired comparison is included. These records do not support a control-strategy or overall solver winner claim.
- See `comparison-records.jsonl` for the canonical, self-contained archives; `runner-attempts.jsonl` preserves the runner's stdout rows.

## B04 reference case: phase timing, microseconds

Times are median (minimum–maximum) over five attempts. A performance difference is not an overall algorithm or strategy winner: setup variance and independent optimality evidence remain relevant.

| Backend / start | Iterations | Formulation | Setup | Warm-start | Solve | Extraction | Outcome / start application |
|---|---:|---:|---:|---:|---:|---:|---|
| OSQP / cold | 33125 (33125–33125) | 47.7 (46.7–55.2) | 113.6 (91.1–132.7) | 0.0 (0.0–0.0) | 163301.3 (163223.5–164102.7) | 8.2 (7.2–9.0) | optimal; seed applied 0/5 |
| HPIPM / cold | 30 (30–30) | 41.5 (40.6–41.9) | 57.7 (26.7–59.4) | 0.0 (0.0–0.0) | 996.5 (966.9–1000.3) | 4.8 (4.3–4.8) | optimal; seed applied 0/5 |
| OSQP / warm_if_available | 25 (25–25) | 56.3 (55.0–60.1) | 106.2 (102.9–117.2) | 2.0 (1.9–2.4) | 135.2 (134.9–135.5) | 4.7 (4.4–4.8) | optimal; seed applied 5/5 |
| HPIPM / warm_if_available | 8 (8–8) | 38.5 (37.7–39.5) | 36.7 (26.3–42.0) | 2.3 (1.4–2.4) | 256.9 (255.8–274.0) | 4.7 (4.7–4.8) | optimal; seed applied 5/5 |

## Native solver classification and termination

These are solver-status classifications; they are not independent mathematical outcome claims.

| Case | OSQP classification / termination | HPIPM classification / termination |
|---|---|---|
| `b04-reference-v1` | optimal (completed) | optimal (completed) |
| `double-integrator-421-v1` | optimal (completed) | optimal (completed) |
| `infeasible-integrator-v1` | infeasible (completed) | undetermined (completed) |
| `ts01-exact-v1` | optimal (completed) | optimal (completed) |
| `ts02-constant-v1` | optimal (completed) | optimal (completed) |
| `unbounded-integrator-v1` | unbounded (completed) | undetermined (completed) |

## B04 diagnostics

- Exact reference norm: 160.880653945527.
- Native original-norm range: 160.880653945490–160.882458930638; max absolute difference from exact reference: 0.00180499.
- Largest binary64 dynamics/bound residual across native attempts: 1.91348e-06; diagnostics remain inconclusive.
- The five cold paths per backend are not averaged. The figure selects the cold repetition whose solve duration is closest to that backend's median cold solve duration. It is a representative trajectory, not a median trajectory.

## Limiter and interpretation

Solver iteration counts explain work per solve: cold B04 OSQP used 33,125 iterations, while HPIPM used 30. In a separate one-repetition diagnostic process run, the full six-case runner consumed 0.417 s user CPU and 0.132 s system CPU over 0.550 s elapsed, indicating the suite was CPU-bound on this host; that run is not part of the timing sample. `process-profile.txt` records those aggregate times. The repeated run did not enforce per-attempt wall or memory caps; its records mark memory as unlimited. It is a local exploratory measurement rather than the enforced-comparison resource profile. These tiny QP cases are microbenchmarks. They do not establish end-to-end planning latency or a control-strategy winner. Machine load immediately before the reported run was captured in run metadata with 8 logical CPUs.
