# Issue #7 capacity and resource policy audit

**Audit base:** `35b663a17cb1a1b60997b549fff32f15e43e82c0`
**Scope:** source audit of current Qhull H/V conversion, H projection / Fourier–Motzkin elimination, nominal predecessor construction, Phase I, `ExecutionContext` / `ResourcePolicy`, and `Executor`; compared with the candidate T-S01 and clipped-stage fixture in the class-level architecture.
**Original scope:** source audit of declared controls and gaps; no benchmark or performance claim and no universal capacity guarantee.

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

These are small structural fixtures. The clipped forward-chain test below verifies only its named nominal fixture; it does not establish backward recovery, complete-family extraction, a composed TEST-08 chain, or admission of a general profile. The individual TEST-08 operator oracles already have behavior-facing tests, summarized below; those tests are separate cases and do not report peak allocations or prove that a selected capacity policy admits a composed chain. Nor do the source row counts bound intermediate Fourier–Motzkin growth for a general input. Any test demonstrating that these analytic cases fit a selected policy establishes only those fixture cases.

### Existing TEST-08 operator behavior tests

| Oracle | Current test evidence | Structural evidence currently asserted | Remaining measurement gap |
|---|---|---|---|
| Unit square intersected with `x+y<=1` | `tests/unit/geometry/polyhedral_intersection_test.cpp`, `unit square intersected with x+y<=1 matches the independent rational triangle`; composed contract case `TEST-08 triangle intersection followed by projection preserves the literal interval` | Standalone case checks six triangle points admitted and three exterior points rejected. The composed case builds four square inequalities plus one cut, checks the resulting H set on three triangle points and one exterior point, and permits at most five H rows. | The composed case records the current row count in this audit but allows equivalent reductions; it does not materialize the triangle to V. |
| Triangle projected onto `x` | `tests/contract/geometry/projection_predecessor_tests.cpp`, `projection of the rational unit-square triangle is the exact interval [0,1]` and `TEST-08 triangle intersection followed by projection preserves the literal interval` | Input H has five inequalities; output dimension is one, no equalities, and literal points 0, 1/2, 1 are admitted while exterior points are rejected. The composed case permits at most four output H rows. | Output bounds allow equivalent row reduction; intermediate Fourier–Motzkin workspace/row counts and allocations are not exposed. |
| Triangle affine image under `(x,y)->x` | `tests/contract/geometry/affine_sum_tests.cpp`, `TEST-08 triangle intersection followed by affine image preserves the literal interval` | The composed case builds the same square/halfspace intersection, checks the intermediate H dimension and row envelope, then runs the registered affine image operation and checks support endpoints 0 and 1 plus request-bound evidence. | Qhull intermediate V candidate counts and allocations are not exposed; the test establishes the literal image support, not a generator cap. |
| `[0,1]+[2,3]=[2,4]` | `tests/contract/geometry/affine_sum_tests.cpp`, `interval Minkowski sum matches independent rational endpoint oracles` | Output is ambient-one V with at least two vertices; every vertex lies in `[2,4]` and both endpoints occur. | Does not assert an exact vertex count or record candidate/temporary allocation counts. |
| Singular map `(x,y)->(x,0)` of the unit square | `tests/contract/geometry/affine_sum_tests.cpp`, `rectangular and singular affine maps retain their actual ambient spaces` | Output remains ambient two, has observed affine rank one, lies on `y=0` within `[0,1]`, and includes both segment endpoints. | Does not assert an exact vertex count or record candidate/temporary allocation counts. |
| Unbounded line preimage | `tests/contract/geometry/projection_predecessor_tests.cpp`, `projection provider rejects the unbounded preimage of y=0 instead of returning finite vertices` | Provider admission rejects the request before execution and verifies that no workspace is created. | Does not execute projection or prove runtime unbounded-result detection; contributes no finite-output capacity counts. |

### Executed clipped T-S01 forward-chain evidence (2026-10-18)

The caller-facing `nominal_forward_tests` now executes the two-stage scalar integrator with `X1=[0,1/2]`, all controls `[0,1]`, and the existing terminal state constraint `X2=[0,2]`. Literal independent interval oracles confirm the stage marginals `R0={0}`, `R1=[0,1/2]`, and `R2=[0,3/2]`. This traverses the registered state/control affine images, Minkowski sum, V-to-H conversion, next-state intersection, state projection, and zero-coordinate feasibility projection. The later stage retains six operation-lineage entries.

The public `ForwardStage` factors expose these observed H shapes (dimension, inequality rows, equality rows, inequality scalar entries, equality scalar entries):

| Stage | Joint transition factor | Post-sum state intersection | Published state marginal |
|---|---:|---:|---:|
| 1, clipped | `(3, 6, 2, 18, 6)` | `(1, 4, 0, 4, 0)` | `(1, 4, 0, 4, 0)` |
| 2 | `(3, 8, 1, 24, 3)` | `(1, 4, 0, 4, 0)` | `(1, 4, 0, 4, 0)` |

These are observed stage-result counts, including retained redundant rows; they are not minimal representations, whole-family five-coordinate counts, backend peak allocations, or hard-cap values. The public tube does not expose each intermediate V image/sum, so their generator counts and temporary allocations remain unmeasured. The test establishes only this clipped forward fixture. The named TEST-08 operations now have composed intersection-to-projection and intersection-to-affine-image tests (above); composed coverage for the remaining operation paths and broader enforceable boundary evidence remain open before any profile ceiling can be selected.

### Executed TEST-08 intersection-to-projection chain (2026-10-18)

The new contract case `TEST-08 triangle intersection followed by projection preserves the literal interval` calls H intersection, then selects and executes the H projection provider on that returned set. Independent literals confirm the intermediate triangle contains `(0,0)`, `(1,0)`, and `(0,1)` but not `(0.75,0.75)`; projection onto `x` contains `0`, `1/2`, and `1` but excludes `-1/4` and `5/4`. The projected result retains numerical operation evidence bound to the exact request.

The observed H shapes (dimension, inequality rows, equality rows, inequality scalar entries, equality scalar entries) are `(2,5,0,10,0)` after intersection and `(1,4,0,4,0)` after projection. The caller-facing test permits at most five and four rows respectively so an equivalent reduced representation remains valid. These are fixture observations, not admission limits or peak allocation counts; the projection registration in this case has no caller row cap, and no Fourier–Motzkin temporary allocation is exposed. MSVC Release verification passed for the focused case (1/45 assertions) and the full `projection_predecessor_tests` executable (25/664 assertions).

### Executed TEST-08 intersection-to-affine-image chain (2026-10-18)

The new contract case `TEST-08 triangle intersection followed by affine image preserves the literal interval` intersects the unit square with `x+y<=1`, then passes the resulting H set to the registered affine image operation for `(x,y)->x`. The intermediate H shape is two-dimensional, has no equalities, and retains at most five inequality rows. Independent support queries establish output endpoints 0 and 1; geometry evidence remains bound to the affine-image request and its triangle input. MSVC Release verification passed for the focused case (1/38 assertions). The test does not expose Qhull candidate counts or allocations and does not establish an output-generator cap.

### Fixture-scoped configured-limit boundary probes (2026-10-18)

Two existing caller-configured limits now have adjacent-value behavior checks. For the intersection-to-projection source with four H rows, `max_rows=3` rejects at input admission, while `max_rows=4` admits the four-row input and the four Fourier–Motzkin combinations; the resulting H representation contains two inequalities whose normalized bounds are exactly `x<=2` and `x>=-2` (tautological zero rows are allowed). For the sum of two two-vertex intervals, `max_candidates=3` rejects and `max_candidates=4` completes with literal support endpoints 0 and 2. The successful results are checked as usable geometry; these probes do not imply shared limits across operations, global profile values, a bound on intermediate allocation before rejection, Qhull output limits, or host-memory enforcement. MSVC Release verification passed for the affine-sum suite (29/1,260 assertions) and projection suite (25/686 assertions).

## Capacity policy recommendation for the first analytic profile

The audit supports defining a fixture-scoped profile, but it does **not** support selecting numerical row, generator, coefficient-entry, or memory ceilings yet. The proposed values of 4,096 intermediate rows, 4,096 vertices/rays, and 65,536 scalar entries are not derived from implementation output, allocation measurements, or a policy decision; they are placeholders and should not be adopted as architecture limits. The five-coordinate and ten-source-row figures are derived from the clipped T-S01 fixture description, but they describe its input envelope only. They do not bound intermediate Fourier–Motzkin growth or backend output.

The next evidence needed to choose finite fixture-profile values is:

1. Complete the observable-operation-chain inventory: unmodified and clipped T-S01 forward fixtures, separate TEST-08 oracles, and rational triangle intersection-to-projection and intersection-to-affine-image cases now have behavior-facing tests. Extend composed-chain tests to remaining operation paths and state the result contract at each step.
2. Extend behavior-facing evidence to all composed chains and record input/output dimensions, row/generator counts, and checked scalar-entry requirements. The TEST-08 H chains record H output shapes but do not expose intermediate V images/sums in the public T-S01 tube; obtain missing counts from a behavior-facing observation seam or separately exercised public operation chain. Keep equalities, inequalities, vertices, and rays distinct.
3. Extend the adjacent-value boundary probes to remaining configurable limits and composed chains. Identify whether each check occurs before expansion, after a conservative bound, or after output generation; prove early rejection only where a conservative size bound is available. For backend-generated output whose size is unknown until enumeration (such as the current synchronous Qhull call), document that a post-generation check cannot provide a hard allocation cap; require a separately reviewed backend admission bound or interruptible allocation before making that claim. Any capacity stop must preserve request identity and completed lineage and must never present a truncated result as equivalent.
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
- `include/csl/reachability/nominal_forward.hpp:8-31` and `tests/unit/reachability/nominal_forward_tests.cpp` — public forward-stage factors and the unmodified/clipped T-S01 literal marginal and shape-count oracles.
- `tests/unit/geometry/polyhedral_intersection_test.cpp` — rational square/triangle intersection membership oracle.
- `tests/contract/geometry/projection_predecessor_tests.cpp` — rational triangle projection, composed triangle intersection-to-projection chain, and unbounded line-preimage admission rejection.
- `tests/contract/geometry/affine_sum_tests.cpp` — interval Minkowski endpoint oracle and singular square-to-segment affine image.
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

Follow-up verification in isolated worktree `test/issue7-ts01-clipped-capacity-20261018`:

- MSVC Release configure with `cmake --preset dev-windows` — passed.
- `cmake --build --preset dev-windows --target nominal_forward_tests` — passed.
- `build/dev-windows/Release/nominal_forward_tests.exe --test-case="clipped T-S01 chain retains literal marginals and stage shape counts"` — passed (1 case, 81 assertions).
- Full `nominal_forward_tests.exe` — passed (9 cases, 605 assertions).
- `git diff --check` — passed.

No benchmark or performance measurement was run. This follow-up establishes executed behavior for the stated clipped fixture only; it does not establish runtime peak memory, backend interruptibility, selected profile thresholds, or universal capacity guarantees.
