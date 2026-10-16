# GEO-07 registered dependent-sum report harness

This optional driver is stacked on frozen algorithm source
`5411e37ad456f0d5b3bf775130f149622ef5ebfa` (draft PR #356). It prepares
the public `GeometryPort` registration at version `1.1.0`, sends a typed
`DependentSum`, executes its workspace, and checks the returned evidence and
literal factor and physical H references. The existing independent
`MinkowskiSum` request is tested as a scoped rejection for the same shared-ID
operands. Its measured result is a separate saved report awaiting independent
scientific review and publication.

| Fixture | Shared factor relation | Literal physical reference |
| --- | --- | --- |
| `shared_cancellation` | `u + (-u)`, one `history.0` axis retained with zero coefficient | `x=0`; `x=-1,1` outside |
| `constrained_shared` | left `u=v`, right `u=-w`, with both equality rows on joined `[u,v,w]` | `(x,y)=(0,0)`; `(0,1),(1,0)` outside |

The driver creates fresh generator handles, a registry and workspace per
checked call. Its timed `steady_clock` interval includes admission, execution,
literal checks, independent-sum rejection and construction of one result JSON
object. It excludes process startup, JSONL serialization, Python row
validation, persistence and rendering. The timing is a whole checked public
path, not isolated native sum latency. The fixtures have exact small integer
binary64 inputs; this does not establish a general rounding enclosure. The
adapter's `equivalent` claim describes real-set generator algebra at numerical
assurance. No validated equality, global error bound, comparator or speedup is
claimed. Internal phase counters and native thread count are unavailable.

## Pre-review verification

From a clean checkout of this harness branch on Windows with MSVC 2022:

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$ctest = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe'
& $cmake -S . -B build/geo07-dependent-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_GEO07_DEPENDENT_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=ON
& $cmake --build build/geo07-dependent-report --config Release `
  --target csl_geo07_dependent_report --parallel 4
& $ctest --test-dir build/geo07-dependent-report -C Release `
  -R '^geo07_dependent_report_smoke$' --output-on-failure
python -B -m unittest tests.reporting.test_geo07_dependent_harness
$harnessCommit = git rev-parse HEAD
python -B scripts/reports/geo07_dependent/collect.py `
  --exe build/geo07-dependent-report/Release/csl_geo07_dependent_report.exe `
  --build-dir build/geo07-dependent-report `
  --out build/geo07-dependent-report/preflight-001 `
  --harness-commit $harnessCommit --preflight-only
```

`--preflight-only` checks the clean exact harness HEAD, frozen source ancestry,
an allowlisted report-only source delta, MSVC x64 Release flags and actual
driver/adapter/native generator project graph. It does a fresh `--clean-first`
build, then saves and validates `--describe` and `--smoke` bytes. The output
retains build/driver stdout and stderr, process captures, input hashes,
compiler and executable provenance, a manifest and a nonpublishable status.
Every timeout or process failure retains available raw stdout/stderr and a
nonpublishable manifest. It never invokes `--measure`.

## Reviewed collection protocol

Independent source and harness reviews, exact-head CI and an idle host window
are prerequisites for collection. After the harness code is reviewed, add
`scripts/reports/geo07_dependent/review-seal.json` in a metadata-only final
commit with the reviewed code commit/tree and frozen source. The full collector
requires that exact HEAD, its seal parent and an otherwise clean checkout. It
also requires `BUILD_TESTING=OFF`, captures a fresh Release rebuild and public
smoke, then observes host CPU/load and build processes. Only a fresh idle host
observation may admit `--measure` with one excluded warmup and at least seven
alternating measured batches per fixture. Each row must contain all checked
calls, literal results, a valid status and at least 20 ms of measured batch
work. Raw failures remain rejected and reviewable. Accepted rows become saved
records for independent scientific review, HTML/ZIP rendering, main-only Pages
deployment and live hash verification under the
[published-results contract](../../../../docs/architecture/published-algorithm-results.md).

## Saved collection and regeneration

Independent harness reviews cover code commit
`eaa32fdfdcf42b3f3f3221dd3031d654fe05e576`. Its metadata-only seal child
`eef1eda3d326418a392b3cc1e8f8f4b204ca7a73` produced the accepted raw
collection `accepted-003`. The immutable source bundle is
[`geo07-dependent-4dcc5a8fe36f17ed`](../../geo07-dependent-4dcc5a8fe36f17ed/).
It contains the complete Release build, description, smoke and trial captures,
the host observation, all process status/byte hashes, and the two rejected
attempts under `evidence/`. The first attempt observed three idle MSBuild
nodes and stopped before measured trials. The second passed its checks but
1,000-call batches were below the 20 ms admission floor. Their raw output and
nonpublishable manifests remain available for audit.

The accepted run made one excluded warmup and seven alternating 2,000-call
measured batches per fixture, with zero observed failures. Its raw trial SHA-256
is `3cc538611451add4eaef7adcbb5f225bbe668eadb8c32bd9e98de298f85fbc0c`;
records SHA-256 is `fb4a0bab5953e679ece8e814aeb2a0fcbe68c4816fad3cc097c9e1b48774399c`.
The saved batches are exploratory observations of this whole checked public
path. Performance interpretation is inconclusive without a comparator,
application workload or source-mapped limiter profile.

From this publication branch, regeneration reads saved bytes only:

```powershell
python -B scripts/reports/geo07_dependent/render_saved.py `
  --bundle reports/algorithm-results/geo07-dependent-4dcc5a8fe36f17ed --check
python -B -m unittest tests.reporting.test_geo07_dependent_publication
python -B scripts/reports/site.py --catalog reports/algorithm-results/catalog.json `
  --check --out build/geo07-dependent-site
python -B scripts/reports/stage_geo07_dependent.py `
  --catalog reports/algorithm-results/geo07-dependent-publications.json `
  --site build/geo07-dependent-site
```

The Pages workflow stages the content-bound route only from main. Merge,
deployment and live URL/hash verification remain pending.
