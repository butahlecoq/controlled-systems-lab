# OBS-05 saved performance tables

`scripts/reports/obs04/export_tables.py` exports a validated
`csl.comparison-record/1` without invoking a solver, selector, or provider. Its
input record is copied byte-for-byte into the new output directory and sealed
in `manifest.json` with its SHA-256. The destination must not already exist.

```sh
python scripts/reports/obs04/export_tables.py \
  --record path/to/comparison-record.json \
  --out-dir build/obs05-export
```

The output contains:

| File | Contents |
| --- | --- |
| `comparison-record.json` | The unmodified source record. |
| `attempts.csv` | Every warm-up and measured attempt, status, run identity and recorded run-level measurements. Structured final result, selection evidence, resource observation and the complete event payload remain as JSON columns so objective conventions, residuals, evidence and failure detail accompany timing without being recomputed. |
| `phase-summary.csv` | Per-arm phase summaries over measured attempts only. |
| `module-spans.csv` | Every persisted module span, parentage, status, termination, clock, iteration and representation-size availability. |
| `module-summary.csv` | Per-arm, per-operation planned span count, returned/known-not-called/unknown execution counts, total and distribution of inclusive duration, plus exclusive duration counts, medians and p95 values. |
| `manifest.json` | Export schema, input identities, byte-preservation hash and metric semantics. |

The record track is carried into the manifest and attempt rows. Historical
reported values remain in their separately labelled source records; this
comparison-record exporter does not merge those values into measured attempts.

The timing tail is nearest-rank p95: sort the available values and select
one-based rank `ceil(0.95 * n)`. Each phase uses its own saved metric. Module
durations convert persisted integer clock ticks using that clock's saved
period and retain exact rational nanoseconds where the period does not yield an
integer. Exclusive wall duration subtracts the union of recorded descendant
intervals clipped to the span; it is unavailable when the span or a descendant
interval is incomplete or uses a different clock. Span rows are observations,
not additive phases: nested and overlapping worker durations are never summed
into run latency. `total_inclusive_ns` sums available per-attempt spans within
one operation row; it is operation work across those observations, not
end-to-end latency, and callers must not sum it across nested operation rows.
Aggregate worker-work and per-span CPU/work are unavailable because the current
saved schema does not record their selection or scope. Summary values include
measured attempts only; `attempts.csv` and `module-spans.csv` retain warm-ups,
failed or stopped attempts, and unavailable values.

Run-level process CPU and peak RSS preserve the metric scope/status and missing
reason in `attempts.csv`. The current run-statistics schema does not expose
per-module CPU or memory; `module-spans.csv` marks those metrics unavailable
with that reason. The event schema also does not provide separate setup or plot
export measurements in every record. These remain unavailable with an explicit
reason instead of being represented as zero. The source record retains the
complete raw provenance and payload needed by another tool.
