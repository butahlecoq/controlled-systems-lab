# B04 native smoke projection

This directory preserves one cold smoke attempt from OSQP and one from HPIPM
on the separate `b04-reference-v1` input. The `native-smoke-projections.svg`
and `.html` files project each returned four-state trajectory into the flow
plane and working-stock plane, beside the exact saved reference witness.

This is an illustration from a single process run, not a repeated benchmark or
a canonical comparison record. The solver rows report `optimal` native
statuses, but their binary64 original-data residual checks remain
`inconclusive`; the exact rational witness independently establishes the
global optimum for this frozen input. This is not a reconstruction or result
claim for historical B04. The working-stock coordinates have no declared
bounds, so negative values are shown. Flow bounds apply only at stages 0 and
16, as specified by the input.

The original norm values in the rows are 160.88245893063822 for OSQP and
160.8806539454904 for HPIPM. These are single-smoke values and are not a solver
ranking. The exact saved optimum is 160.88065394552709.

## Reproduce

Regenerate the figure from the preserved, digest-pinned attempt rows:

```sh
python3 scripts/reports/mpc01/b04_native_smoke_projection.py
```

To produce a new smoke capture, build the optional runner as described in
[`benchmarks/reporting/mpc01/README.md`](../../../../../benchmarks/reporting/mpc01/README.md),
save its full output to a new file, extract the two cold B04 rows to another
new file, then pass that file with `--attempts` and choose a fresh
`--output-dir`. This leaves the pinned rows and figure unchanged. Pass a
machine-readable `--manifest` to bind the new case digest, attempt digest and
runner source commit; without one, the generated page labels the runner source
as unrecorded.

The figure generator checks the case digest against [`manifest.json`](manifest.json),
checks that the attempt-file SHA-256 matches it, and validates solver
identities, cold-start mode, state/control dimensions, outcome fields and
inconclusive residual labels before rendering. Attempt rows SHA-256:
`1ce79daf8a56c4dcce86dade4f6a1cb478f380c3ed4480015d84fee901ec2ed0`.
The runner source commit for the preserved rows is
`9202df9aca690d9c83c780eb6e255c3f87473fd9`.
