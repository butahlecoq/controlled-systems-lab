# EXT-02 finite/mixed branch report

The driver evaluates the three catalogue-index branches in
`benchmarks/scenarios/ext02-analytic-two-state-mixed-v1.json`. This is a
one-stage, two-state nominal open-loop example with one continuous control and
one finite control. All three discrete values attain terminal `x1 = 0`; their
terminal `x2` values are `-1`, `0`, and `1`. The saved record retains the
catalogue identity, objective, complete-family verification flag, aggregate
relation rows/scalars, and the timed solve interval.

The timing includes one call to `solve_finite_mixed_branch_portfolio`, including
branch preparation, registered continuous solves, family verification and
portfolio selection. It excludes fixture and registry construction, process
startup, JSON output, plotting, and publication. The structural numeric-byte
count is `retained_relation_scalars * sizeof(double)` for H-matrix coefficients
and right-hand sides; it excludes C++ object/vector overhead, allocator slack,
strategy temporaries, solver workspace, and process RSS. It does not establish
a scalability or performance comparison.

Build and smoke with the HiGHS and Qhull providers enabled:

```sh
cmake --preset highs -DCSL_ENABLE_QHULL=ON -DCSL_BUILD_EXT02_REPORT=ON
cmake --build --preset highs --target csl_ext02_portfolio_report
ctest --test-dir build/highs -R '^ext02_portfolio_report_smoke$' --output-on-failure
```

The collector runs only from a clean pinned Release source commit, preserves
all warmup and measured raw records, captures process RSS samples separately
from the timed interval, and derives the report figure from the saved branch
records. Seven repeated calls describe this one fixture; they are not a
performance comparison or a scalability result.
