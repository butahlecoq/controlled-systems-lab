# Resource-limited saved Strategy A/B T-S01 capture

This functional measurement uses the same exact two-stage integrator equations as `ts01-exact-v1`: `x0=0`, `x[t+1]=x[t]+u[t]`, `u[t] in [0,1]`, and terminal objective `(x2-1)^2`. It is a separate registered-strategy path from the OSQP/HPIPM QP solve-phase measurements; phase timings are not directly comparable.

- Source commit: `ce7cc08f585fd80f5e63d30becf5ef4054fd879e`.
- Scenario SHA-256: `bbeb83947627a197d71dd380dbaa5cfae12e22cd6d79b12e66ef08275b2c390a`.
- Event/stdout SHA-256: `6f6349e8c71844a14d6f08d1919617234628ce05d57fd8431516aa705b221997`.
- One excluded warmup pair and seven measured alternating A/B pairs; all 16 trials passed.
- Every measured result carries the registered T-S01 complete-family profile, two distinct selected witnesses, zero original/recomputed objective, and numerical-pass original-data checks. Witness checks do not claim separate optimality or completeness proofs; the profile-specific family status is retained separately.

| Strategy | Median end-to-end (ms) | Range (ms) |
|---|---:|---:|
| `csl.synthesis.reach-back` | 5.322090 | 5.254692–5.786888 |
| `csl.synthesis.strategy-b` | 1.281738 | 1.266303–1.402075 |

The timing interval covers strategy preparation through two witness checks. It excludes process startup, shared scenario/provider setup, JSON serialization, build and rendering. The full capture process tree completed under a 2147483648 byte cgroup-v2 memory cap with swap disabled and a 300 second suite-level wall cap. The wall cap covers the whole capture invocation, not each trial separately. Observed peak process-tree memory was 10018816 bytes; no OOM or timeout occurred. This constrained-host profile is not the comparison-program default per-attempt profile and supports no general performance winner claim.

Saved-data report: [`strategy-ab-ts01-summary.html`](strategy-ab-ts01-summary.html) with the control-plane figure [`strategy-ab-ts01-control-plane.svg`](strategy-ab-ts01-control-plane.svg).

Regenerate the HTML, SVG, and Markdown summary from the retained records:

```sh
python3 scripts/reports/mpc01/summarize_strategy_ab.py \
  --events docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-events.jsonl \
  --stdout docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-stdout.jsonl \
  --scenario examples/scenarios/two-stage-integrator.json \
  --environment docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-environment.json \
  --resource-profile docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/resource-profile.json \
  --output docs/research/evidence/mpc01-external-qps-20261026-r3/strategy-ab-ts01-limited-capture/strategy-ab-ts01-summary.md
```
