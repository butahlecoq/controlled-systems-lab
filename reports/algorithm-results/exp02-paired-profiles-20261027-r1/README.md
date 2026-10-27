# EXP-02 paired exact-profile slice

This is a partial, descriptive comparison for the exact T-S02 constant-integrator and T-S03 singular-integrator profiles. The run uses one process and one shared setup per profile, one excluded warmup pair, then five measured A/B, B/A alternating pairs. Each timed strategy interval includes family construction, selection, and original-problem verification of two distinct witnesses. Process startup and shared setup are outside those intervals.

## Result

| Profile | Strategy | n | Median (ns) | Range (ns) | Check |
|---|---|---:|---:|---:|---|
| T-S02 constant integrator | csl.synthesis.reach-back | 5 | 5,345,407 | 5,246,581–9,692,986 | pass |
| T-S02 constant integrator | csl.synthesis.strategy-b | 5 | 567,883 | 529,680–706,589 | pass |
| T-S03 singular integrator | csl.synthesis.reach-back | 5 | 4,741,277 | 4,687,079–10,245,155 | pass |
| T-S03 singular integrator | csl.synthesis.strategy-b | 5 | 1,249,958 | 1,234,313–1,297,869 | pass |

The timing medians are descriptive. No winner or bottleneck claim is made: load was not captured before measurement, and this host lacks `perf` and a profiler-instrumented executable. The limiter remains unknown. This is not a scalability result or completion of EXP-02.

## Geometry

The SVG/PNG panels show analytical projections of each complete optimal control family in the `(u₀,u₁)` plane: T-S02 has a constant objective over the square; T-S03 minimizes `(u₁−1)²`, so its optimal set is the upper edge. The figures are derived from the scenario definitions and are separate from sampled witness verification.

## Reproduction and evidence

Run `python3 run.py --executable /absolute/path/to/registered_synthesis_comparison`, then `python3 render_report.py` to regenerate the summary and analytical figures from retained JSONL. The runner refuses to overwrite raw evidence and enforces 300 seconds CPU, 300 seconds wall, and 8 GiB address-space limits over each entire profile process. The outer limits are stricter than the per-attempt contract in scope and should not be read as an observed memory measurement. `raw/` retains JSONL, stdout, stderr, process metadata, scenario hashes, and executable hashes. Process wall times were 0.052113 s (T-S02) and 0.063438 s (T-S03).

The source revision is `2977b95bab581a343c2daba02459f96014e893b0`. The executable was built in Release mode with GCC 16.2.1 (`-O3 -DNDEBUG`), CMake 3.31.6, HiGHS 1.11.0 and Qhull 8.0.2. Its SHA-256 is `300863246730c863d12ddd95090a5d0e0350a3389fb39019dc4e29e6e9274384`. The host was Linux x86_64 with 8 logical CPUs. Load average was checked after the runs (0.18, 1.37, 1.27), not before or during them.

The event rows report numerical assurance. Each completed row reports complete-family verification, two distinct witnesses, and original feasibility/objective verification; optimality assurance remains numerical and no formal proof is claimed.

Issue #94 remains open; this slice does not cover T-S01, the full module substitution matrix, resolved hull/V-H workloads, or source profiling.
