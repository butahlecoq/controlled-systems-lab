# EXP-02 exploratory dyadic hull comparison

This is a first, single-host timing pass for issue #94 and the requested ITIS17 hull methods. It tests whether a dyadic interior-heavy fixture lets the LP adaptations produce exact, checkable reductions. It does not complete EXP-02 or resolve native dependency #86.

## Workload and method

Each fixture is the four corners of the unit square plus deterministic unique interior points on the 1/32 grid. The 64-point and 256-point inputs therefore have the same exact four-vertex hull. The point set is visualized in [`dyadic-interior.svg`](dyadic-interior.svg). Source input hashes, raw warmup and measured rows, validation diagnostics, and executable hash are retained alongside this report.

The Release executable was built from commit `f6a22739ca26480324be2b84b4f9b41da50db140` with GCC 16.2.1 and HiGHS 1.11.0 on an AMD Ryzen 5 3550H laptop (8 logical CPUs). The runs were serial; host load before them was 0.43, 0.49, 0.53. Each method had one warmup and one measured call. Every invocation creates a fresh LP workspace before timing; that workspace serves the LP calls within that invocation. The execution context uses absolute and relative tolerances of `1e-8`; HiGHS uses the simplex solver, primal and dual feasibility tolerances `1e-8`, `threads=1`, `random_seed=0`, `presolve=off`, and `parallel=off`. The fixture generator seed is `0x6d2b79f5`; all coordinates are finite binary64 values. HiGHS was configured for one thread; actual OS thread use was not instrumented. These observations are exploratory, not stable comparative estimates.

## Measured outcomes

| Method | 64 points: ms / retained / passed | 256 points: ms / retained / passed |
|---|---:|---:|
| Geometric QuickHull | 0.157 / 4 / yes | 0.552 / 4 / yes |
| Phase-one basis reuse | 0.215 / 34 / yes | 0.758 / 125 / yes |
| A44 incremental LP adaptation | 7.317 / 4 / yes | 28.097 / 4 / yes |
| A43 certificate-safe basis adaptation | 5.201 / 34 / no | 25.332 / 123 / no |
| LP membership baseline | 10.313 / 64 / no | 70.307 / 255 / no |
| Ordered membership adaptation | 10.555 / 64 / no | 69.628 / 255 / no |

For LP reducers, “yes” means the driver accepted complete status and point accounting, the required verifier ID suffix, coordinate bounds, and the source-index hull check. The driver does not independently recompute each stored removal combination; the current reducer implementations create certificates only after their internal exact check. QuickHull passed its geometric vertex and source-index hull checks. Times for failed rows are diagnostics and must not be compared as successful reduction performance. Basis reuse passed the driver’s checks but retained many interior points. A44 reduced both inputs to the four square corners and passed the driver’s checks. A43 and A44 are paper-informed C++ adaptations, not faithful ports. The archived Pascal baseline remains unavailable in this checkout. This fixture provides an initial comparison between QuickHull and A44, while the baseline, ordered method, and A43 adaptation remain incomplete. One measured repetition is too small to support a general speed or winner claim.

## Reproduce

From the repository root, configure the existing Release report build, build the target, and run:

```sh
cmake -S . -B build/it17-hull-release-r2
cmake --build build/it17-hull-release-r2 --target csl_it17_hull_comparison_report -j2
build/it17-hull-release-r2/csl_it17_hull_comparison_report --dyadic-size 64 --measure 1
build/it17-hull-release-r2/csl_it17_hull_comparison_report --dyadic-size 256 --measure 1
```

This change only extends the exploratory benchmark executable and adds result documentation; it changes no public API, installed dependency, package, or release workflow.
