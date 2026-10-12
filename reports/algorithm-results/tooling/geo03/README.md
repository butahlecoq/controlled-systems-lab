# GEO-03 report tooling

This tooling collects a versioned descriptive report for the bounded Qhull H/V adapter on the four literal contract fixtures in `hv_conversion_driver.cpp`. It is disabled in ordinary builds; enable it with `-DCSL_BUILD_GEO03_REPORT=ON`. The fixtures are intentionally small and are not a representative workload distribution.

## Reproduction

Configure and build a clean Release tree with CMake, then record the exact source revision, configure/build commands and logs, compiler/CMake versions, executable hash, and dependency pin hashes in a provenance text file. Run `hv_conversion_driver.exe --repetitions 7 --warmups 1` only after checking CPU/load and competing processes. Each case gets one excluded warmup, then seven measured trials; iteration order alternates. The driver independently checks output membership and support values against literal fixture oracles. A failed conversion or oracle aborts collection.

Capture limiter evidence separately from measured trials. On Windows, for example, start `wpr -start CPU -filemode`, run the Release driver with `--profile-rounds 1000`, stop with `wpr -stop <trace.etl>`, and analyze the ETL separately with Windows Performance Analyzer or `xperf`. Record the profiled operation count and the hottest resolved module/function, or state when symbols prevent function attribution. Never include the profile run in trial data.

Run `build_report.py` with the executable, runtime and report source commit IDs, CMake version, build provenance, separate profile notes, and an output path that does not yet exist. It writes raw CSV/JSONL, summaries, saved-data JSON, standalone HTML/SVG, a hashed manifest and an offline ZIP. Then run `python validate_report.py <report-directory>`; the ZIP must sit beside that directory.

The report schema is `csl.geo03-hv-report/1`. Timings describe this adapter and these tiny fixtures only. Numerical membership/support checks are not validated global certificates. The report makes no competitor, speedup, production-size or scaling claim.
