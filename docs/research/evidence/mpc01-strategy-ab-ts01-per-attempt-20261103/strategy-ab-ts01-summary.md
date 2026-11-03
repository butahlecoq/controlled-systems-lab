# Resource-limited saved Strategy A/B T-S01 capture

This functional measurement uses the same exact two-stage integrator equations as `ts01-exact-v1`: `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and terminal objective `(x2-1)^2`. It is a separate registered-strategy path from the OSQP/HPIPM QP solve-phase measurements; phase timings are not directly comparable.

- Source commit: `af4aa5cec4c8a9673460da63475698c2bd76a92a`.
- Scenario SHA-256: `bbeb83947627a197d71dd380dbaa5cfae12e22cd6d79b12e66ef08275b2c390a`.
- Event/stdout SHA-256: `3b1d7b69eb0720759b02714be3a786aab0be980c509c614f7cea24d1dce0d8f5`.
- 1 excluded warmup pair(s) and 5 measured alternating A/B pairs; all 12 trials passed.
- Every measured result carries the registered T-S01 complete-family profile, two distinct selected witnesses, zero original/recomputed objective, and numerical-pass original-data checks. Witness checks do not claim separate optimality or completeness proofs; the profile-specific family status is retained separately.

| Strategy | Median end-to-end (ms) | Range (ms) |
|---|---:|---:|
| `csl.synthesis.reach-back` | 12.458224 | 7.217722–13.507177 |
| `csl.synthesis.strategy-b` | 4.304973 | 2.835294–4.406174 |

The timing interval covers strategy preparation through two witness checks. It excludes process startup, shared scenario/provider setup, JSON serialization, build and rendering. The supervised process tree ran under a 8589934592 byte cgroup-v2 memory cap with swap disabled and a 300 second watchdog. Wall-cap scope: each individual Strategy A or Strategy B attempt is restarted and supervised in its own process tree. Observed peak process-tree memory was 12439552 bytes; no OOM or timeout occurred. 2 separate limiter probes are retained. Timings support no general performance-winner claim.

Saved-data report: [`strategy-ab-ts01-summary.html`](strategy-ab-ts01-summary.html) with the control-plane figure [`strategy-ab-ts01-control-plane.svg`](strategy-ab-ts01-control-plane.svg).

Regenerate the HTML, SVG, and Markdown summary from the retained records:

```sh
python3 scripts/reports/mpc01/summarize_strategy_ab.py \
  --events docs/research/evidence/mpc01-strategy-ab-ts01-per-attempt-20261103/strategy-ab-ts01-events.jsonl \
  --stdout docs/research/evidence/mpc01-strategy-ab-ts01-per-attempt-20261103/strategy-ab-ts01-stdout.jsonl \
  --scenario docs/research/evidence/mpc01-strategy-ab-ts01-per-attempt-20261103/scenario.json \
  --environment docs/research/evidence/mpc01-strategy-ab-ts01-per-attempt-20261103/strategy-ab-ts01-environment.json \
  --resource-profile docs/research/evidence/mpc01-strategy-ab-ts01-per-attempt-20261103/resource-profile.json \
  --output docs/research/evidence/mpc01-strategy-ab-ts01-per-attempt-20261103/strategy-ab-ts01-summary.md
```
