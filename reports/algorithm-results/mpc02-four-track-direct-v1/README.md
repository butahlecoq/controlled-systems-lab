# MPC-02 four-track direct-joint measurement

This bundle measures the same Release HiGHS convex adapter on the four authored
MPC-02 scenarios. Each track uses one warmup and seven non-warmup attempts.
Every returned witness and objective is checked against the independent
Fraction oracle in `tests/reporting/test_mpc02_four_track_independent_oracle.py`.

This is descriptive evidence for four direct joint formulations. It does not
rank solvers, compare hosts, or claim a general performance winner. The earlier
[`mpc02-slew-formulation-v1`](../mpc02-slew-formulation-v1/README.md) bundle
remains the separate direct-versus-exact-slew-lift comparison; this bundle does
not invent a lift for the L1 history rows.

| Scenario | Variables | Rows | Median assembly (ns) | Median prepare (ns) | Median solve (ns) | Exact witness | Exact objective |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `mpc02-unconstrained-2d-v1` | 8 | 6 | 37,156 | 9,498 | 1,699,952 | `(1/2, 0)` | `0` |
| `mpc02-stage-box-2d-v1` | 8 | 10 | 39,531 | 9,987 | 1,845,083 | `(1/2, 0)` | `0` |
| `mpc02-slew-2d-v1` | 8 | 11 | 14,318 | 4,819 | 741,720 | `(3/8, 1/8)` | `1/32` |
| `mpc02-l1-budget-2d-v1` | 8 | 14 | 14,248 | 4,819 | 754,362 | `(1/4, 0)` | `1/16` |

The clean source checkout was commit
`b1ed6d8213b977dd7960dc493365c1d7896254bd`, built as Release with GCC
16.2.1, using `csl.convex.highs@1.0.0+highs.1.11.0`. All 32 attempts passed
with zero reported solver residual. Timings are nanoseconds from one host and
include no CPU/RSS quota or hardware-counter profile; retain them as a baseline
for later matched comparisons, not as an optimization conclusion.

Reproduction from a clean checkout:

```sh
cmake -S benchmarks/reporting/mpc02/runner -B build/mpc02-four-track \
  -DCMAKE_BUILD_TYPE=Release -DCSL_SOURCE_ROOT="$PWD"
cmake --build build/mpc02-four-track --parallel 4
build/mpc02-four-track/csl_mpc02_four_track_measure \
  reports/algorithm-results/mpc02-four-track-direct-v1 \
  examples/scenarios/mpc02-unconstrained-2d.json \
  examples/scenarios/mpc02-stage-box-2d.json \
  examples/scenarios/mpc02-slew-2d.json \
  examples/scenarios/mpc02-l1-budget-2d.json
```

The raw event stream is [`events.jsonl`](events.jsonl), with SHA-256
`c44c957c95e591971a43a360c58743408448e30ed315dddd214af66d94c219c7`.
