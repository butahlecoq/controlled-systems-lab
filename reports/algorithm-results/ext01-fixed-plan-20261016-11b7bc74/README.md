# EXT-01 fixed-source collection record

This is the saved raw acquisition for EXT-01 issue #62. The algorithm source
commit is `fd75a63657bc6b1d8cbd26c644bd8fb39cc1a3ec`; the independently
reviewed harness commit is `11b7bc74e4756bafc2c6c450628d10c6a62f8f39`.
The checkout was clean at that harness commit before and after the fresh MSVC
Release rebuild and trials. `records.json` binds the source tree, fixture and
B08 reference hashes, executable hash, compiler graph, environment, timing
scope, 32 raw attempt rows, and seven measured observations per fixture.

`accepted.stdout.jsonl` and `accepted.stderr.txt` are exact process bytes.
`accepted.process.json` retains process status and sampled CPU/RSS. The
nonreported profile run has separate `profile.*` files and is excluded from
the timing summary. `fresh-build.json`, `build-graph.json`, and
`smoke-ctest.txt` retain build and functional-check evidence. The collection
code and large-output regression are in `scripts/reports/ext01`.

Two attempts were excluded. `excluded-profile-001.json` records a capture
deadlock in the first profile collector: the child filled unread Windows
anonymous pipes and both owned processes were stopped before measured trials
began. Its stdout and stderr bytes were unavailable because they had never
been durably captured; the empty sidecars mark that absence explicitly. The
collector was changed to stream directly into files, with a regression that
captures more than one MiB and retains a failed child's output/status.
`excluded-002.*` preserves all 32 raw rows, stderr, process status and the
validation error from a completed run rejected by a provisional 50 ms batch
floor. The L19 10,000-call batch took roughly 44–46 ms. The final collection
used an explicit 20 ms admission floor and reran after another fresh Release
rebuild. No timings from either excluded attempt enter `records.json`.

All reported durations are **batch** intervals, including fixture creation,
public API calls, literal result checks and construction of the JSON result
object. The driver excludes process startup, JSONL serialization, persistence
and rendering. L19's short batch interval warrants particular caution; no
per-call latency or speedup is inferred. This is a single-adapter observation
without a comparator. Source-bound numerical results are for authored native V
data and the displayed rounded B08 model. They do not reproduce unrounded
historical MATLAB data, the published 67.12, nonlinear trajectories, validated
rounding, feedback optimality or an optimal family.

This acquisition is awaiting saved-data HTML/CSV/ZIP rendering, independent
report review, main-only Pages publication and live URL verification. Issue
#62 remains open.
