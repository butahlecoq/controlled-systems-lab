# B08 comparison-record archive

This directory contains a derived `csl.comparison-record/1` archive for the frozen B08 L04 displayed-data run. The record has two arms and one capture per arm: the finite-action MIQCP and the continuous-control QCP relaxation. It retains exact input, solver, and rational-oracle evidence plus the existing disturbance-tube figure.

The QCP uses a different feasible set from the finite action problem. Its lower bound is recorded separately and its mathematical outcome is undetermined. Solver termination is retained as a separate field. This is one exploratory capture per formulation and supports no timing ranking.

The B08 model has four state coordinates. The saved figure projects all disturbance-corner histories to `(x1,x3)` and marks the target and worst terminal point. Its SHA-256 and source path are in `manifest.json`; the SVG bytes are also attached to each run in `comparison-record.json`.

Regenerate the record from the unchanged source bundle with:

```sh
cmake --build <build-dir> --target csl_mpc03_b08_comparison_record
<build-dir>/csl_mpc03_b08_comparison_record \
  reports/algorithm-results/mpc03-b08-l04-miQCP-v1 \
  /tmp/b08-comparison-record.json
```

The output is deterministic. The adapter validates the saved input hashes and uses the production run and comparison codecs; it never reruns SCIP or overwrites the frozen source bundle.
