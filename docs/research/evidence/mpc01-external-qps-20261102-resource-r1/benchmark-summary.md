# MPC-01 five-repetition native solver comparison

This is a new comparison on the frozen `b04-reference-v1` article-derived input and six analytic/general-purpose cases. It is not a historical B04 reconstruction. The native solver status is recorded separately from mathematical evidence. Binary64 residual diagnostics alone are inconclusive; a separate exact-rational checker re-derives feasible trajectories and objective bounds from the saved controls.

## Run identity

- Records SHA-256: `88acdb74bda3a7d25904b975454fffedd69c05669737a14be7abddfd5d44ced6`
- Runner stdout SHA-256: `c0bf8454ab138da267c7fa680b259c1343b138aeab23b863f8d27e3b12dcbdb4`
- Canonical records: 7; attempts: 140; repetitions per arm: 5.
- Exact independent candidate checks: 90; see `exact-check-manifest.json` and `exact-candidate-checks.jsonl`.
- Execution alternated which backend ran first on each repetition. Each backend used a fresh workspace for the cold attempt, then a separate fresh workspace seeded from that repetition's cold result when available. Warm fallback remains explicit.
- Reported phases are formulation, setup, warm-start, solve and extraction. This excludes post-run independent proof work; the available binary64 residual diagnostics remain inconclusive.
- No acados or Strategy A/B paired comparison is included. These records do not support a control-strategy or overall solver winner claim.
- See `comparison-records.jsonl` for the canonical, self-contained archives; `runner-attempts.jsonl` preserves the runner's stdout rows.

## B04 reference case: phase timing, microseconds

Times are median (minimum–maximum) over five attempts. A performance difference is not an overall algorithm or strategy winner: setup variance and independent optimality evidence remain relevant.

| Backend / start | Iterations | Formulation | Setup | Warm-start | Solve | Extraction | Outcome / start application |
|---|---:|---:|---:|---:|---:|---:|---|
| OSQP / cold | 33125 (33125–33125) | 47.6 (44.9–53.8) | 101.0 (94.0–118.2) | 0.0 (0.0–0.0) | 163066.5 (162055.6–163729.9) | 8.5 (7.1–9.6) | optimal; seed applied 0/5 |
| HPIPM / cold | 30 (30–30) | 38.6 (37.3–43.6) | 49.1 (26.6–55.9) | 0.0 (0.0–0.0) | 1002.1 (969.0–1032.7) | 4.7 (4.3–4.8) | optimal; seed applied 0/5 |
| OSQP / warm_if_available | 25 (25–25) | 55.9 (51.8–58.0) | 110.3 (107.6–118.8) | 2.3 (1.9–2.4) | 134.6 (132.3–134.9) | 4.8 (4.7–4.8) | optimal; seed applied 5/5 |
| HPIPM / warm_if_available | 8 (8–8) | 38.6 (35.3–39.5) | 36.7 (27.2–40.1) | 2.4 (2.0–2.4) | 257.6 (251.5–272.2) | 4.6 (1.5–4.7) | optimal; seed applied 5/5 |

## Native solver classification and termination

These are solver-status classifications; they are not independent mathematical outcome claims.

| Case | OSQP classification / termination | HPIPM classification / termination |
|---|---|---|
| `b04-reference-v1` | optimal (completed) | optimal (completed) |
| `double-integrator-421-v1` | optimal (completed) | optimal (completed) |
| `infeasible-integrator-v1` | infeasible (completed) | undetermined (completed) |
| `ts01-exact-v1` | optimal (completed) | optimal (completed) |
| `ts02-constant-v1` | optimal (completed) | optimal (completed) |
| `ts03-singular-v1` | optimal (completed) | undetermined (completed) |
| `unbounded-integrator-v1` | unbounded (completed) | undetermined (completed) |

## B04 diagnostics

- Exact reference norm: 160.880653945527.
- Native original-norm range: 160.880653945490–160.882458930638; max absolute difference from exact reference: 0.00180499.
- Largest binary64 dynamics/bound residual across native attempts: 1.91348e-06; those diagnostics alone remain inconclusive.
- The five cold paths per backend are not averaged. The figure selects the cold repetition whose solve duration is closest to that backend's median cold solve duration. It is a representative trajectory, not a median trajectory.

## Singular T-S03 analytic reference

For this fixture, the state recurrence is `x[t+1]=u[t]`, with both controls in `[0,1]`, and the terminal objective is `(x2-1)^2`. Therefore the objective reduces to `(u1-1)^2`: its exact minimum is zero and its complete optimal control face is `{(u0,u1): 0<=u0<=1, u1=1}`. The first control is a singular zero-curvature direction. This exact derivation checks solver objective values without requiring identical witnesses; it does not certify general family completeness for either native QP backend.

## Infeasible and unbounded analytic references

The infeasible fixture fixes `x0=0`, `u0=0`, and requires `x1=1`, while its dynamics require `x1=x0+u0=0`; infeasibility follows from the exact contradiction. In the unbounded fixture, `x1=u0` has no finite control bound and the objective is `-x1`; the feasible ray `u0=s` drives the objective to `-infinity`. OSQP's precise native classifications agree with these references. HPIPM returns undetermined on both and remains so in the saved records.

## Independent exact feasibility and objective bounds

The standalone Fraction checker exactly re-derived states from each saved binary64 control sequence and the exact fixture recurrence, verified all relevant control/state bounds, and compared exact candidate objective upper bounds with analytic lower bounds for 90 optimal attempts. It checks squared norm for B04. Maximum exact objective gaps by case: b04-reference-v1: max exact gap 1.99716e-06; double-integrator-421-v1: max exact gap 4.87484e-20; ts01-exact-v1: max exact gap 7.15511e-25; ts02-constant-v1: max exact gap 0; ts03-singular-v1: max exact gap 2.22706e-14.

## Limiter and interpretation

This seven-fixture capture completed 140/140 attempts under an enforced Linux cgroup-v2 process-tree cap: 8 GiB memory, swap disabled, one worker pinned to CPU 0, and a 300-second watchdog for the complete suite. Peak process-tree memory was 24,743,936 bytes; cgroup memory-limit and OOM counters were zero. The attempts ran sequentially, so the process-tree memory cap bounded each solver call. The watchdog was suite-level, not per attempt. The canonical comparison records still declare memory as unlimited because this runner does not ingest the external cgroup profile; `resource-profile.json` binds the exact record and stdout hashes and documents that difference. A separate 5-second, 8 GiB cgroup run of the independent Fraction checker verified exact feasibility and candidate objective bounds for all 90 solver attempts classified as optimal. A source-mapped limiter profile is unavailable (`perf` is not installed on this host), so the recorded timings are descriptive and support no solver or control-strategy performance winner. These tiny QP cases do not establish end-to-end planning latency. Host load average was 0.84 / 1.54 / 1.31 before and after the 1.70-second capture on an 8-logical-CPU host.
