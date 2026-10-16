# GEO-07 registered-port fixed-source report harness

This harness is stacked on exact reviewed adapter source commit
`41b4b58f2ef982e75554519862afdd803e30f717` (draft PR #344). It calls
registered `CSL::generator_adapter` through freshly prepared public
`GeometryPort` and `ConversionPort` providers, executes workspaces, then
checks returned evidence and literal independent geometry oracles. It does not
replace the separate native generator report.
PR #344 and issue #32 remain open while this adapter-specific evidence is
reviewed and published.

The three authored fixtures are:

| Fixture | Public operation | Literal physical or V oracle |
| --- | --- | --- |
| `affine_box` | Affine image of `c=(1,2)`, `G=diag(2,3)` by `[1,1]` plus `4` | `2 ≤ x ≤ 12`; factors and coefficients retained |
| `constrained_disjoint_sum` | Minkowski sum of `x=1+u, u=v` and `x=3+2q, p=-q`, with disjoint IDs | `1 ≤ x ≤ 7`; both equality rows and IDs retained |
| `finite_v` | Unconstrained two-factor segment `7+2a+3b`, explicit cap `4` | Enumerated corner images / V-representation rows `2,6,8,12`, zero rays and label `x` |

Each fresh call verifies feasible factor witnesses and physical H in/out
answers or exact V-representation row bytes. Only 2 and 12 are extreme
endpoints of this segment; 6 and 8 are redundant interior corner images.
The call also verifies scoped rejection of
validated assurance, shared-ID independent sum, intersection, a too-small
enumeration cap, constrained conversion and H conversion. The exact authored
inputs, public request identity, H/V references, witnesses, control requests
and output identity appear in `--describe`. The Python collector compares
that catalogue with independent literal values, writes canonical
`fixture-inputs.json`, and records each fixture payload SHA-256. Driver source,
raw description bytes and the full reviewed source commit are also bound.

The timed `steady_clock` interval includes fresh generator construction,
provider registration and preparation, workspace execution, literal H/V and
factor checks, rejection controls, and per-call nlohmann JSON result
construction and assignment. It excludes process startup, JSONL
serialization, Python saved-row verification, persistence, rendering and
deployment. Every call must pass; elapsed batch time includes verification
and allocation and is not isolated operation latency. Each fixture has one
excluded warmup and at least seven measured batches in alternating fixture
order. The collector admits only batches of at least 20 ms and retains all
raw rows, including failed or partial rows. A process failure leaves a
nonpublishable status with exact raw stdout/stderr and hashes.

The representation claims are equivalent in real-set algebra. All values are
evaluated in binary64; no validated rounding enclosure or global numerical
error bound is supplied. This is one adapter and three small examples, with
no comparator, speedup, application throughput, scaling or source-mapped
limiter claim. Internal phase counters and observed native thread count are
unavailable. Any eventual timing is exploratory and performance conclusions
remain inconclusive.

## Bounded pre-review verification

These commands build and smoke-check the harness without running measured
collection. They are not performance evidence:

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$ctest = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe'
& $cmake -S . -B build/geo07-port -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_GEO07_PORT_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=ON
& $cmake --build build/geo07-port --config Release `
  --target csl_geo07_port_report --parallel 4
& $ctest --test-dir build/geo07-port -C Release `
  -R '^geo07_port_report_smoke$' --output-on-failure
python -B -m unittest discover -s tests/reporting -p test_geo07_port_harness.py
```

## Later reviewed collection procedure

Collection requires independent review and exact-head CI for this harness,
a clean checkout at that reviewed commit, and an observed idle host window.
The final commit changes only `scripts/reports/geo07_port/review-seal.json`.
That seal pins its reviewed code parent and tree; the collector checks the
actual HEAD, its parent and the final commit's exact changed-path set before
building or invoking the driver. `--harness-commit` cross-checks the checked
out HEAD and cannot authorize a newer code commit.
The collector rebuilds the exact configured Release target with
`--clean-first --verbose`, checks MSVC x64 `/O2 /Ob2 /DNDEBUG` and the driver,
adapter and native generator library project/link graph, rejects `CL`, `_CL_`
and `LINK` overrides, and retains build stdout/stderr, project hashes,
compiler evidence and exact executable hash. After the final rebuild and
driver description, the collector captures its own structured Windows CPU
load, logical processor count and `cmake`/`MSBuild`/`cl` process counts. The
UTC observation must be after the rebuild, at most 30 seconds before the
measurement start, have CPU load at most 25%, and have zero build processes.
If the host is busy, it saves the exact observation bytes and a nonpublishable
status without invoking `--measure`. An admitted attempt retains those raw
bytes, their SHA-256 in the record and manifest, and UTC collection start/end.
The record separates the frozen source tree from the reviewed harness tree.

The following commands are a plan only. **They have not been run for this PR.**

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $cmake -S . -B build/geo07-port -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_GEO07_PORT_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=OFF
& $cmake --build build/geo07-port --config Release `
  --target csl_geo07_port_report --parallel 4
$harnessCommit = git rev-parse HEAD
python -B scripts/reports/geo07_port/collect.py `
  --exe build/geo07-port/Release/csl_geo07_port_report.exe `
  --build-dir build/geo07-port `
  --out build/geo07-port/collection-001 `
  --harness-commit $harnessCommit `
  --repetitions 7 --batch 1000
```

The collector saves native stdout as exact `trials.jsonl` bytes and stderr as
`driver.stderr` before parsing. It admits only complete ordered rows with
checked call counts, literal result payloads, valid statuses and batch
duration. Accepted records, fixture inputs, driver description, build
provenance and a SHA-256 manifest are saved under the new collection path.
Scientific review, deterministic rendering and ZIP, catalogue registration,
main-only deployment and live Pages verification are later gates under
[`published-algorithm-results.md`](../../../../docs/architecture/published-algorithm-results.md).

## Accepted saved collection and publication source

Independent saved-record audits accepted `collection-002`, report ID
`geo07-port-4dee19cde3d50259`, from frozen source
`41b4b58f2ef982e75554519862afdd803e30f717` and sealed harness
`95ba77d3fb2077ec3f56c8fe68903eb18f26488a`. The committed report
directory carries every native collector file byte-for-byte, including its
native manifest, plus a separate immediately-after-run host observation.
The raw JSONL SHA-256 is
`41649b7f4acde2c0e980b7c648358d9d217f68e3e5ec9c103f25173e7ab0d39e`;
the records SHA-256 is
`e197ee1852fdb49b3b9180e0a7bfee3004cbb5bb000cf3f175f5ba22b61a5cb1`;
the post-run host note SHA-256 is
`dff519dc043fe14cd451f919315a9eee34f00a919e979fba46be809a71548c8a`.

All 24 saved batches passed literal checks: one excluded warmup and seven
measured batches per fixture, 5,000 checked fresh calls per batch, 120,000
checked calls overall and zero failures. The verified-batch medians/ranges in
milliseconds are affine image `57.405 [56.795, 58.241]`, constrained sum
`69.538 [68.830, 74.891]`, and V conversion `83.050 [82.442, 84.471]`.
These are descriptive single-adapter observations, including verification
cost, with no comparator or attributed limiter. Performance interpretation is
exploratory and inconclusive. The representation algebra is equivalent for
the authored real-set fixtures; binary64 evaluation has no validated rounding
enclosure.

The earlier `collection-001` is excluded: its 1,000-call batches passed
literal checks but fell below the 20 ms admission floor. Its raw SHA-256 is
`7f31a8988d36fde6846b4fbb463b797ced9f4b93796bf06e3e9db5843a7d433e`.
Those rejected raw bytes and their pre-rebuild build evidence remain outside
the published bundle. The renderer never invokes the native driver:

```powershell
python -B scripts/reports/geo07_port/render_saved.py `
  --bundle reports/algorithm-results/geo07-port-4dee19cde3d50259 --check
python -B -m unittest tests.reporting.test_geo07_port_publication
python -B scripts/reports/site.py --catalog reports/algorithm-results/catalog.json `
  --check --out build/geo07-port-report-site
python -B scripts/reports/stage_geo07_port.py `
  --catalog reports/algorithm-results/geo07-port-publications.json `
  --site build/geo07-port-report-site
```

The source page, table CSVs, SVG, report manifest and source ZIP are
deterministically regenerated from the saved files. The typed extension
catalogue binds all staged bytes and LF-normalized publisher source to an
immutable public route; its ZIP has a root landing page and a complete nested
report. Main-only Pages deployment and opening its live links remain pending.
The separate adapter source/harness PRs and GEO-07 issue #32 remain open.
