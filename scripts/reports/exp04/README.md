# EXP-04 independent plant replay report

The immutable numerical driver source is commit
`eb4497e08f1532c732163e677d5d7aa03697c7de`. The four authored histories
use exact discrete plant callbacks; none is a recovered B04 trajectory.
The [saved bundle](../../../reports/algorithm-results/exp04-replay-93fe3b87795e1d3a/)
contains its raw smoke and measurement CSV, complete input declarations,
clean prebuild/postrun source receipts, raw configure/build and CMake compiler
records, host/build provenance, a two-state SVG, HTML, file manifest and offline ZIP.

To reproduce on a clean checkout at that source commit, configure a fresh
Release build with `BUILD_TESTING=OFF`, `CSL_ENABLE_HIGHS=OFF`,
`CSL_ENABLE_QHULL=OFF` and `CSL_BUILD_EXP04_REPORT=ON`. Build
`csl_exp04_replay_report`, then run it with `smoke` and `measure`. The measurement
capture used the MSBuild property `/p:PreferredUILang=en-US` and English UI
environment settings so its retained raw build log is in English. The measurement
uses one excluded 1,000-call warmup batch per case and seven rotated 1,000-call
measured batches per case. Every call must pass the literal trajectory and
objective checks. The duration is the sum of `ReplayRecord.replay_time` for the
1,000 public calls; it excludes the post-call checks and process/report work.

`collect.py` admits a frozen local capture without running native work. Its
source and executable receipt inputs are documented by `--help`. Once captured,
regenerate and verify the saved page with:

```sh
python scripts/reports/exp04/render_saved.py --bundle reports/algorithm-results/exp04-replay-93fe3b87795e1d3a --check
python scripts/reports/stage_exp04.py --source reports/algorithm-results/exp04-replay-93fe3b87795e1d3a
python -m unittest discover -s tests/reporting -p test_exp04.py
```

The last `stage_exp04.py` command prints the exact extension catalog. Main-only
Pages staging checks that catalog against the saved bundle and renderer bytes.
These are descriptive single-adapter timings with no comparator, speedup or
source-mapped limiter claim. The original plant callback and its provenance
are declared inputs, not independent proof of a historical physical model or
validated rounding bound.
