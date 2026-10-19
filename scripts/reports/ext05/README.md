# EXT-05 continuous-model report

The native driver calls the public `model::discretize`, `model::snapshot` and
two state steps on a two-dimensional double integrator. It checks the analytic
zero-order-hold transition matrices and trajectory during every timed call.

From a separate clean worktree at the frozen numerical source commit:

```sh
python scripts/reports/ext05/capture.py --source <clean-source> --capture <fresh-capture> --commit <frozen-commit> --cmake <cmake-executable>
python scripts/reports/ext05/collect.py --capture <fresh-capture> --source <clean-source> --out reports/algorithm-results
python scripts/reports/ext05/render_saved.py --bundle reports/algorithm-results/<report-id>
python scripts/reports/ext05/render_saved.py --bundle reports/algorithm-results/<report-id> --check
python scripts/reports/stage_ext05.py --source reports/algorithm-results/<report-id>
```

The capture retains clean prebuild and postrun source receipts, build logs,
CMake configuration, compiler file, executable hash, host metadata, one smoke
row, an excluded warmup and seven measured batches. The collector checks all
rows against literal analytic values before saving a versioned record. The
renderer reconstructs HTML, CSV, SVG, manifest and offline ZIP from saved
bytes alone. The stager accepts one reviewed catalogue entry and the exact
allowlisted bundle into the main-only Pages workflow.

Batch duration includes fixture construction, public conversion, snapshot,
two state steps and literal checks. It excludes CSV output and rendering.
This is descriptive single-adapter timing on one host; no speedup or certified
global error bound follows from it.

The accepted clean source is `c1125dc393c84015a289dbb97c3bfc5f8b225673`.
Its capture is retained outside the repository at
`D:\work\PhD\captures\ext05-capture-20261019-v2`; the first capture at
`D:\work\PhD\captures\ext05-capture-20261019` was superseded because its
timing-scope text omitted fixture construction. The published candidate is
`ext05-discretization-e86c11adbd999b2d`. The capture paths are audit inputs,
not runtime or install dependencies.
