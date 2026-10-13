# SYN-02 terminal relation report

This versioned harness measures the public `TerminalOptimizer` on five analytic
H-polyhedral terminal-slice fixtures. It uses the registered HiGHS LP and
convex adapters and makes no competitor, speedup, application-throughput, or
scaling claim. The report is descriptive and binary64-only.

## Fixed source and harness

The measured algorithm source identity is pinned to
`c234a1a04b2f90e34776a2bfa349a91a1d30257d`. A later harness/artifact commit
adds only the reporting option/target and these tooling files. Collection
rejects source changes outside that allowlist, dirty tracked files, or an
executable whose embedded source/harness identities do not match the selected
commits. The report option is private and off by default; the target is not
installed and does not change the library API.

## Saved records and publication contract

`records.json` retains the private native payload schema
`csl.syn02-terminal-report/1`. Each bundle also contains `publication-map.json`,
which gives the exact projection to `csl.algorithm-report-envelope/1` and
`csl.algorithm-report-catalog/3`: the native report ID becomes
`source_report_id`; the publisher supplies the immutable public `report_id`;
the payload schema/digest, `native_payload_sha256` (the canonical digest of the
complete native `records.json` payload), source commit, measured scope, evidence
limits and complete native payload populate the shared envelope. The map enumerates the
exact staged file inventory hashed by `publication-manifest.json`: the
validated bundle artifacts plus generated `index.html` and `report-envelope.json`;
the publication manifest excludes itself. The generated offline ZIP contains
that staged inventory and its digest is recorded in the catalogue.

The immutable public ID is `syn02-` plus the full SHA-256 of canonical UTF-8
JSON (`ensure_ascii=false`, sorted keys, compact separators) for
`{schema: csl.registered-publication-identity/1, source_report_id, source_files,
publisher_sha256}`. `source_files` maps sorted relative paths to SHA-256 for
every validated native source file (the native manifest inventory plus the
manifest itself; any separately validated source ZIP is included). The adapter
module hash is SHA-256 of its UTF-8 source after CRLF-to-LF normalization. This
matches the repository's registered-publication identity rule and binds both
the saved measurement and its renderer/publisher implementation.

This is a mapping specification, not a registered adapter. SYN-02 is not
publishable until `scripts/reports/syn02_registered_reports.py` implements
`adapt`, `render_page`, `publication_artifacts` and `offline_zip`, and
`scripts/reports/site.py` imports it, admits the schema-3 kind, and dispatches
to it from `site.stage`. The adapter must validate safe identity/paths, native
record and source identity, complete trial/summary consistency including
failures, inventory/hash manifest, SVG, common envelope projection and
deterministic ZIP. Then the schema-3 catalogue and main-only Pages workflow
must stage the report and verify the live page and ZIP URLs. Until those steps
land, neither this mapping nor its producer HTML makes the bundle publishable.

On any collector exception, `collection-failures/<attempt-id>/failure.json`
preserves the stage, error, source/harness identities, attempted command and
hashes of available configure/build/driver/profile streams. Partial timeout
stdout/stderr and incomplete trial streams are saved alongside it. These use
the distinct `csl.syn02-collection-failure/1` schema under
`collection-failures/`, carry `accepted_measurement: false`, and are not valid
report bundles, catalogue entries, or accepted measurements.

## Fixtures and limits

* `linear-face`: minimize `x + 7` on `[0,1]^2`; expected value 7 and sampled
  minimizer face `x=0`.
* `constant-linear`: minimize `3` on `[0,1]^2`; expected relation is the whole
  box.
* `psd-null-direction`: minimize `x²` on `[0,1]^2`; expected sampled face is
  `x=0`.
* `rectangular-residual`: minimize `||x-0||²` for residual map `[x,y] -> x`;
  expected sampled face is `x=0`.
* `shifted-residual-degenerate`: minimize `||x-0.5||²` for the same
  rectangular map; the selected HiGHS backend returns `undetermined` with
  `numerical_failure` termination, a retained primal value of 0.5, and no
  minimizer relation. This is counted as a non-success even when the expected
  backend behavior matches.

The independent literal checks verify outcome/status, objective values, H-row
shape, and included/excluded sample points. They are not a proof of exact set
equality, global optimum, or complete optimizer-family coverage. Relation and
optimum support remain `Unestablished`; the shift-degenerate result is retained
as data rather than converted into a successful optimizer witness.

## Timing

Every trial builds a fresh resolved problem, set, provider registrations and
prepared providers. `prepare_ns` records that setup. `solve_ns` covers the
`TerminalOptimizer::solve` call, including internal program construction,
workspace execution, anchor handling, and relation construction. `oracle_ns`
records immediate C++ result consumption; saved-data literal checks are rerun in
Python after the executable exits, outside every reported algorithm interval.
`execute_ns` spans fixture resolution through immediate C++ result
consumption. Process startup, compilation, destruction, JSON writing, collector validation, and
rendering are excluded. One process is used, with one excluded warmup per
fixture and seven alternating forward/reverse measured rounds. The output
retains every event and failure; a failed oracle invalidates its fixture
summary instead of filtering failures from timing statistics.

The separate 1,000-round process-counter run samples CPU time and resident
memory, and retains its complete raw event stream. A Windows Performance
Recorder CPU stack-profile attempt failed with `0xc5585011` while enabling the
system performance profiling policy. The separate counters cannot attribute
call stacks, so the limiting function/path remains unknown. These measurements
are not a speed comparison or a scale claim.

## Build and collection

Use a clean checkout of the harness commit, the fixed source commit above, and
fresh build/output directories. Python requires `psutil`; there are no package
install steps in CMake.

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$build = 'build\syn02-report-release'
$outRoot = 'reports\algorithm-results'
python reports/algorithm-results/tooling/syn02/collect.py `
  --cmake $cmake --build-dir $build --out-root $outRoot `
  --harness-commit (git rev-parse HEAD) `
  --generator 'Visual Studio 17 2022' --architecture x64 `
  --repetitions 7 --warmups 1
```

The collector configures/builds the private driver in Release, verifies the
CMake File API target and C++20/NDEBUG/optimization flags, records full commit
identities and machine/compiler/build details, then measures and checks all
trials. It writes `index.html`, raw JSONL, CSV, records, SVG, build/profile
evidence, a hash manifest and an adjacent offline ZIP. Rendering uses only
saved data. The standalone `render_saved.py` command regenerates HTML and SVG
from `records.json` without invoking the executable. It does not change the
main catalogue, report index, or Pages site;
publication remains a separate review/deployment step.

Run harness tests before collection:

```powershell
python reports/algorithm-results/tooling/syn02/test_report.py
python -m py_compile reports/algorithm-results/tooling/syn02/collect.py
python -m py_compile reports/algorithm-results/tooling/syn02/render_saved.py
python -m py_compile reports/algorithm-results/tooling/syn02/publication_map.py
```

Regenerate the page and figure from an existing bundle:

```powershell
python reports/algorithm-results/tooling/syn02/render_saved.py `
  --records reports/algorithm-results/<report-id>/records.json `
  --out-dir reports/algorithm-results/<report-id>
```
