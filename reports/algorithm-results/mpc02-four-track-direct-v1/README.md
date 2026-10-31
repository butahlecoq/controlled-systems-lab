# MPC-02 four-track direct-joint measurement

This bundle measures the same Release HiGHS convex adapter on the four authored
MPC-02 scenarios. Each track uses one warmup and seven non-warmup attempts.
Every returned witness and objective is retained in the raw event stream and
checked against the independent Fraction oracle in
`tests/reporting/test_mpc02_four_track_independent_oracle.py`.

This is descriptive evidence for four direct joint formulations. It does not
rank solvers, compare hosts, or claim a general performance winner. The earlier
[`mpc02-slew-formulation-v1`](../mpc02-slew-formulation-v1/README.md) bundle
remains the separate direct-versus-exact-slew-lift comparison; this bundle does
not invent a lift for the L1 history rows.

| Scenario | Variables | Rows | Median assembly (ns) | Median prepare (ns) | Median solve (ns) | Exact witness | Exact objective |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `mpc02-unconstrained-2d-v1` | 8 | 6 | 30,101 | 8,521 | 1,589,672 | `(1/2, 0)` | `0` |
| `mpc02-stage-box-2d-v1` | 8 | 10 | 12,991 | 4,680 | 672,927 | `(1/2, 0)` | `0` |
| `mpc02-slew-2d-v1` | 8 | 11 | 13,479 | 4,749 | 715,879 | `(3/8, 1/8)` | `1/32` |
| `mpc02-l1-budget-2d-v1` | 8 | 14 | 14,877 | 4,680 | 757,645 | `(1/4, 0)` | `1/16` |

The clean source checkout was commit
`b1ed6d8213b977dd7960dc493365c1d7896254bd`, built as Release with GCC
16.2.1, using `csl.convex.highs@1.0.0+highs.1.11.0`. All 32 attempts passed
with zero reported solver residual. Timings are nanoseconds from one host and
include no CPU/RSS quota or hardware-counter profile; retain them as a baseline
for later matched comparisons, not as an optimization conclusion.

The raw event stream is [`events.jsonl`](events.jsonl), with SHA-256
`eebeef0ed8da0ea5895c3494acd5c9812df8fb39c2ad798ddcc1bd5d113cab2b`.
