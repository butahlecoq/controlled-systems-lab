# GEO-03 report tooling

This tooling collects a versioned descriptive report for the bounded Qhull H/V adapter on the four literal contract fixtures in `hv_conversion_driver.cpp`. It is disabled in ordinary builds; enable it with `-DCSL_BUILD_GEO03_REPORT=ON`. The fixtures are intentionally small and are not a representative workload distribution.

## Reproduction

From a clean checkout, configure and build the optional driver in Release mode:

```powershell
cmake -S . -B build/geo03-report -G 'Visual Studio 17 2022' -A x64 -DCSL_BUILD_GEO03_REPORT=ON
cmake --build build/geo03-report --config Release --target csl_geo03_conversion_report --parallel 4
```

Record the exact source revision, configure/build commands and logs, compiler/CMake versions, executable hash, and dependency pin hashes in a provenance text file. Run `hv_conversion_driver.exe --repetitions 7 --warmups 1` only after checking CPU/load and competing processes. Each case gets one excluded warmup, then seven measured trials; iteration order alternates. The driver independently checks output membership and support values against literal fixture oracles. A failed conversion or oracle aborts collection.

Capture limiter evidence separately from measured trials. On Windows, for example, start `wpr -start CPU -filemode`, run the Release driver with `--profile-rounds 1000`, stop with `wpr -stop <trace.etl>`, and analyze the ETL separately with Windows Performance Analyzer or `xperf`. Record the profiled operation count and the hottest resolved module/function, or state when symbols prevent function attribution. Never include the profile run in trial data.

Run `python reports/algorithm-results/tooling/geo03/build_report.py` with `--exe build/geo03-report/Release/csl_geo03_conversion_report.exe`, `--repetitions 7`, `--warmups 1`, `--runtime-commit <runtime-sha>`, `--report-commit <report-code-sha>`, `--cmake-version <version>`, `--profile-operations <count>`, `--profile-finding <honest-module-or-function-summary>`, `--profile-summary <profile-notes.txt>`, `--build-provenance <build-provenance.txt>`, and `--out <new-output-directory>`. It writes raw CSV/JSONL, summaries, saved-data JSON, standalone HTML/SVG, a hashed manifest and an offline ZIP. Then run `python reports/algorithm-results/tooling/geo03/validate_report.py <report-directory>`; the ZIP must sit beside that directory.

The report schema is `csl.geo03-hv-report/1`. Timings describe this adapter and these tiny fixtures only. Numerical membership/support checks are not validated global certificates. The report makes no competitor, speedup, production-size or scaling claim. This review artifact is not registered in the shared Pages catalogue; do not claim a hosted URL until issue #148 is integrated and the deployed URL is verified.
