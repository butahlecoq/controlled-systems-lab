# Source-faithful BTULSHOR C++ modules

The owner approved extractable old algorithms as interchangeable C++ modules for comparison, preserving operation order, pivot choices, phases, tolerances and original status codes. They explicitly delegated technical decisions and requested implementation agents and independent mattpocock reviews. This design records those decisions for issue #2; it does not require recovering the full old project or attributing a historical table-generating revision.

## Source and fidelity

Use the recovered A06 `btulshor.pas`, SHA-256 `06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442`: REACH lines41–72, KPABEP73–127, MODIF128–213. Preserve literal source control flow and scalar accumulation order, strict comparisons, first-winner ties, phase changes, `1e-5` in KPABEP, `1E11` ratio sentinel, and raw p values. No modern solver, sorting, normalization, perturbation, duplicate removal or post-result repair inside the port. Source variable names/gotos may be retained where they improve line correspondence.

C++ binary64 `double` is the explicit port representation. It is not a claim of historical bit identity. Disable floating contraction/fast-math for this target. Technical bounds/finite-value guards and allocation replace unavailable Pascal fixed types; stopped/refused outcomes must never masquerade as original p=1/2/3. A pivot budget stops a cycle as a wrapper outcome before the next pivot; a routine may still complete after exactly its maximum allowed pivots. Bounded trace truncation continues computation without altering arithmetic.

REACH uses BEP stride **n**, with nr logical primitive-control coordinates and n-stride private padding. Refuse nr>n for this literal source layout. A/B/BEX/BEP are by value in Pascal: callers' inputs remain unchanged. Preserve the translated-copy ordering, including the final control vertex translated into the first output block. Track original point IDs alongside swaps without affecting numeric decisions.

## Approaches and synthesis

Two independent sketches considered a compact request/result function module and a provider composed of three virtual routine objects. Select the compact design, adding the second sketch's explicit dependency injection at MODIF and KPABEP call boundaries. A single raw module owns all Pascal array conventions; public callers use existing row-major `csl::Matrix` and point vectors. Do not adapt the old code to HullReducerPort, whose exact-certificate semantics it does not satisfy.

The sketches and score rubric are private working artifacts. Configured candidates and judge pool are all from the same model family; no cross-family judge is available. Root selects the synthesis by source fidelity, explicit module substitution, small API, honest failure semantics and independently checkable outputs.

## Interface contract

Create `include/csl/geometry/legacy_btulshor.hpp` and `src/geometry/legacy_btulshor.cpp`, namespace `csl::geometry::legacy_btulshor`, target `CSL::legacy_btulshor`.

- `Limits`: max_pivots default100000 per MODIF, max_dense_entries1048576, capture_trace false, max_trace_events4096. Use checked products before allocation.
- `StopReason`: invalid_input, capacity_limit, pivot_limit, non_finite_arithmetic, invalid_dependency_result. `Stopped` owns reason/message. `Outcome<T>` is `variant<T,Stopped>`.
- `ModifRequest`: row-major `Matrix a`, `Vector x`, `double epsilon=1e-5`, `int initial_status=0`. Rows>=3, x length=rows, columns may be zero; initial status0 or1. NB is initialized by the original algorithm, not supplied by callers.
- `PivotStep`: source one-based entering/leaving indices, phase and ratio. `ModifResult`: original_status, x, basis, pivot count, ordered pivot trace, phase sequence and trace_truncated. Trace fields may be empty when disabled.
- `ModifPort`: owning string id and function `Outcome<ModifResult>(const ModifRequest&,const Limits&)`.
- `KpabepResult`: raw retained points, retained_indices into caller input, modif_calls, pivots, bounded candidate trace and trace_truncated. A candidate trace records original candidate index, original status and pivot count.
- `KpabepPort`: owning string id and function `Outcome<KpabepResult>(span<const Vector>,const ModifPort&,const Limits&)`.
- `ReachRequest`: row-major matrices a,b; initial_points and control_points. A is n×n, B is n×nr, every initial point has n coordinates and every primitive control point has nr coordinates. Derive dimensions from these types, zero-pad private BEP columns to n entries, and document the nr<=n restriction.
- `ReachVertexSource`: original initial-point index and control-point index. `ReachResult`: raw points, source_vertices, kpabep_calls, modif_calls and pivots.
- `modif(request,limits={})`; `source_modif_port()`; `kpabep(points,modif_port=source_modif_port(),limits={})`; `source_kpabep_port()`; `reach(request,kpabep_port=source_kpabep_port(),modif_port=source_modif_port(),limits={})`.

Use exact names above so report/test tasks can work independently. Port factories expose distinct stable IDs `csl.legacy.btulshor.modif.source-v1` and `csl.legacy.btulshor.kpabep.source-v1`; the reach function identity is `csl.legacy.btulshor.reach.source-v1`. Replacement ports stay explicitly named. A function result is raw numerical behavior, not a certified LP/hull result. Reject malformed pluggable dependency outputs rather than accessing wrong-sized arrays. Do not reject p=3 merely because it is not a hull certificate; KPABEP uses only p=2 to retain a point.

## Verification and delivery

A private FPC shim extracts only the three original bodies, replaces unavailable imported type declarations with explicit Double arrays, and executes deterministic fixtures. Original Pascal body text stays private. Record compiler package/hash, source hash, exact extraction boundaries, fixture input/output and all shim changes. Compare C++ raw p, coordinate order, basis and pivots, with declared numeric tolerance. This tests a compatible extracted source, not the missing historical compiler/project.

Meaningful public tests cover p1/p2/p3, strict entering/leaving ties, candidate order/sign flips, interior/edge/duplicate/collinear clouds, private padding, by-value inputs, unsupported nr>n, capacity/invalid/nonfinite guards, a real pivot limit and injected routine substitution. Use independent exact 2D hull checks and preserve discrepancies as source outcomes. Provide a common-input comparison with QuickHull and existing LP/paper providers where supported, unmodified raw outputs and honest statuses, plus a small labelled 2D plot and English HTML/offline evidence.

No FPC runtime/build dependency enters CSL. Installed-consumer and native/sanitizer checks apply to the public C++ target. Numerical reports follow existing immutable bundle/Pages evidence gates. New API/package impact belongs in the implementation PR. No original source project is publicly redistributed. Source translation is the owner-requested implementation, not an assertion of release lineage or ITIS17 correspondence.
