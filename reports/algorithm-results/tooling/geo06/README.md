# GEO-06 QuickHull report harness

This report measures the public `quickhull_2d` adapter from fixed source
commit `ce63bff5a0face88c3c5e977f7d96337e8cbe948`. It is descriptive
single-adapter evidence for three tiny analytic clouds. No speedup,
application throughput, or scaling conclusion follows from it.

The fixtures are a square with duplicate and interior points, a collinear
cloud, and a triangle whose top edge differs by `2^-50`. The expected original
input indices are respectively `0:1:2:3`, `1:3`, and `0:1:2` in counterclockwise
order. The driver checks every call against these literals; the Python
collector separately checks every saved row. These checks establish the named
examples only. Exact orientation refers to represented binary64 coordinates.

The measured interval surrounds a batch of fresh `quickhull_2d` calls and
immediate observation of each returned result. It excludes process startup,
CSV serialization, and independent saved-row verification. The driver uses
the C++ steady clock. One warmup per fixture is excluded, followed by seven
repetitions in alternating fixture order. Every row retains the requested
call count, observed vertex count, output indices, status, and nanoseconds.
The report has no competitor and no measured limiter profile; its timings
must not be turned into a performance ranking. OS thread count and internal
phase timing are unavailable.

After independent review of this fixed harness commit, configure a clean
Release build with `CSL_BUILD_GEO06_REPORT=ON`, `CSL_ENABLE_HIGHS=OFF`,
`CSL_ENABLE_QHULL=OFF`, and `BUILD_TESTING=OFF`, then run the smoke. Build and
record the exact harness commit before accepted collection:

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $cmake -S . -B build/geo06-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_GEO06_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=OFF
& $cmake --build build/geo06-report --config Release `
  --target csl_geo06_quickhull_report --parallel 4
build/geo06-report/Release/csl_geo06_quickhull_report.exe --smoke
$harnessCommit = git rev-parse HEAD
python scripts/reports/geo06_report.py collect `
  --exe build/geo06-report/Release/csl_geo06_quickhull_report.exe `
  --build-dir build/geo06-report `
  --source-commit ce63bff5a0face88c3c5e977f7d96337e8cbe948 `
  --harness-commit $harnessCommit `
  --concurrent-work build/geo06-report/concurrent-work.txt `
  --repetitions 7 --calls 1000 --out build/geo06-report/collection-001
python scripts/reports/geo06_report.py check `
  --bundle build/geo06-report/collection-001
```

The final report directory under `reports/algorithm-results/<report-id>/`
contains `records.json`, `trials.csv`, `index.html`, and `manifest.json`.
The output is regenerated and validated solely from saved records. A later
artifact commit differs from the source and harness identities. Publication
requires registration with the Pages catalogue and a live URL check; a local
HTML file or functional smoke is not a deployed report.
