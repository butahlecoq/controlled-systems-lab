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

After preparing `build/geo03-report/profile-notes.txt` and `build/geo03-report/build-provenance.txt` as described above, collect and validate with:

```powershell
$runtimeCommit = git rev-parse HEAD
$reportCodeCommit = git rev-parse HEAD
$cmakeVersion = (cmake --version | Select-Object -First 1).Replace('cmake version ', '')
python reports/algorithm-results/tooling/geo03/build_report.py `
  --exe build/geo03-report/Release/csl_geo03_conversion_report.exe `
  --repetitions 7 --warmups 1 `
  --runtime-commit $runtimeCommit --report-commit $reportCodeCommit `
  --cmake-version $cmakeVersion --profile-operations 8000 `
  --profile-finding 'Module-only ETW did not resolve functions; algorithm-stage limiter unresolved.' `
  --profile-summary build/geo03-report/profile-notes.txt `
  --build-provenance build/geo03-report/build-provenance.txt `
  --out build/geo03-report/collection-001
python reports/algorithm-results/tooling/geo03/validate_report.py build/geo03-report/collection-001
```

Output paths must be new. The collector writes raw CSV/JSONL, summaries, saved-data JSON, standalone HTML/SVG, a hashed manifest and an offline ZIP beside the report directory.

If the executable exits nonzero or the measured CSV, scenario roster, adapter identity, or oracle check fails, the collector saves available stdout, stderr, the command, and `collection-status.json` in the requested output directory before exiting nonzero. A failed collection has no accepted `records.json` or ZIP. The saved report's two historical build-log digests cannot be matched to retained log bytes; its `build-provenance.txt` labels that limitation rather than identifying either candidate as the final timed build log.

The report schema is `csl.geo03-hv-report/1`. Timings describe this adapter and these tiny fixtures only. Numerical membership/support checks are not validated global certificates. The report makes no competitor, speedup, production-size or scaling claim. Check the shared Pages catalogue for the current registration state, and verify the deployed URL before claiming that the report is hosted.
