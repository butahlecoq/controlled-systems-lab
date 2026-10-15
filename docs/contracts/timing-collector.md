# Nested and parallel timing

OBS-02 supplies `csl/execution/timing_collector.hpp` in `CSL::artifacts`.
`ExecutionContext::timing` is an optional, default-empty collector handle. Existing
callers remain source compatible; the compatible-toolchain contract is not a
stable binary ABI. No executor scheduling or mutable solver workspace changes.
OBS-03 owns automatic instrumentation of mathematical ports.

## Strategy A phase slots

The public `csl/synthesis/strategy_a/strategy.hpp` header reserves these planned
IDs for the first Strategy A timing slice. The caller must put all five IDs in
the resolved `CollectionPlan`; ID 0 is the run root and IDs 1–4 are nested below
it. The operation labels are `strategy-a/run`, `strategy-a/forward`,
`strategy-a/feasible-preimage`, `strategy-a/terminal-optimization`, and
`strategy-a/terminal-preimage`. The `SpanDescriptor` remains authoritative for
module/backend provenance and all other observations. Phase spans measure the
named Strategy A logical phase; backend-specific LP, convex, geometry,
conversion, and provider identities still require instrumentation at those
ports. Strategy A does not translate collector ticks into the legacy
`SynthesisResult::spans` seconds field.

An enabled plan that omits a reserved ID causes that span start to be rejected
by the collector; the mathematical result is not changed by timing failures.
Unentered phases remain incomplete, not zero-duration. A stopped root closes
with the synthesis result's termination, while a completed phase records its
own return status.

Resolve the OBS-01 `CollectionPlan` before execution. Its fixed span IDs, explicit
`nested`/`spawned` parents, module identities, shards and wall clock domain remain
authoritative. `make_timing_collector(plan, clock, run_id, worker_ids)` admits one
root covering all planned spans, a matching monotonic wall clock, and unique worker
span IDs with no ancestor/descendant pair. Matching includes resolution and calibration
metadata: availability, available value, or unavailable reason and detail. A mismatch
rejects before sampling, so published plan metadata describes the admitted source.
Selecting workers is an explicit work
accounting decision; an empty list means zero selected worker work. A nonempty
`ExecutionContext::run_id` must match the plan. No implicit thread-local parentage,
dynamic ID allocation or implicit scheduling is introduced.

```cpp
context.timing = collector;
auto started = start_timing(context, planned_span_id);
if (auto* scope = std::get_if<TimingScope>(&started)) {
    // Invoke the already admitted operation using its own exclusive workspace.
    scope->close(Termination::resource_limit); // when a resource budget stopped it
}
```

Each planned ID can be started once. Unknown/duplicate IDs return an artifact
error. A scope owns its completion, is movable, and closes once. Move assignment
closes its previous owned scope. Automatic closure records failure while unwinding
an exception, otherwise cancellation for a requested stop or expired execution
deadline, otherwise completion. Deadline uses the existing steady-clock execution
contract, independently of an injected observation clock. Explicit `close(status)`
preserves the caller's termination, including resource exhaustion and generated
operation/contract rejection. Timing never edits a result, family claim, diagnostic,
incumbent or evidence. Exceptions produce `FailedSpan`, not a mathematical failure
claim. OBS-01's completion validator now recognizes every existing `Termination`
variant, including rejection values added by the synthesis contract migration.
No serialized record or schema changed.

`TimingReport` contains an immutable OBS-01 wall/status collection and separate
in-memory metrics in the wall clock's tick unit:

- Inclusive wall duration is end minus start for that span.
- Exclusive wall duration subtracts the union of descendant intervals, clipped to
  the span. In fully nested traces this is exactly the immediate-child union;
  considering descendants also accounts for spawned work that outlives its local
  parent. Overlapping intervals are subtracted once.
- Run wall latency is the root interval only, available when all planned spans
  have closed and lie within the root envelope. It is never the inclusive-span sum.
- Worker work is the sum of the explicitly selected independent worker intervals.
  Nested spans are not selected again. It measures occupied worker wall time,
  including waits, rather than CPU use; it may exceed run latency.

`TimingClock` is the injection port. Read methods are `noexcept`; the collector
serializes reads within one collector so deterministic test clocks need no locking.
A source shared by multiple collectors must itself support concurrent reads. Its dedicated mutex
orders clock samples and span claims, and protects consistent snapshots. Solvers
retain separate workspaces. The plan is immutable; each scope has one owner.
Snapshots copy observations under the mutex, then publish independent OBS-01
shards outside it. They do not consume scopes or double-count previous snapshots.
Live/unstarted scopes are explicitly incomplete, and their full exclusive duration
is unavailable. Snapshot allocation failure returns an artifact error.

`make_steady_timing_clock()` uses `std::chrono::steady_clock` with a collector-local
origin and its declared native tick period. Actual clock resolution and CPU counters
are unavailable by default. Callers may provide an optional CPU clock with its
own period, origin, availability and `thread_cpu`/`process_cpu` scope. Thread CPU is
reported only when the same thread samples both endpoints; its thread identity is
retained. A process CPU delta is reported only for the run root, never for children,
including sequential children, because it contains process-wide activity. CPU
inclusive spans are not additive. CPU metrics and derived exclusive/worker/run
metrics are in-memory report fields; the existing portable OBS-01 schema persists
wall endpoints and statuses only. Persisting richer metrics needs a later artifact
schema revision, not an unversioned extension here.

Backwards/negative wall samples invalidate wall metrics for the entire snapshot.
A nested interval outside its parent, or any span outside the root run, likewise
invalidates wall totals and records a typed diagnostic. Spawned spans may outlive
local parents if the run still encloses them. Missing wall clocks and incomplete
spans retain their precise unavailable reason. CPU regressions or cross-thread
closure invalidate only that CPU measurement; valid wall data remains usable.
Checked arithmetic marks worker-sum overflow unavailable. No plausible timing is
substituted for missing data.

Disabled OBS-01 plans have no span/clock layout. Their collector accepts inert
scopes without sampling clocks, taking the collection mutex, or retaining detail.
`start_timing` with no context collector is also inert. Disabled reports preserve
problem/configuration/run bindings and use `collection_disabled`, with no detailed
spans or CPU metrics. Final outcomes/evidence remain independently publishable.

## Independent oracle and overhead harness

`timing_collector_tests` uses a deterministic fake clock: root `[0,20]`, workers
`[2,12]` and `[5,17]`, and nested `[4,9]`. Literal results are root inclusive 20,
root exclusive 5, first worker exclusive 5, worker work 22; the legacy bucket's
inclusive 47 is explicitly not run latency. Additional tests cover real concurrent
scope claims, escaping spawned descendants, incomplete snapshots, statuses,
clock failures, CPU scope and disabled result/evidence retention. There is no timed
unit-test threshold.

Configure with `-DCSL_BUILD_OBSERVABILITY_BENCHMARK=ON`, build Release, then run:

```powershell
$sourceCommit = git rev-parse HEAD
./tmp/native/Release/observability_overhead.exe 10000 5 $sourceCommit
```

The driver measures the same serial checksum workload with enabled and disabled
collection, alternates first mode per repetition, and prints CSV with setup, scope
loop, publication and end-to-end nanoseconds. Setup/preallocation and snapshot
publication are outside the scope-loop measurement and separately visible. Every
row validates the exact checksum, completed-span count, diagnostics and failures.
No solver or scientific algorithm runs. Record the clean measured source commit,
compiler/build, host/load, raw rows and missing CPU metrics with any reported
measurement. A profiler/limiter check must be separate from reported repetitions.
These synthetic measurements do not establish application-level overhead or a
production scalability claim.
