# Isolated synchronous execution

`<csl/execution/executor.hpp>` and `CSL::execution` provide typed batches over
retained registry preparations. This is a compatible-toolchain source interface;
the canonical source contract remains revision 1.4. No mathematical DTO, registry
port, solver configuration or evidence rule is replaced.

## Preparation and ownership

`make_task(TaskId, PreparedPipeline<Port>, ResourceUse)` accepts exactly one typed
prepared port. The overload taking `PreparedStrategy` produces a
`Task<registry::StrategyPort>`. Its immutable private storage owns the prepared
request/factory snapshot, copied declaration and complete provenance. The source
registry, request, preparation and declaration can be destroyed before execution.
The existing registry rules still apply: callbacks must retain anything they use,
immutable payloads must honor their contract, factories must be safe to call
concurrently and must return a fresh exclusive workspace. Capturing a dangling
reference or a shared mutable backend in an adapter violates those rules.

A task exposes no workspace or arbitrary execution callback. Each admission
creates a new exclusive `BoundWorkspace`; each creation is destroyed exactly once
before its reservation is released. A prepared strategy may perform repeated
solves and use a warm start inside its private workspace. Another task or later
batch receives a fresh workspace and fresh LP attempt sequence. The executor does
not share basis state, solver instances or caches across tasks. Tasks may be
copied, and their immutable descriptions may be shared between independent runs.

`make_executor(ResourcePolicy, EnforcementRequest)` validates and privately copies
the policy into a shared immutable owner. `resources()` supplies that exact owner
for the caller's `ExecutionContext`. An equal-valued separately owned policy is
rejected. Tolerances must be finite and nonnegative, `run_id` nonempty, mode known,
and task IDs unique within a batch. All declarations are checked before any
factory runs. `run<Port>(span, context, mode, limit)` is synchronous: its input task
span, context and executor must remain stable and alive until it returns. The
executor copies context and result metadata before starting work. A second run on
the same executor, including recursive use from an adapter, immediately returns
`Diagnostics` at `execution.busy`. Independent executors represent independent
resource domains; there is no process-wide aggregate scheduler.

The outcome type is derived from the port's actual `BoundWorkspace::run` return
type. New registry ports need no central execution result alternative. The owning
outcome must be nothrow move-constructible. Custom ports must supply owning
results; a nothrow movable raw pointer alone would not establish ownership.

## Admission and resource meaning

Sequential mode invokes on the caller's lane. Bounded parallel mode uses at most
`min(task_count, outer_workers)` joined worker threads. At most `outer_workers`
workspaces are active, and each reserves `threads_per_worker` compute participants.
The existing policy requires the aggregate reservation not exceed `total_threads`.
A resource declaration has a positive `peak_compute_threads`, a nonempty
`thread_assumptions` description, an optional workspace byte reservation and one
of the three `CallStopSupport` values. A declared thread peak larger than a lane's
capacity is unsupported before any work starts.

The declaration includes the invoking lane plus every simultaneously active
backend/BLAS/helper compute participant. The synchronous coordinating caller and
stop-notification machinery are not additional compute reservations. The adapter
must configure and honor its stated native thread footprint. The current ports
cannot independently enforce or inspect native pools. Reports therefore always
say `NativeThreadEnforcement::declared_only`; requests for actual native thread
enforcement return unsupported. This is neither a native-thread audit nor a
throughput or speedup claim. `CallStopSupport` is also a retained adapter
declaration, not an executor certification of interruptibility.

With finite `memory_bytes`, every task needs a byte reservation. Credits are
reserved before its factory and retained through invocation and complete
workspace destruction. A reservation larger than the entire cap is skipped
without invoking its factory. A temporarily unavailable reservation waits in FIFO
admission order; smaller later tasks do not pass it. Zero-byte reservations are
valid declarations. They do not promise zero native allocation. With no memory
cap, reservations are accounted when all are supplied and the sum is representable;
otherwise the reported peak is absent. Overflow is never wrapped into a small
reported value. This peak describes active declarations, not measured bytes.

Memory accounting excludes input snapshots, tasks, collector metadata, retained
results, allocator overhead and native/BLAS allocations not covered by an adapter's
reservation. It does not impose a heap or RSS limit. A request for a hard memory
limit is unsupported. `MemoryEnforcement::active_reservations_only` and
`unlimited_accounting` distinguish the two modes honestly.

`AdmissionLimit::max_admitted_tasks` counts factory admissions, including creation
failures. Zero is valid. Oversized skipped reservations do not count. Exhaustion
closes admission and skips unclaimed tasks; it does not cancel already admitted
work. Outer-lane, memory and task-count admission are enforced, while native
thread and native heap limits have the limitations above.

## Stops, failures and result preservation

The supplied stop token is observed through a callback registered for the entire
batch through worker joins. A linked batch token combines external cancellation
and internal failure. Every adapter receives that linked token, the original
copied deadline, the executor's policy owner and the copied numerical policy.
Admission and invocation boundaries also observe external cancellation and the
monotonic deadline. A pre-stopped or pre-expired batch invokes no factory. A stop
observed after creation skips invocation but destroys the created workspace.

Cancellation/deadline closes admission, asks active work to stop cooperatively and
wakes credit waiters. There is no watchdog, forced interruption, detached thread
or guarantee of a deadline on return. A noninterruptible factory or native call
may finish arbitrarily late. Its real returned outcome is retained unchanged,
including a completed result after cancellation, or a partial incumbent with
unestablished claims and its original evidence. The executor does not fabricate
infeasibility, optimality, family completeness or a numerical failure.

Each input position owns a `TaskRecord` with stable ID/order, provenance,
declaration, timing and exactly one of:

- `Returned<Port>`: the canonical port value, including its own `Unsupported`.
- `Skipped`: cancellation, deadline, task-count exhaustion, oversized reservation
  or a batch failure prevented this call. A created-but-not-invoked task has
  creation timing; an unadmitted task has none.
- `TaskFailure`: exception pointer, creation/invocation stage and allocation versus
  adapter-exception category. Re-throwing preserves the original exception.

Metadata, slots, bindings and worker-vector capacity are allocated before work.
A prework allocation failure propagates `std::bad_alloc` and releases the busy
guard; no guaranteed allocation-free diagnostics object is promised. Once a
factory or call starts, exceptions are stored in preallocated records, admission
closes, the linked token is requested and all workers drain. Previously returned
values survive. A partial thread launch failure is retained in `launch_failure`
and similarly stops/drains successfully launched workers. Destructors must not
throw. Standard mutex/thread infrastructure failures and an adapter that never
returns cannot be turned into a guaranteed finite drain by this interface.

Result slots are disjoint; the scheduler alone protects admission, credits and
batch stop observations. It makes no user collector callback. Stop requests and
workspace destruction occur outside the scheduler mutex. Workers are joined
before dispatch returns; callback deregistration then waits for any in-flight
external notification outside that mutex. Metadata and canonical outcomes remain
owned after the task, context, registry, tokens and executor are destroyed.

## Timing authorities and reproducible intervals

All raw times use `std::chrono::steady_clock` and are process-local observations.
They are not UTC timestamps, serializable cross-process clock values or benchmark
measurements. Per-task `queued_at`, optional `admitted_at`, creation start/finish,
call start/finish and `released_at` distinguish work that was never started.
Creation/invocation finish is also recorded when that stage throws. Release is
recorded after destruction and credit release.

`BatchTiming` deliberately owns four different stop/completion authorities:

- `configured_deadline`: the original optional deadline, including extreme values.
- `admission_closed`: the first close cause and observation time; later events
  never overwrite it. It may be task-count exhaustion or an internal exception.
- `external_cancellation_observed_at`: when the registered callback observes the
  caller token. It is recorded even when an earlier internal stop already requested
  the linked token. It is an observation, not the caller's exact request time.
- `workers_joined_at` and `completed_at`: all worker joins, then final completion
  after external callback quiescence and report finalization.

For example, an adapter fails at t1, the linked-token observer triggers external
cancellation at t2, and a sibling noninterruptible call returns at t3. The report
retains the first failure closure at t1, the independent callback observation at
t2, and the real call finish at t3. It supports worker drain `joined-t1`, external
cancellation late return `t3-t2` when that observation lies inside the call, and
post-join callback drain `completed-joined`. A cancellation observed after a call
finished supplies no cancellation-latency sample for that call. The first closure
time must never substitute for external cancellation time.

For deadline lateness, compare the finish time with the configured deadline first;
if finish is at or before it, lateness is zero. Otherwise subtract only with a
checked representation or suitably wider arithmetic: extreme timepoints can
make signed clock-duration subtraction overflow. No derived duration helper,
performance collector or exporter is introduced here. The returned raw fields
supply the required observations without manufacturing a bound on native latency.

## Evidence and verification limits

The unit suite uses independently authored interval optima on `[-1,4]` for
`3x+2`, `-2x+2` and `2`; both sequential and parallel paths agree with the literal
answers within the copied numerical tolerance. Controlled gates establish
out-of-order completion, actual compute-participant peaks, cancellation during
creation/call, retained complete/partial results, credit admission, failures,
callback lifetime and nonreentrancy. The failure→external-stop→late-return oracle
uses causal handshakes with no sleep, threshold or watchdog. Registered strategy
fixtures only forward witnesses and deliberately leave family/optimality claims
unestablished. They do not implement synthesis algorithms.

The standalone installed consumer uses only `find_package(CSL CONFIG)` and
`CSL::execution`. Both existing neutral header-order clients retain their original
numeric-only link boundary and runtime checks. The public dependency audit remains
applicable. Actual native enforcement, arbitrary scheduler deadlock recovery and
OS thread-creation exhaustion are not certified by these analytic fixtures.
