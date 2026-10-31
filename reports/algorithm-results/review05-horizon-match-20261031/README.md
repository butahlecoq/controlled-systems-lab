# REVIEW-05 HORIZON-01 scalar horizon pilot

This report captures a matched horizon ladder for the scalar integrator
`x[t+1] = x[t] + u[t]`, `x[0] = 0`, `0 <= u[t] <= 1`, minimizing `x[T]`.
It runs reach-back and Strategy B at horizons 2, 4, and 8. Each horizon has
one excluded warmup pair and six measured alternating pairs. The timed region
is `SynthesisWorkspace::run()`; launch and setup are excluded.

The exact fixture-specific checker accepted all 42 attempts: 6 warmups and 36
measured runs, with 18/18 measured pairs verified. It independently checks the
emitted H relations against exact dyadic/rational constraints. Since
`x[T] = sum(u[t])`, `u[t] >= 0`, and the candidate terminal level is at most
zero, each fixture's emitted set is exactly the singleton all-zero optimal
history. This does not establish either strategy's general completeness.

## Matched timing summary

| Horizon | Reach-back median (range) | Strategy B median (range) |
|---:|---:|---:|
| 2 | 5.271 ms (5.223–11.189) | 0.658 ms (0.645–0.682) |
| 4 | 10.856 ms (10.701–11.094) | 0.717 ms (0.672–0.807) |
| 8 | 22.909 ms (22.350–23.156) | 0.742 ms (0.725–0.765) |

These are descriptive observations for this host and fixture. They make no
winner, speedup, general performance, or complexity claim. The ladder changes
the horizon and resulting relation size while state and control dimensions
remain one; it does not separately vary constraints per stage. H coefficient
counts are not allocated-byte measurements. RSS and internal phase timings
were not collected. See `summary.json`, `attempts.jsonl`, `checks.jsonl`, and
`raw/` for complete records.

The fixture is scalar and has no supported two-dimensional state-set plot.
The separate 4D fuel model's projections should be labeled `(x1, x2)` for
oxidizer and `(x3, x4)` for fuel; those plots are outside this scalar pilot.

## Reproduction

From the repository root, follow the build and replay commands in
[`benchmarks/reporting/review05/README.md`](../../../benchmarks/reporting/review05/README.md).
The captured build configuration, dependency versions, binary digest, compiler,
and run limits are recorded in `build-provenance.json` and `manifest.json`.
`SHA256SUMS` covers every other file in this report directory.
