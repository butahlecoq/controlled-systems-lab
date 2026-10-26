# OBS-06 fuel minimax phase timing

This evidence bundle adds solver phase timings to the existing B06, B07 and
B09 fuel cases. It introduces no historical reproduction, validated-arithmetic,
speedup or strategy-winner claim.

## Captures

The raw records contain 28,128 spans for B06, 28,128 spans for each of the
eight B07 cases, and 52,491 spans for each B09 lambda case. Each record retains
its raw wall endpoints, wall-clock ticks and period, parent ID/kind, execution
status, phase status, and inclusive/exclusive wall metrics. The phase table reports planned
`span_count` separately from actual `call_count`; not-called phases are not
zero-duration calls. Summed per-operation values are work totals across spans,
not elapsed time across operations. Nested inclusive values overlap and must
not be added.

B06 and both B09 pairs use one uninstrumented call followed by one instrumented
call, with no warmup. B07 uses one excluded warmup and seven uninstrumented
measurements per case, followed by one instrumented call. Numerical success
fields match exactly. B06 also checks an unsupported-capacity failure pair and
retains its raw failure-path spans. Collection uses one outer worker; this
solver has no external numerical backend. CPU time and worker work are
unavailable because no CPU clock or worker spans were supplied. The capture
manifest includes environment facts, source identity, executable hashes,
scenario/driver hashes and pair ordering.

The independent B06 exact enumeration, B07 eight-case corner-history oracle,
and B09 direct action/corner-history oracle are included. B09 geometry records
also preserve the nonlinear open-loop and receding-horizon replay results and
the outside-solver geometry/replay measurements. JSON serialization timing is
reported separately from the solver interval. Figure export is not part of
these solver-phase captures. The separate
[`postprocess-timings.json`](postprocess-timings.json) records one process-level
wall interval each for independent oracles, saved-data report/figure exports,
and summary generation. These include process startup and output writes and
are single observations, not performance comparisons.

For these postprocessing invocations, B06 exact-oracle verification took
31.8 ms; B07 independent verification took 4.06 s; and B09 direct verification
took 6.10 s. Saved-data exports took 52.3 ms for B06, 6.25 s for the B07
Matplotlib gallery, and 65.9/64.3 ms for B09 lambda 0/1. Regenerating the
96-row timing table took 5.33 s. Those wall intervals include tool startup and
file writes; they do not overlap the solver phase timings above.

## 4D fuel model projections

These plots show two 2D projections of saved terminal rows from the four-state
fuel model. They are explanatory geometry, not timing plots.

- [B06 4D terminal projections](../b06-owner-confirmed-7df01ba3af5e4c46/terminal-projections.svg)
- [B07 flow and stock projections across eight cases](../b07-owner-approved-eight-case-v1/projections.svg)
- [B09 lambda 0 projections and replay](projections-lambda0.svg)
- [B09 lambda 1 projections and replay](projections-lambda1.svg)

## Reproduction

Build the three Release report executables plus the dedicated B06 phase driver with the options in
[`benchmarks/reporting/issue6/README.md`](../../../benchmarks/reporting/issue6/README.md).
Run each executable with `--phase-timing`, retaining stdout as the matching
raw JSON/JSONL file. Regenerate the table with:

```sh
build/csl_issue6_b06_phase_report --phase-timing > raw/b06-phase.json
build/csl_issue6_b07_report --phase-timing > raw/b07-phase.jsonl
build/csl_issue6_b09_report --lambda 0 --phase-timing > raw/b09-lambda0-phase.json
build/csl_issue6_b09_report --lambda 1 --phase-timing > raw/b09-lambda1-phase.json
python3 benchmarks/reporting/issue6/fuel_phase_summary.py \
  raw/b06-phase.json raw/b07-phase.jsonl \
  raw/b09-lambda0-phase.json raw/b09-lambda1-phase.json \
  --output phase-summary.csv --provenance capture-provenance.json
```

The CSV and Markdown table are generated from the compressed raw spans. Verify
bundle bytes against `SHA256SUMS` before relying on the capture.
