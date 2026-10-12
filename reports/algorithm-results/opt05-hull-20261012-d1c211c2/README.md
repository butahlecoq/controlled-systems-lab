# OPT-05 LP-backed hull reducer report

This report records one implementation and one deterministic workload family: finite points on 5x5, 9x9, and 13x13 square lattices. The measured implementation is `CSL::geometry::reduce_hull` at source commit `d1c211c2763989a9cf3e39a8acaf609c5cf33a07`, using the HiGHS 1.11.0 LP adapter. This is descriptive data, not a comparison or speedup claim.

Open `index.html` locally for the rendered report. The JSON and CSV files beside it are the primary accepted data; `evidence/accepted-002/` retains the exact timed harness source, raw process output, sanitized compiler log, host-overlap note and derived records. `profile/README.md` documents the separately built sampling profile. `evidence/accepted-001/` is an earlier exploratory run and is superseded by accepted-002; do not combine its trials with the accepted measurement.

## Accepted measurement

The timed interval is only `reduce_hull`; input generation, LP registration and workspace construction are outside it. Lazy HiGHS initialization on first use is inside the call. A fresh workspace is created for each invocation. Cases are interleaved in round-robin order; each has one warmup and seven measured trials. All 21 measured trials returned complete results and passed the fixture oracle; there were zero failed trials and zero unsupported, stopped, numerical-failure, or malformed outcomes. LP calls equaled input point count in every trial.

| Grid | Points | Median | Observed range | LP calls / trial | Removed / retained |
|---|---:|---:|---:|---:|---:|
| 5x5 | 25 | 2.1357 ms | 2.0977–2.1607 ms | 25 | 21 / 4 |
| 9x9 | 81 | 7.9319 ms | 7.6351–8.3261 ms | 81 | 77 / 4 |
| 13x13 | 169 | 18.9077 ms | 18.7140–19.3865 ms | 169 | 165 / 4 |

The oracle checks the four square-corner IDs, all returned barycentric certificates against original coordinates, complete status and the LP-call/attempt count. This is a binary64 tolerance check, not a proof of exact or validated hull equality. No other reducer or solver was measured. These cases do not represent the fuel-consumption application or establish scaling behavior outside this narrow two-dimensional workload.

## Environment and provenance

- Windows 11 build 22631; Intel Core i5-12400F (6 cores / 12 logical processors); 33,387,800 KiB visible RAM.
- Visual Studio 17 2022 x64, MSVC 19.44.35215.0, C++20, CMake 3.31.6-msvc6, HiGHS 1.11.0.
- Release compile command included `/O2 /Ob2 /D NDEBUG /MD /fp:precise /std:c++20`; HiGHS was configured for one thread, simplex, presolve off and parallel off.
- The accepted executable SHA-256 and build-log SHA-256 are in `evidence/accepted-002/build-provenance.json`. Its saved harness SHA-256 matches `evidence/accepted-002/hull_measure.cpp`. The executable is not bundled; the timed build output was overwritten when the separate symbol-enabled profile binary was built.
- Six MSBuild processes remained from other worktrees before collection. Each had zero CPU-time delta during a five-second check; no `cl.exe` was present. There was no observed overlapping build activity during measurement. Pre/post CPU snapshots are recorded; unrelated background load cannot be ruled out.

## Reproduction and validation

Run from the repository root in a Visual Studio developer PowerShell with Python 3.13.5, CMake 3.31.6, HiGHS 1.11.0 available. The exact measured configuration and timed harness are retained in `harness/` and `evidence/accepted-002/`.

```powershell
cmake -S reports/algorithm-results/opt05-hull-20261012-d1c211c2/harness -B build-opt05-harness -G "Visual Studio 17 2022" -A x64 -DCSL_ROOT="$PWD" -DCMAKE_PREFIX_PATH="$PWD/build"
cmake --build build-opt05-harness --config Release --target csl_hull_measure --parallel 4 --verbose
python reports/algorithm-results/opt05-hull-20261012-d1c211c2/collect.py --exe build-opt05-harness/Release/csl_hull_measure.exe --out reports/algorithm-results/opt05-hull-20261012-d1c211c2/evidence/reproduced
cmake -S . -B build-opt05-results -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTING=ON
cmake --build build-opt05-results --config Release --target hull_reducer_test --parallel 4
ctest --test-dir build-opt05-results -C Release -R hull_reducer_test --output-on-failure --no-tests=error
python reports/algorithm-results/opt05-hull-20261012-d1c211c2/render_saved.py --records reports/algorithm-results/opt05-hull-20261012-d1c211c2/records.json --out reports/algorithm-results/opt05-hull-20261012-d1c211c2
python reports/algorithm-results/opt05-hull-20261012-d1c211c2/validate_report.py
```

The benchmark collector runs a new measurement; rendering and validation are offline and do not invoke the solver. The CMake test configuration fetches the pinned project dependencies and builds the `hull_reducer_test` target in Release before CTest runs it. The commands above describe reproduction, not a claim that every command ran in this exact order during collection. Recorded execution evidence: Release harness build succeeded; collector accepted 21/21 trials and retained 3 warmups; the recorded `ctest ... -R hull_reducer_test ...` run passed 1/1 (0.02 s); saved-record rendering and consistency validation are run when assembling this report.

The report validator also checks every field in both accepted and root-level trial and summary CSV files against `records.json`. Run its corruption checks with `python -m unittest reports.algorithm-results.opt05-hull-20261012-d1c211c2.test_validate_report`; they mutate a trial or summary value in both CSV copies and require validation to reject it.

`profile/target-process-samples.csv` and `.json` are exported target-process-only summaries from a distinct `/Zi` symbol-enabled run. Raw system-wide ETL and symbolized all-process exports are intentionally excluded. Raw reducer-profile JSONL and exact profiler command/evidence remain in `profile/`.

## Bundle

`bundle.zip` is an offline snapshot of the report and evidence. `manifest.sha256` lists SHA-256 hashes for every packaged file (excluding the manifest itself); `bundle.zip.sha256` records the ZIP hash. Regenerate after all edits using the packaging commands in `validate_report.py`.
