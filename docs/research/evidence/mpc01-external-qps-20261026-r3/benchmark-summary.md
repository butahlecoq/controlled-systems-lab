# MPC-01 five-repetition native solver comparison

This is a new comparison on the frozen `b04-reference-v1` article-derived input and six analytic/general-purpose cases. It is not a historical B04 reconstruction. The native solver status is recorded separately from mathematical evidence. Binary64 residual diagnostics alone are inconclusive; a separate exact-rational checker re-derives feasible trajectories and objective bounds from the saved controls.

## Run identity

- Records SHA-256: `b617f7f24794e898bae5e2c64663b9474fe1b5c642db3aee4b76fffe16ac645a`
- Runner stdout SHA-256: `c37f59b1d5db218685f317b90442ac121dbcaa5c557e10959c2c1142578cde4b`
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
| OSQP / cold | 33125 (33125–33125) | 48.1 (45.6–56.2) | 104.3 (91.6–122.2) | 0.0 (0.0–0.0) | 163642.2 (163502.4–163824.4) | 7.2 (7.1–9.1) | optimal; seed applied 0/5 |
| HPIPM / cold | 30 (30–30) | 42.0 (41.5–55.8) | 55.9 (27.1–60.1) | 0.0 (0.0–0.0) | 1010.8 (979.1–1019.4) | 4.7 (4.7–4.8) | optimal; seed applied 0/5 |
| OSQP / warm_if_available | 25 (25–25) | 56.4 (54.9–60.0) | 105.5 (102.7–132.2) | 2.0 (1.9–2.4) | 135.1 (134.9–135.6) | 4.7 (4.4–4.9) | optimal; seed applied 5/5 |
| HPIPM / warm_if_available | 8 (8–8) | 39.3 (34.3–51.3) | 27.0 (26.6–37.2) | 2.4 (2.3–2.4) | 259.7 (258.1–260.7) | 4.7 (4.3–4.8) | optimal; seed applied 5/5 |

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

Solver iteration counts explain work per solve: cold B04 OSQP used 33,125 iterations, while HPIPM used 30. A separate one-repetition seven-case process profile recorded 0.50 s user CPU, 0.12 s system CPU, and 0.62 s elapsed; it is excluded from the timing sample. Bash built-in time measures the runner process in aggregate and does not isolate per-solver CPU. The timed run did not enforce per-attempt wall or memory caps; its records mark memory as unlimited. It is a local exploratory measurement rather than the enforced-comparison resource profile. These tiny QP cases are microbenchmarks. They do not establish end-to-end planning latency or a control-strategy winner. Host load sampled just after this run was 0.46, 0.76, 0.81 (sampled just after capture) with 8 logical CPUs.
