# REVIEW-05 DIMENSION-01 vector-state pilot

This new-comparison experiment crosses state/control dimensions `n=1,2` and
horizons `T=2,4`, with reach-back and Strategy B on the same problem each time:

```text
x[t+1] = x[t] + u[t],  x[0] = 0
0 <= u_i[t] <= 1,  -T <= x_i[t] <= T
minimize sum_i x_i[T]
```

One warmup pair and six alternating measured pairs were attempted per case.
The checker first matches each copied fixture field-for-field against the
analytic case definition, then verifies initial/dynamics/control/state-box rows,
the terminal level, and every candidate H row using exact rational arithmetic. Since
`x_i[T] = sum_t u_i[t]` and each control is nonnegative, the terminal level
`sum_i x_i[T] <= 0` forces every state and control to zero. This proves the
unique optimal-history set only for these four fixtures, not general strategy
completeness.

## Capture outcome

The saved capture has 56 attempts: 49 verified, 7 inconclusive, and zero
incorrect. The seven inconclusive outcomes are reach-back's `operation_rejected`
for `n=2,T=4` across one warmup and six measured calls. Strategy B completed
those calls, but there are no matched verified pairs at that case, so no timing
is summarized there. The other three cases have six of six matched verified
pairs each. Every attempt, raw stdout/stderr, copied fixture, checker result,
summary, build provenance, and checksum is retained.

| State/control dimension | Horizon | Reach-back median (range) | Strategy B median (range) | Verified pairs |
|---:|---:|---:|---:|---:|
| 1 | 2 | 5.284 ms (5.256–5.584) | 0.690 ms (0.685–0.755) | 6/6 |
| 1 | 4 | 11.070 ms (10.857–16.173) | 0.738 ms (0.716–0.963) | 6/6 |
| 2 | 2 | 12.038 ms (11.747–18.077) | 0.756 ms (0.738–0.812) | 6/6 |
| 2 | 4 | not summarized | not summarized | 0/6 |

These are descriptive timings of `SynthesisWorkspace::run()` on the recorded
host. They make no winner, speedup, general performance, or complexity claim.
The factorial fixtures vary dimension, horizon, and explicit stage-state row
count; they do not isolate those factors. Nonzero H coefficients are not
allocated bytes. RSS and internal phase timings were not measured.

The small 2D SVG is analytic fixture geometry: forward reachable squares are
`[0,t]^2`, while backward sets to the selected optimal terminal point and their
intersections are the origin. The figure is an explanatory construction, not a
trace of internal algorithm iterations.

## Reproduction

From the repository root, use the dimension-pilot commands in
[`benchmarks/reporting/review05/README.md`](../../../benchmarks/reporting/review05/README.md).
The original horizon-only scalar pilot is preserved separately in
[`review05-horizon-match-20261031`](../review05-horizon-match-20261031/).
`SHA256SUMS` covers all other files in this report directory.
