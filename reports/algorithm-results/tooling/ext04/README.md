# EXT-04 observed replay report harness

This private report harness measures the public `CSL::controllers`
`replay_observed_policy` path from frozen source commit
`c23aaf13c1c1e5480cc22dd5bac5cd3e79562609` (draft source PR #342).
It does not modify the replay implementation or add an installed report API.
The harness is reviewed separately before any timed collection. Issue #68
remains open for initial-set synthesis, broader observation variants, and
policy/evidence acceptance.

The three explicitly sampled fixtures have independent binary64 literals:

| Fixture | Physical states | Released observations | Decisions |
|---|---|---|---|
| `partial_noisy_delayed` | `(1,7) -> (2,7) -> (9,7)` | `4` at before(0); `7` measured after(0), released before(1) | `1,7` |
| `post_feedthrough` | `2 -> 3 -> 10` | `7 = x0 + 2u0 + v0` measured/released after(0) | `1,7` |
| `no_channel` | `5 -> 7` | none; no implicit full-state observation | `2` |

Every public call constructs a fresh `LinearSystem`, runs the estimator and
controller through the public replay function, then compares complete state,
observation, release-event, available-history, estimate, action and retained
input records with literals inside the timed batch. The C++ driver and Python
collector each check those values. These are sampled trajectory checks under
exact chosen initial states and measurement errors. They establish no policy
nonanticipativity against arbitrary callback captures, state-estimate accuracy,
all-initial-states feasibility, all-disturbance guarantee, optimality, family
completeness, or validated rounding enclosure.

The measured interval is one batch of fresh public model snapshots and replay
calls, callback execution, full literal comparisons and per-call JSON result
construction and assignment/replacement of the prior result. It excludes
process startup, JSONL serialization, Python
validation, persistence and rendering. One warmup per fixture is excluded;
at least seven measured repetitions alternate fixture order. Successful
batches must have at least 20 ms of measured work. Results are descriptive
single-path batches with no comparator, speedup, attributed limiter, or
application-throughput conclusion. CTest smoke runtime is not a benchmark.

## Bounded functional checks before review

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $cmake -S . -B build/ext04-harness -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_EXT04_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=ON
& $cmake --build build/ext04-harness --config Release `
  --target csl_ext04_observed_replay_report --parallel 4
python scripts/reports/ext04/check_smoke.py `
  build/ext04-harness/Release/csl_ext04_observed_replay_report.exe
python -m unittest discover -s tests/reporting -p 'test_ext04_harness.py'
```

`--smoke` executes each fixture once and checks literal results. Synthetic
collector tests never create a measured run. The source and harness PRs must
receive independent review before the following collection workflow is used.

## Fixed-source collection after harness review

Use a clean checkout of the exact reviewed harness commit. The collector
rejects other source deltas, dirty source, stale paths, non-Release flags,
compiler overrides, a missing concurrent-work note, incomplete/failing JSONL,
or a batch shorter than 20 ms. It performs a fresh Release rebuild before
launching the driver. The exact build graph, compiler ID/version/toolset/path
and binary hash, raw CMake cache and compiler evidence, source/harness commits,
driver and executable hashes, full fixture hashes, raw process bytes,
OS/host note and every attempted row are saved. A rejected attempt preserves
raw stdout/stderr bytes and a nonpublishable status; it cannot be repaired into
an accepted collection by selecting only successful rows.

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
& $cmake -S . -B build/ext04-report -G 'Visual Studio 17 2022' -A x64 `
  -DCSL_BUILD_EXT04_REPORT=ON -DCSL_ENABLE_HIGHS=OFF `
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=OFF
& $cmake --build build/ext04-report --config Release `
  --target csl_ext04_observed_replay_report --parallel 4
python scripts/reports/ext04/check_smoke.py `
  build/ext04-report/Release/csl_ext04_observed_replay_report.exe

# Inspect live CPU/load and competing processes, then write an accurate
# public-safe UTC note to build/ext04-report/concurrent-work.txt.
$reviewedHarness = git rev-parse HEAD
python scripts/reports/ext04/collect.py `
  --exe build/ext04-report/Release/csl_ext04_observed_replay_report.exe `
  --build-dir build/ext04-report `
  --out build/ext04-report/collection-001 `
  --harness-commit $reviewedHarness `
  --concurrent-work build/ext04-report/concurrent-work.txt `
  --repetitions 7 --batch 5000
```

The collector marks a syntactically and scientifically admitted raw bundle
`accepted_for_report_review=true` but `publishable=false`. A separate report PR
must render a versioned standalone English HTML page with a table and figure,
offline ZIP and exact-byte manifest, register the immutable site route, receive
independent saved-record review, and verify the live Pages URL before
publication is claimed. The later artifact commit does not change the frozen
source/harness measurement identity.

## Saved collection and publication candidate

The single accepted clean Release collection is
`ext04-df62c7c6d295e135`, from source `c23aaf13` and reviewed harness
`959755ed`. Its 13 native files are copied byte for byte under
`reports/algorithm-results/ext04-df62c7c6d295e135/`; the native manifest
continues to describe those original bytes. Adjacent `host-pre.json` and
`host-post.json` preserve the separate five-second host observations. The
report manifest binds these observations and all saved-only outputs.

Regenerate or verify the standalone page, figure, CSVs, manifest and source
offline ZIP without invoking the C++ driver:

```powershell
python scripts/reports/ext04/render_saved.py `
  --bundle reports/algorithm-results/ext04-df62c7c6d295e135 --check
python -m unittest discover -s tests/reporting -p 'test_ext04_publication.py'
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json `
  --check --out build/ext04-site
python scripts/reports/stage_ext04.py `
  --catalog reports/algorithm-results/ext04-publications.json `
  --site build/ext04-site
```

`ext04-publications.json` is a content-bound extension catalogue. Its stage
adds one immutable route and download to the existing report index; source
and public ZIPs each have a working root landing page and a nested report.
The report is an exploratory, inconclusive single-path batch observation;
there is no comparator or source-mapped limiter profile. Independent saved
report review, main-only deployment, and live Pages/download verification
are pending. Issue #68 stays open for the remaining algorithm acceptance.
