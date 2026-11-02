# MPC-01 source-mapped CPU profile

This is a diagnostic profile of the MPC-01 native QP runner. It is separate from the saved Release benchmark captures and is **not a timing result**: the binary and all native dependencies were built with GNU `-pg`, and profiling instrumentation changes runtime cost.

## Workload

The runner executed the seven retained MPC-01 fixtures: T-S01, T-S02, singular T-S03, the infeasible and unbounded analytic fixtures, the #421 double integrator, and `b04-reference-v1`. It used 20 repetitions, alternating backend order, with cold and warm-if-available starts. The raw output contains 560 completed attempts: 280 OSQP and 280 HPIPM calls. It is retained to show that the profiled workload ran; its recorded timings must not be compared with production Release records.

## Profile finding

The sampled call graph attributes 91.0% of total profiled call time to `osqp_solve` over 280 calls. Within the sampled CPU profile, `QDLDL_Ltsolve` accounts for 34.52%, `QDLDL_Lsolve` for 22.02%, and `solve_linsys_qdldl` for 11.90%. The dominant path is therefore OSQP's QDLDL sparse linear solve, especially the forward and transpose triangular solves.

The source mapping is:

- QDLDL 0.1.8 `src/qdldl.c`, lines 265–292: `QDLDL_Lsolve` and `QDLDL_Ltsolve` triangular loops.
- OSQP 1.0.0 `algebra/_common/lin_sys/qdldl/qdldl_interface.c`, lines 418–443: `solve_linsys_qdldl` invokes the LDL solve and copies the result.

This is a workload-specific limiter diagnosis. It does not establish a speedup, a solver winner, or the limiter for other fixtures or larger application workloads.

## Build and profile identity

- CSL source: `dd3b260b847325bc5821b70fea7cbe812fbdacfe`.
- Build: GCC 16.2.1, CMake 3.31.6, Ninja, Release optimization plus debug symbols and `-pg`; C, C++, and executable link flags were instrumented. The pinned native solver dependencies were built in that same configuration.
- Dependencies: OSQP 1.0.0, HPIPM `e3a56c1caddd7f12d125d84f337b9a9e5c186271`, BLASFEO `d6251233923c9b475fe894fb729fb63ab693e301`, QDLDL 0.1.8.
- The profiling process was pinned to CPU 0, ran in a Linux cgroup v2 scope with an 8 GiB memory cap and swap disabled, and was guarded by a 300-second process-tree watchdog. These limits describe this diagnostic invocation only.
- The executable SHA-256 is `524758e6e8399991435de39c82d16922d92484dab2fc7746c87c16e57dd8b176`.
- The QDLDL and OSQP source-file SHA-256 values are recorded in `profile-manifest.json`.

`gmon.out` is the raw GNU gprof profile and is interpretable with the recorded executable and GNU gprof 2.47. `gprof-flat-profile.txt` and `gprof-osqp-callgraph.txt` retain the relevant excerpts. `diagnostic-attempts.jsonl` preserves all rows emitted by the instrumented diagnostic run; do not use its timings as benchmark observations.

## Reproduction

From the repository root, configure a separate build with `-DCMAKE_C_FLAGS_RELEASE='-O3 -DNDEBUG -g -pg -fno-omit-frame-pointer'`, `-DCMAKE_CXX_FLAGS_RELEASE='-O3 -DNDEBUG -g -pg -fno-omit-frame-pointer'`, and `-DCMAKE_EXE_LINKER_FLAGS_RELEASE='-pg'`; enable `CSL_BUILD_MPC01_REPORT`, disable HiGHS and Qhull, then build `csl_mpc01_native_dependencies` followed by `csl_mpc01_report`. Run the seven-case report command with `--repetitions 20` in a fresh directory, then invoke `gprof <instrumented-runner> gmon.out`. Keep compiler temporaries on a filesystem with sufficient space; the initial attempt using `/tmp` failed because its quota was exhausted.

The ordinary saved benchmark records remain the source for all solver timing comparisons. The separate profile is only the source-mapped limiter diagnostic required to interpret that comparison.
