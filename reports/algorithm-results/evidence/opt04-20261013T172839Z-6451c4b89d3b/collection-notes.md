# OPT-04 measurement collection notes

## Status and identity

This is a genuine local collection from the current-main fixed checkout. It is retained as private source evidence. The native report bundle is `opt04-20261013T172839Z-6451c4b89d3b` at `reports/algorithm-results/opt04-20261013T172839Z-6451c4b89d3b/`; its schema is `csl.opt04-phase-one-report/2`. The native bundle contains the exact ten-file inventory required by the schema-3 adapter. These notes and profile-attribution status are outside that immutable native inventory.

- Measurement checkout and reviewed harness commit: `d68f57f1530f69039a7881f950566167683eb222` (`origin/main` at collection time).
- Reviewed algorithm source commit: `03ba157eb50eac7d61d39e37af015729ea04f922`. The algorithm source directory and public header are byte-identical between that commit and the measurement checkout.
- Executable SHA-256, CMake cache SHA-256 and clean Release build-log SHA-256 are in `records.json`; compiler, flags, host, Python version and requested resource policy are also recorded there.
- Native inventory SHA-256 mapping is in `manifest.sha256`; deterministic native ZIP SHA-256 is in `bundle.zip.sha256`.
- Adapter inventory digest, for bundle-review reference only: `238ff015f68d98e385593d844436a562317e12bb0f7cdedbe07e96af7f32bda7`. It is not allowlisted. No production digest pin, catalogue row or public URL is added.

## Collection and result

The harness ran one excluded warmup for each of five fixtures and each of two sides, followed by seven measured repetitions per fixture and side: 70 measured attempts and 10 warmups total. Side order alternates by fixture/repetition; fixture order alternates forward/reverse. Timed phases are setup, `BoundWorkspace.run`, independent verification, and fixture-to-verified-result end-to-end. Process startup and serialization are excluded. The collector returned exit 0; every attempt passed its literal/status and applicable numerical checks; no attempts were missing or aborted. The native saved-data validator passed after the focused correction described in this PR. See `index.html`, `performance.svg`, `records.json`, `stdout.jsonl`, `driver-stdout.txt`, `stderr.txt`, and `release-build.txt` for the complete output and per-fixture medians/ranges.

These are descriptive measurements on five small analytic equality/nonnegative fixtures only. They do not establish a speedup, a winner, application throughput, scalability, exact/validated feasibility, a complete feasible solution family, or the archived author's verified original release. The fixture set excludes collinear inputs; issue #29 remains open. Numerical evidence support remains **Unestablished**.

The claim supported here is limited to: the saved harness completed seven valid measured repetitions for each fixture/side pair on this host. This is a descriptive collection, not a comparative performance conclusion. For example, on `triangle`, `public_run` for `phase-one-bland` had median 25,300 ns (range 18,300–50,500; n=7), and `highs-reference` had median 202,700 ns (range 182,600–283,500; n=7). These values are reported to make the raw collection inspectable; they do not establish a speedup or identify a generally faster approach.

The timed script was `collect.py --measure`; it timed only the four regions defined below. Input sizes and expected outcomes are the five named analytic fixtures saved in `records.json`. The collection used a single process and requested one total thread, one outer worker, and one native thread where applicable; actual worker/thread counts were not observed. The Highs profile requested simplex, presolve off, parallel off, and one native thread. The phase-one implementation is single-threaded in-process. The build used the CMake `Release` configuration with `NDEBUG`; no extra compiler-specific optimization or CPU tuning was applied beyond that configuration. The collector's clean-first Release rebuild occurred before timed trials. Functional CTest durations are not part of this benchmark and are not used in the displayed timings.

## Environment and load

- Windows 11 Home, version 10.0.22631, x64; Intel Core i5-12400F, 6 cores / 12 logical processors; 33,387,800 KiB visible physical memory (13,677,820 KiB free at the pre-run snapshot).
- Visual Studio 17 2022 generator, MSVC 19.44.35215, Release, C++20, `NDEBUG`; CMake 3.31.6; Python 3.13.5. Exact flags and binary identity are retained in `records.json` and `release-build.txt`.
- A single WMI snapshot immediately before the harness rebuild measured 6% total CPU. Three MSBuild processes were active at that snapshot, in addition to browsers, editor/agent services and other background processes. These were not isolated or controlled. The matched order interleaves the two solver sides, but this host condition limits timing interpretation. A later snapshot read 5% after collection; this is not a measurement of the timed interval.
- Runtime worker/native thread counts are unobserved by the harness; the one-thread values are requests/configuration only, as stated in `records.json`.

## Reproduction commands

From the checkout root in PowerShell with Visual Studio 2022 installed:

```powershell
$api = 'build/opt04-report/.cmake/api/v1/query'
New-Item -ItemType Directory -Force $api | Out-Null
New-Item -ItemType File -Force "$api/codemodel-v2" | Out-Null
New-Item -ItemType File -Force "$api/toolchains-v1" | Out-Null
cmake -S . -B build/opt04-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_OPT04_REPORT=ON -DBUILD_TESTING=OFF
cmake --build build/opt04-report --config Release `
  --target csl_opt04_phase_one_report --parallel 4
python reports/algorithm-results/tooling/opt04/collect.py --smoke `
  --exe build/opt04-report/Release/csl_opt04_phase_one_report.exe
python -m unittest discover -s reports/algorithm-results/tooling/opt04 -p 'test_*.py'
python reports/algorithm-results/tooling/opt04/collect.py --measure `
  --exe build/opt04-report/Release/csl_opt04_phase_one_report.exe `
  --build-dir build/opt04-report `
  --source-commit 03ba157eb50eac7d61d39e37af015729ea04f922 `
  --harness-commit d68f57f1530f69039a7881f950566167683eb222 `
  --concurrent-work-file build/opt04-report/concurrent-work.txt `
  --out build/opt04-report/collection-001
python reports/algorithm-results/tooling/opt04/render.py `
  --records build/opt04-report/collection-001/records.json `
  --out build/opt04-report/collection-001
python reports/algorithm-results/tooling/opt04/validate_report.py `
  --report build/opt04-report/collection-001
```

The collector itself performs a clean-first Release rebuild immediately before timing. Rendering consumes only saved records and reruns no solver. The three final verification commands all passed: the native report validator confirmed the 70 trials, warmup schedule, residuals/oracles, summary, generated HTML/SVG, inventory manifest and deterministic ZIP; the report-tool suite passed 16 tests; `git diff --check` passed.

## Limiter and publication gates

No profiler data are mixed into the trials. A separate Windows Performance Recorder CPU sample was attempted after collection with `wpr.exe -start CPU -filemode`; WPR returned error `0xc5585011` while enabling the system-performance profiling policy. WPR status after that attempt confirmed no recording was active. No CPU profile or interval-level system-counter evidence was produced, so the hot path and limiting resource remain unattributed. The performance verdict is **INCONCLUSIVE**; no speedup or performance winner is asserted.

The reviewed OPT-04 publisher registry currently has no reviewed native bundle digest. Consequently this PR does not add a catalogue row, alter the publication allowlist, run the main-only Pages deployment, or claim a public page/URL. Issue #185 remains open for independent bundle/adapter review, reviewed digest admission and the exact publication/live-download gates. Issue #29 remains open for its algorithm acceptance requirements and scientific review.

