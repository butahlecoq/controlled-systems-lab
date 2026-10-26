# Current-branch Strategy A/B T-S01 paired run

This functional measurement uses the same exact two-stage integrator equations as `ts01-exact-v1`: `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and terminal objective `(x2-1)^2`. It is a separate registered-strategy path from the OSQP/HPIPM QP solve-phase measurements; phase timings are not directly comparable.

- Source commit: `ce7cc08f585fd80f5e63d30becf5ef4054fd879e`.
- Scenario SHA-256: `bbeb83947627a197d71dd380dbaa5cfae12e22cd6d79b12e66ef08275b2c390a`.
- Event/stdout SHA-256: `2271031cdcd5e96d5da577c3fdab52277bc004e8d7ce79b925c650929c32de4a`.
- One excluded warmup pair and seven measured alternating A/B pairs; all 16 trials passed.
- Every measured result carries the registered T-S01 complete-family profile, two distinct selected witnesses, zero original/recomputed objective, and numerical-pass original-data checks. Witness checks do not claim separate optimality or completeness proofs; the profile-specific family status is retained separately.

| Strategy | Median end-to-end (ms) | Range (ms) |
|---|---:|---:|
| `csl.synthesis.reach-back` | 5.325654 | 5.263006–9.010723 |
| `csl.synthesis.strategy-b` | 1.310374 | 1.258761–2.004882 |

The timing interval covers strategy preparation through two witness checks. It excludes process startup, shared scenario/provider setup, JSON serialization, build and rendering. No separate limiter or per-attempt resource-cap profile was collected, so these tiny-case timings support no general performance winner claim.
