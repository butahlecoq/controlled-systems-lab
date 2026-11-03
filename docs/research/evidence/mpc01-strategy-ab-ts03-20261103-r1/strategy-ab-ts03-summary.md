# MPC-01 registered Strategy A/B on T-S03

This synthetic singular-integrator fixture uses `x0=0`, `x[t+1]=u[t]`, independent `u0,u1 in [0,1]`, and terminal cost `(x2-1)^2`. Since `x2=u1`, the exact minimizer family is `u0 in [0,1], u1=1`; this analytic family was not inferred from a selected witness.

One warmup pair was excluded; five measured pairs alternated order. All 12 attempts completed and reported profile-specific family verification. Both selected histories passed original-model binding, feasibility, and objective checks at objective zero. The verifier's separate trajectory optimality/completeness fields remain unsupported.

| Strategy | Median end-to-end (ms) | Range (ms) |
|---|---:|---:|
| `csl.synthesis.reach-back` | 4.693297 | 4.635259–4.999275 |
| `csl.synthesis.strategy-b` | 1.255685 | 1.222790–1.313864 |

Timing is strategy preparation through selected-witness replay, excluding process startup, shared setup, serialization, build and rendering. Five pairs on this one small synthetic fixture are descriptive; they establish no general winner.

The full process tree ran under a 2 GiB cgroup-v2 cap with swap disabled and a 300-second suite watchdog. The watchdog is suite-wide, not per-attempt, and does not meet the comparison contract default per-attempt limiter profile.

Source commit: `0f407af581c3a5b536d5d76f6e889fef542c4597`. Scenario SHA-256: `a1d6fa3f349bfb6032736e5f6b52e0ff52f8bdece8cfe54752de12c9cf314e4d`. Event SHA-256: `bcf51736bf00389ca1eb0579268d383f4a593c6953f7637be490672afa1d578b`. Executable SHA-256: `f87118d2114992fea92625e60599ff6937de694a189389cc3e173187f2d4f73e`.

This is a partial #597 increment. The broader fixture matrix, external comparison and publication catalogue integration remain outstanding.
