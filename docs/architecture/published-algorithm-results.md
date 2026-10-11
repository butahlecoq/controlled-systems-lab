# Published algorithm results

The owner requires an English HTML report whenever an implemented algorithm can produce numerical results. Reports are deliverables of the algorithm work, not a feature deferred until the complete optimal-control application exists. [HTML-01 #123](../superpowers/plans/tickets/HTML-01.md) provides the initial report pipeline and first reference-LP report. Existing scientific and implementation acceptance criteria remain binding.

## Artifact and publication

Use saved, versioned records to render a standalone HTML page with numerical tables, suitable figures and measured performance. Publish an index and immutable report URLs through this repository's GitHub Pages site. Keep the report, raw JSON/CSV and assets in version control, with a download path that remains useful offline. Link the actual published URL and source commit in each relevant PR and issue. Until a report is measured, reviewed and deployed, its URL and performance are pending rather than implied by passing tests.

Each report identifies algorithm/module/backend versions, code commit, scenario and input hashes, supported assumptions, expected analytic or sourced values, actual objectives/residuals/status and evidence scope. Distinguish historical published figures from new measurements. A solver witness is not a complete optimal relation. Failed, unsupported and cancelled runs retain their status and any available evidence.

## Measurements

Record hardware, OS, compiler and release settings; arithmetic/tolerances/seeds; requested and actual worker/native thread counts; cold/warm and workspace reuse policy. Specify precisely what each interval includes, with units and raw per-repetition data. Separate setup, solve, verification, end-to-end and rendering where measured. Name unavailable internal counters instead of guessing them. Nested or parallel durations cannot be summed as end-to-end latency. CTest runtime is test-harness time, not an algorithm benchmark.

Comparative performance claims require at least five alternating tuned repetitions per side, median/range, failures and a separate limiter profile, following [skill routing](../agents/skill-routing.md). Report inconclusive comparisons when the measurement does not support a winner. A first single-adapter report can report reproducible timings without an invented competitor or speedup. Check expected numerical outputs and that the work actually ran before accepting a timing record.

## Module boundaries and review

Keep execution, measurement collection, scientific saved records, HTML rendering and publication independently replaceable, outside solver logic. Future [OBS-04](../superpowers/plans/tickets/OBS-04.md), [OBS-05](../superpowers/plans/tickets/OBS-05.md) and [VIZ-03](../superpowers/plans/tickets/VIZ-03.md) extend the records/figures; they are not blockers for the first analytic LP report. The first small record must have an explicit migration path into those authoritative artifacts rather than a competing result schema.

Independent review checks mathematical/evidence labels, measurement validity and module boundaries. Verify raw-record/HTML consistency and regeneration, visually inspect the page, and open the deployed URL before claiming publication. The orchestrator publishes the reviewed artifact. Private historical source code and raw archives remain unchanged and are not copied into the report site.

## Reference-LP pipeline

The [report-record contract](../contracts/algorithm-report-records.md) specifies the executable, saved schemas, exact timing scopes, independent literals, build/environment provenance, commands and OBS migration. `csl_lp_report --smoke` is a bounded functional test. Accepted seven-trial measurements and the separate counter profile follow review of a fixed clean Release code commit; their source identity is distinct from the later artifact commit.

Collection, plotting, rendering and static staging are separate commands under `scripts/reports`. Regenerate a reviewed bundle from saved `records.json` without rerunning the solver. Keep all failures and unavailable fields, inspect actual figures/pages, and retain raw JSONL, JSON/CSV, profile/build evidence and exact-byte manifests. Bundles live under `reports/algorithm-results/<report-id>/`, with a catalogue/index and adjacent offline ZIP. Destinations are immutable, and only allowlisted reviewed files enter the main-only Pages deployment workflow. The actual deployed versioned URL and downloads must be verified before algorithm-report completion is claimed.
