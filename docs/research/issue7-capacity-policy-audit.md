# Issue #7 capacity and resource policy audit

**Audit base:** `35b663a17cb1a1b60997b549fff32f15e43e82c0`
**Scope:** source audit of current Qhull H/V conversion, H projection / Fourier–Motzkin elimination, nominal predecessor construction, Phase I, `ExecutionContext` / `ResourcePolicy`, and `Executor`; compared with the candidate T-S01 and clipped-stage fixture in the class-level architecture.
**Not in scope:** benchmark execution, performance measurement, changing implementation, or establishing universal numerical behavior.

## Findings

### Capacity classification

| Area | Current limits and stop behavior | Classification |
|---|---|---|
| Qhull conversion | `QhullOptions` has optional `max_ambient_dimension` and `max_input_rows`; empty optionals mean no policy limit. Admission also applies Qhull signed-`int` dimension/count bounds and host/container checks. The conversion observation has output row/generator counts, but there is no output-size admission cap. Context cancellation/deadline is checked before conversion and around LP queries and before publishing; the Qhull call itself is a synchronous native call, so it is observed after return rather than interrupted in flight. | Optional caller-configured local admission; native integer/container limits; no output cap; in-flight Qhull stop is unverified/noninterruptible. |
| H projection | `ProjectionOptions::max_rows` is optional. The H materializer checks input H row count and every Fourier–Motzkin intermediate `zero + positive × negative` row count against the option and checked `size_t` products/storage. It checks cancellation/deadline before each eliminated coordinate and each positive/negative pair, with finite-arithmetic checks. No H output generator cap applies because the output is H; final H rows remain covered by the row cap. | Optional caller-configured local admission; checked arithmetic overflow guard; cooperative checkpoints. No default row cap. |
| V projection | Copies selected coordinates from all input vertices and rays, checking storage multiplication overflow and stop between generators. It has no `max_rows` parameter in the V path and no output-generator cap. | Overflow guard only; caller stop/deadline; no policy output cap. |
| Nominal predecessor | Preparation combines H/singleton/empty/universal state, control and target constraints into a joint `[x,u]` H set, pulls target rows back through `A,B,offset`, and checks dimension/row/storage arithmetic overflow. It does not itself receive a row/memory budget or poll the context during this construction. The selected projection provider admits the concrete projection request; projection option limits apply only if configured on that registration. | Local overflow guards; no predecessor-level cap or cancellation/deadline during preparation. Later projection limits are registration-local. |
| Phase I | `Options` defaults: 10,000 pivots, 1,048,576 dense entries, and trace limit 128. The estimate rejects `m(m+n)` above `dense_entry_limit`, Eigen/index/permutation extents and checked byte arithmetic; estimated workspace bytes are compared against `ExecutionContext.resources.memory_bytes` when present. It polls cancellation/deadline at solve boundaries, row blocks, and pivot work. The estimate is an accounted model, not a native-heap enforcement mechanism. | Fixed local algorithm limits; caller-selectable `ResourcePolicy` memory admission against an estimate; cooperative stop checkpoints. No process memory cap. |
| `ExecutionContext` / shared resources | `ResourcePolicy` requires positive total thread, outer worker and threads-per-worker values with `outer_workers × threads_per_worker ≤ total_threads`. `memory_bytes` is explicitly “admission/accounting, not enforced”. The context carries a shared immutable policy pointer, stop token, optional deadline and numerical policy; it does not define default time or memory values. | Caller-supplied shared policy and deadline; no default deadline or hard memory cap. |
| `Executor` concurrency | A bounded-parallel batch starts `min(task_count, outer_workers)` workers; sequential mode uses one calling thread. Tasks must declare positive peak threads and assumptions, and a task declaration cannot exceed `threads_per_worker`. A finite memory budget requires each task to provide a workspace reservation; reservations gate active admission and are released after task completion. `AdmissionLimit::max_admitted_tasks` is optional and caller-set. `Executor` prevents concurrent batches on the same instance, but separate executors are not coordinated. Native thread enforcement is explicitly `declared_only`; hard memory enforcement requests are rejected. | Per-executor/per-batch caller-set admission and accounting; no process-global thread/heap cap; no native thread enforcement. |

### Fixture envelope

The architecture’s candidate T-S01 case uses two stages, scalar state/control, and `[0,1]` controls. Its clipped companion adds `X1=[0,1/2]`; the canonical joint relation has five coordinates, four equality rows and six source inequality rows before permitted reduction, and is a segment with two extreme points and no rays. The class-map labels these counts as minimum regression requirements only; they exclude backend auxiliaries and do not establish global caps. The TEST-08 operator companions are two-dimensional (triangle, interval projection, singular image) and have a three-vertex triangle oracle.

These are small structural fixtures, but the current source does not prove that every proposed operation chain is implemented or admitted: the class map explicitly says H/V conversion alone is not intersection, projection, predecessor, or family extraction. Nor do the source row counts bound intermediate FM growth for a general input. Any test demonstrating that these specific analytic cases fit a selected policy would establish only those fixture cases.

## Capacity policy recommendation for the first analytic profile

The audit supports defining a fixture-scoped profile, but it does **not** support selecting numerical row, generator, coefficient-entry, or memory ceilings yet. The proposed values of 4,096 intermediate rows, 4,096 vertices/rays, and 65,536 scalar entries are not derived from implementation output, allocation measurements, or a policy decision; they are placeholders and should not be adopted as architecture limits. The five-coordinate and ten-source-row figures are derived from the clipped T-S01 fixture description, but they describe its input envelope only. They do not bound intermediate Fourier–Motzkin growth or backend output.

The next evidence needed to choose finite fixture-profile values is:

1. Implement or identify the complete analytic fixture operation chains and their observable result contracts, including T-S01, its clipped companion, and TEST-08. The architecture currently cautions that H/V conversion alone does not prove intersection, projection, predecessor, or family extraction.
2. Add behavior-facing tests that execute each full chain and record exact per-stage input and output dimensions, row/generator counts, and checked scalar-entry requirements. Keep equalities, inequalities, vertices, and rays distinct.
3. Derive the smallest structural limits that admit those exact chains, then add boundary tests proving the limit admits each required result and rejects the first over-limit request before allocation or publication. A capacity stop must preserve request identity and completed lineage and must never present a truncated result as equivalent.
4. Keep those values explicitly fixture-profile scoped. A broader profile requires separate workload evidence and a policy decision; fixture results cannot establish universal capacity, host-memory enforcement, native-thread enforcement, or numerical completeness.
5. For concurrent scenarios, use one caller-owned `ExecutionContext`/`ResourcePolicy` and per-task workspace reservations. Keep the existing warning that reservations are accounting/admission only, and do not describe separate `Executor` instances as sharing a process-wide cap.
6. Keep algorithms serial within each task and use outer executor workers for scenario concurrency. Provide cancellation/deadline for each run. Qhull remains synchronously stoppable only at its pre/post-call checkpoints. Preserve Phase I's pivot/dense/trace guards and describe its workspace estimate as admission accounting, not a hard allocator cap.

This recommendation establishes the evidence sequence without inventing capacity thresholds. It leaves exact fixture-profile values and all broader capacity claims open until the operation-chain tests produce those counts and boundary evidence.

## Source evidence

- `include/csl/adapters/polyhedral/qhull.hpp:28-44` — optional Qhull admission options and selected LP registration.
- `src/adapters/polyhedral/qhull.cpp:27-39, 102-120, 199-210, 246-253, 405, 459, 512, 564-590` — stop checks, Qhull native input limits, caller admission, pre/post-call stops, capability admission. `ConversionObservation` records output counts at `include/csl/adapters/polyhedral/qhull.hpp:7-25`; no output cap is declared there.
- `include/csl/geometry/polyhedral_projection.hpp:10-16, 50-55` — optional projection row budget and materializer API.
- `src/geometry/polyhedral/projection.cpp:112-125, 130-145, 147-194, 200-214, 227-248` — checked row arithmetic, FM intermediate count, stop checkpoints, and V generator copying without a V output cap.
- `include/csl/reachability/nominal_predecessor.hpp:7-16, 34-52` and `src/reachability/nominal_predecessor.cpp:60-83, 110-177` — H-only operands, separate prepared projection workspace, overflow-checked joint pullback assembly without an execution context or policy during preparation.
- `include/csl/optimization/phase_one.hpp:18-27, 36-50` and `src/optimization/phase_one/simplex.cpp:32-56, 81-84, 218-257, 275-338` — local defaults/profile estimate, context polling, caller memory estimate check and pivot stop.
- `include/csl/execution/contracts.hpp:10-23` and `src/contracts/execution.cpp:14-19` — shared caller policy, optional deadline and validation of declared thread arithmetic; memory explicitly not enforced.
- `include/csl/execution/executor.hpp:11-20, 49-57, 121-145, 176` and `src/execution/executor.cpp:30-37, 51-73, 87-131, 151-219` — per-task declarations, enforcement labels, admission checks, cancellation/deadline, reservations and worker launch/join behavior.
- `docs/superpowers/specs/2026-10-12-class-level-system-architecture.md:587-595` — architecture gates, exact T-S01 and clipped fixture envelope, TEST-08 companion cases, and explicit warning that fixture counts are not global caps.
- `docs/superpowers/specs/2026-10-12-class-level-system-architecture-synthesis.md:36-38` and `docs/superpowers/specs/2026-10-12-cross-cutting-api-decisions-proposal.md:13-19, 44-52, 66-68, 84-87, 92` — gate status, common-context/outer-concurrency proposal, declared-vs-enforced policy, and unresolved global capacity decision.

## Method and verification limits

Commands run from the audited worktree:

- `git rev-parse HEAD` — returned the requested base `35b663a17cb1a1b60997b549fff32f15e43e82c0`.
- `rg -n` and numbered `Get-Content` reads over the source and architecture paths listed above — used to locate and inspect implementation contracts and fixture definitions.
- `git diff --check` — run after writing this report.

No benchmark, performance measurement, build, test, or external-source lookup was run. This report establishes source-declared controls and gaps only; it does not establish runtime memory use, backend interruptibility, fixture completion, selected profile thresholds, or a universal capacity guarantee.
