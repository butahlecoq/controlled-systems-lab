# REVIEW-07 saved fuel projection probe

This probe measures only the coordinate selection used to create the B07 and
B09 flow and stock plot data from their saved four-state terminal rows. It does
not run a solver, a geometry query, Matplotlib, image export, or report
rendering. The result is therefore a projection data-preparation microbenchmark,
not solver latency or end-to-end plotting cost.

## Measurement

The probe used seven alternating B07/B09 pairs after one excluded warmup per
workload. Every measured sample makes 100 passes over the complete saved
workload, builds both coordinate pairs for every row, and checks the last
projected result against literal coordinate selection from the input rows.
Input files are loaded and decoded before timing. Measurements use one process
and one thread; the arrays and Python runtime are warm. The separate cProfile
run is not included in the timings.

| Saved workload | Cases | Rows per case | Timed passes per sample | Median batch | Range | Derived median per pass |
|---|---:|---:|---:|---:|---:|---:|
| B07 | 8 | 1,024 | 100 | 128.123 ms | 124.654–145.455 ms | 1.281 ms |
| B09 | 2 | 256 | 100 | 5.159 ms | 4.865–5.194 ms | 51.587 µs |

These values characterize only tuple/list coordinate selection for these saved
row counts. They do not estimate geometric projection of a complete polytope,
solver work, materialization overhead, image rendering, or application-scale
performance. B07's rows are ordered `(x1,x3,x2,x4)`; B09's are ordered
`(x1,x2,x3,x4)`.

The separate source profile records 2,000 calls to `project_coordinates` and
attributes 0.114 s of its 0.153 s profiled run to that function. Profiled time
is not used as the reported wall-time measurement. It identifies Python
coordinate selection and tuple creation as the measured operation; no
comparison winner or speedup is claimed.

## Provenance and reproduction

- Measurement source commit: `c4f0795a23d3943e2c4402ea9531cfbbd723861f`.
- Renderer source SHA-256: `7d91916425af0f87021bf462a6a155be6af892e31fd90edc946be4e42c9ea141`.
- Probe source SHA-256: `a15a6a36ae85295582abeac6cd504626790f3cde181d9af552dacd50a1995dee`.
- B07 results SHA-256: recorded in `fuel-projection-results.json`.
- B09 results SHA-256: recorded in `fuel-projection-results.json`.
- Host: Linux Omarchy, kernel `7.2.5-3-omarchy`, AMD Ryzen 5 3550H, 8 logical CPUs.
- Python: 3.14.7; initial 1/5/15-minute load averages were 0.30/0.29/0.34.
- All 14 timed samples passed their raw-row projection checks.

Reproduce with the repository's pinned reporting dependencies:

```sh
python3 -m venv <temporary-venv>
<temporary-venv>/bin/python -m pip install -r scripts/reports/requirements.txt
<temporary-venv>/bin/python benchmarks/results/review-observability/fuel_projection_probe.py \
  --output benchmarks/results/review-observability/fuel-projection-results.json \
  --profile-output benchmarks/results/review-observability/fuel-projection-profile.txt \
  --iterations 100
```

The raw sample order, environment, input hashes, source hashes and scope limits
are in `fuel-projection-results.json`; the separate profiler output is in
`fuel-projection-profile.txt`.
