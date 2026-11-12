# MPC-01 per-attempt resource capture

Capture window: `2026-11-02T21:40:14.512292+00:00` to `2026-11-02T21:40:41.248634+00:00`.
Host: Linux `7.2.8-9-omarchy`, `x86_64`, AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx, 8 logical CPUs.
Load average before/after: `[0.4814453125, 0.70556640625, 0.91015625]` / `[0.73974609375, 0.7470703125, 0.91796875]` (1, 5, 15 minutes). Hardware details recorded at `2026-11-02T21:41:29.256231+00:00`.
Source revision: `452db1ceb0312607fe7791b5ff4d84a2730df6ff` plus the source-file hashes in `build-identity.json`.
Build: Release with `GNU 16.2.1`; executable SHA-256 `7e33a46cab540882ba84aecf23649c6c7aa81b143a2fe8bb36dbf66178ef0dc7`.

The run retained 140 of 140 native attempts and 7 canonical comparison records. Each attempt ran sequentially in its own systemd user scope with an enforced 300-second process-tree watchdog, an 8 GiB cgroup-v2 memory cap, swap disabled, one CPU quota and one pinned logical CPU. The host has 7.55 GiB physical RAM, below the configured per-attempt cgroup maximum; observed use stayed small, with a largest process-tree peak of 12,173,312 bytes. No attempt timed out, failed, or recorded memory OOM events.

The independent exact-rational checker verified feasibility and objective bounds for 90 native attempts classified as optimal. Native solver classifications for singular, infeasible and unbounded cases remain separate; non-optimal attempts are retained in `attempts.jsonl` and their canonical records.

A separate [source-mapped gprof limiter profile](../mpc01-source-mapped-profile-20261102/README.md) attributes sampled OSQP time to QDLDL triangular solves on its 20-repetition workload. It was instrumented with `-pg` and is excluded from these Release timings; the current measurements do not establish a general limiter outside that workload.

Solve timings below are native solver phase timings, reported as descriptive medians and ranges of five repetitions per fixture/arm. Warm attempts include a same-process cold seed solve inside their attempt resource budget; the seed solve time is retained separately in each event. These rows do not establish a general solver winner or end-to-end MPC latency.

| Fixture | Solver | Start mode | Completed / outcomes | Solve median (ms) | Solve range (ms) | Attempt process median (ms) |
|---|---|---|---:|---:|---:|---:|
| `b04-reference-v1` | `hpipm-structured-ocp-qp` | `cold` | 5 (optimal: 5) | 1.505027 | 1.239277–1.762814 | 8.333 |
| `b04-reference-v1` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (optimal: 5) | 0.284885 | 0.272384–0.298994 | 6.608 |
| `b04-reference-v1` | `osqp-sparse-qp` | `cold` | 5 (optimal: 5) | 162.758902 | 161.904588–164.110133 | 169.269 |
| `b04-reference-v1` | `osqp-sparse-qp` | `warm_if_available` | 5 (optimal: 5) | 0.134027 | 0.133119–0.134795 | 169.877 |
| `double-integrator-421` | `hpipm-structured-ocp-qp` | `cold` | 5 (optimal: 5) | 0.074871 | 0.072566–0.100014 | 5.484 |
| `double-integrator-421` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (optimal: 5) | 0.016692 | 0.015225–0.022070 | 5.160 |
| `double-integrator-421` | `osqp-sparse-qp` | `cold` | 5 (optimal: 5) | 0.150510 | 0.112376–0.208059 | 5.293 |
| `double-integrator-421` | `osqp-sparse-qp` | `warm_if_available` | 5 (optimal: 5) | 0.052312 | 0.051962–0.057271 | 4.972 |
| `infeasible` | `hpipm-structured-ocp-qp` | `cold` | 5 (undetermined: 5) | 0.100084 | 0.080947–0.166783 | 4.646 |
| `infeasible` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (undetermined: 5) | 0.049308 | 0.042883–0.079690 | 6.400 |
| `infeasible` | `osqp-sparse-qp` | `cold` | 5 (infeasible: 5) | 0.057969 | 0.055804–0.070610 | 4.415 |
| `infeasible` | `osqp-sparse-qp` | `warm_if_available` | 5 (infeasible: 5) | 0.131233 | 0.126344–0.243958 | 4.558 |
| `ts01` | `hpipm-structured-ocp-qp` | `cold` | 5 (optimal: 5) | 0.084928 | 0.074173–0.123830 | 4.522 |
| `ts01` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (optimal: 5) | 0.025771 | 0.012362–0.025842 | 5.277 |
| `ts01` | `osqp-sparse-qp` | `cold` | 5 (optimal: 5) | 0.112097 | 0.094007–0.138217 | 4.492 |
| `ts01` | `osqp-sparse-qp` | `warm_if_available` | 5 (optimal: 5) | 0.064395 | 0.046375–0.129277 | 6.131 |
| `ts02` | `hpipm-structured-ocp-qp` | `cold` | 5 (optimal: 5) | 0.091423 | 0.053918–0.128789 | 5.009 |
| `ts02` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (optimal: 5) | 0.018648 | 0.012432–0.020673 | 5.094 |
| `ts02` | `osqp-sparse-qp` | `cold` | 5 (optimal: 5) | 0.084998 | 0.057690–0.101411 | 4.958 |
| `ts02` | `osqp-sparse-qp` | `warm_if_available` | 5 (optimal: 5) | 0.071518 | 0.048330–0.087163 | 5.738 |
| `ts03-singular` | `hpipm-structured-ocp-qp` | `cold` | 5 (undetermined: 5) | 4.328532 | 3.277828–5.645683 | 9.533 |
| `ts03-singular` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (undetermined: 5) | 3.035895 | 3.026676–3.431689 | 11.384 |
| `ts03-singular` | `osqp-sparse-qp` | `cold` | 5 (optimal: 5) | 0.231945 | 0.188853–0.335801 | 4.520 |
| `ts03-singular` | `osqp-sparse-qp` | `warm_if_available` | 5 (optimal: 5) | 0.083741 | 0.066699–0.118243 | 6.331 |
| `unbounded` | `hpipm-structured-ocp-qp` | `cold` | 5 (undetermined: 5) | 0.065721 | 0.052801–0.101411 | 5.301 |
| `unbounded` | `hpipm-structured-ocp-qp` | `warm_if_available` | 5 (undetermined: 5) | 0.012711 | 0.010826–0.014457 | 4.668 |
| `unbounded` | `osqp-sparse-qp` | `cold` | 5 (unbounded: 5) | 0.063626 | 0.060204–0.109023 | 4.748 |
| `unbounded` | `osqp-sparse-qp` | `warm_if_available` | 5 (unbounded: 5) | 0.128788 | 0.084229–0.160358 | 6.057 |

## Artifacts

- `attempts.jsonl`: one resource and outcome record per attempt, including stdout/stderr hashes and cgroup counters.
- `comparison-records.jsonl`: seven validated canonical records; each measurement payload binds its resource receipt.
- `native-attempts.jsonl`: source rows used by the exact checker and record builder.
- `exact-candidate-checks.jsonl` and `exact-check-manifest.json`: independent rational feasibility/objective checks.
- `exact-checker-resource-profile.json`: separate five-second checker budget and resource accounting.
- [B04 2D projection (HTML)](b04-repeated-projections.html) and [SVG](b04-repeated-projections.svg): representative saved solver paths in the `(x1,x2)` oxidizer and `(x3,x4)` fuel planes, alongside the exact reference witness.
- `SHA256SUMS`: bundle integrity manifest.
