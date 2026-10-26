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
| B07 | 8 | 1,024 | 100 | 126.030 ms | 121.036–146.070 ms | 1.260 ms |
| B09 | 2 | 256 | 100 | 5.116 ms | 4.822–6.883 ms | 51.164 µs |

These values characterize only tuple/list coordinate selection for these saved
row counts. They do not estimate geometric projection of a complete polytope,
solver work, materialization overhead, image rendering, or application-scale
performance. B07's rows are ordered `(x1,x3,x2,x4)`; B09's are ordered
`(x1,x2,x3,x4)`.

The separate source profile records 2,000 calls to `project_coordinates` and
attributes 0.111 s of its 0.147 s profiled run to that function. Profiled time
is not used as the reported wall-time measurement. It identifies Python
coordinate selection and tuple creation as the measured operation; no
comparison winner or speedup is claimed.

## Figure export cost

A second probe times the actual B07 and B09 saved-data renderer functions. It
includes loading and hashing their saved rows, generating the figures, writing
SVG and PNG outputs, and writing per-figure export receipts. Each measured call
uses a fresh output directory; one warmup per renderer is excluded, followed by
seven alternating B07/B09 pairs in one warm Python process.

| Renderer | Figures | SVG/PNG/receipt files | Median | Range | Output bytes |
|---|---:|---:|---:|---:|---:|
| B07 (8 saved cases) | 8 | 24 | 5.166 s | 5.126–5.323 s | 3,618,304 |
| B09 (2 objective variants) | 2 | 6 | 1.238 s | 1.228–1.334 s | 461,304 |

The separate profile run shows work distributed across Matplotlib text layout,
SVG serialization and PNG encoding; it does not identify one unique limiter.
The 24 B07 and 6 B09 output hashes are retained for every measured sample. They
match the corresponding files in `docs/examples/viz10/` byte-for-byte. The
figure export time is separate from the coordinate-selection microbenchmark
above. Both are static report-generation measurements from saved data. Neither
includes solving or a geometry query, and the renderer probe excludes the
gallery index and manifest.

## Provenance and reproduction

- Measurement source commit: `d656c41d238b2f6d48b24c291b12ad8a0cdb4c0a` (contains the probe script).
- Renderer source SHA-256: `7d91916425af0f87021bf462a6a155be6af892e31fd90edc946be4e42c9ea141`.
- Probe source SHA-256: `a15a6a36ae85295582abeac6cd504626790f3cde181d9af552dacd50a1995dee`.
- B07 results SHA-256: recorded in `fuel-projection-results.json`.
- B09 results SHA-256: recorded in `fuel-projection-results.json`.
- Host: Linux Omarchy, kernel `7.2.5-3-omarchy`, AMD Ryzen 5 3550H, 8 logical CPUs.
- Python: 3.14.7; initial 1/5/15-minute load averages were 0.60/0.34/0.35.
- All 14 timed samples passed their raw-row projection checks.
- Figure export probe source commit with output hashes: `69adbff15a93c7cac762a5025b672fb2b5cf99e4`.
- Figure export probe source and result hashes are in `fuel-plot-export-results.json`.
- Figure export profile output is `fuel-plot-export-profile.txt`; the profile run is separate from reported times.
- Figure export run load averages before measurement: 0.66/0.53/0.43.

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

Reproduce the figure-export measurements with the same pinned environment:

```sh
<temporary-venv>/bin/python benchmarks/results/review-observability/fuel_plot_export_probe.py \
  --output benchmarks/results/review-observability/fuel-plot-export-results.json \
  --profile-output benchmarks/results/review-observability/fuel-plot-export-profile.txt \
  --temporary-root /dev/shm
```

The probe uses temporary per-run figure directories and removes them when each
sample completes. Its retained records contain the exact raw timing samples,
output sizes, source hashes, environment and profiler hash.
