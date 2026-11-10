# BTULSHOR source-faithful modules implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Deliver directly transcribed, replaceable REACH/KPABEP/MODIF C++ modules and common-input numerical comparisons.

**Architecture:** One raw module owns Pascal storage and arithmetic. MODIF and KPABEP ports allow explicit substitution without claiming the modern hull certificate contract. Reports check unchanged raw outputs independently.

**Tech Stack:** Existing C++20, CMake, doctest, JSON/report tooling; private extracted FPC oracle only.

**Spec:** `docs/superpowers/specs/2026-11-10-btulshor-faithful-port-design.md`.

## Global constraints

Preserve source SHA06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442 and exact source operation/branch order. Binary64 target, no historical bit-identity claim. Preserve source p codes separately from guards. REACH literal n-stride padding and by-value inputs. No modern solve/repair inside source kernels. Keep private original bodies out of public bundles. User-approved remaining technical decisions are delegated; no further preference checkpoint is required.

## Review focus

- REACH nr<n padding and by-value semantics; test caller inputs unchanged and nr>n refused.
- Duplicate/edge/collinear and tied-pivot cases; pin source outputs and independently check geometry.
- Zero structural columns in MODIF and p1/p2/p3; literal tiny fixtures test each branch.
- Dense capacity, pivot exhaustion and nonfinite arithmetic; preserve distinct wrapper outcomes.
- Pluggable MODIF/KPABEP results; test substitution and malformed dependency refusal.

## Task 1: raw module and focused behavior tests

Files: create public header, source and `tests/unit/geometry/legacy_btulshor_test.cpp`; modify `src/geometry/Module.cmake` and `Tests.cmake`; add contract `docs/contracts/legacy-btulshor.md`.

Interfaces: exactly the spec's request/result records, Outcome<T>, ModifPort/KpabepPort and entry points. Report workers consume these signatures.

- [ ] Add failing literal tests for MODIF rows3/columns0 with x=(1,0,-1) ->p2 and x=(1,0,0)->p1; rows3/columns1 A=(-1,0,-1)^T,x=(1,0,-1)->p3.
- [ ] Run focused test to confirm missing implementation fails.
- [ ] Transcribe all three source routines with boundary adaptation/guards and explicit port dependencies.
- [ ] Add strict tie fixture rows4/columns2 with two identical columns (1,1,0,-2)^T,x=(1,1,0,-2); first pivot enters1/leaves1. Add logical layout, by-value, injected port, actual pivot-budget and malformed-input tests.
- [ ] Compare raw oracle fixtures supplied by root; add analytic independent hull checks, preserving any old algorithm failure.
- [ ] Run focused tests and commit only owned module/test/CMake/contract files.

## Task 2: independent private source oracle

Owner root; private scratch outside repository. Consume source hash and public interface only.

- [ ] Extract original procedures verbatim with minimal explicit Double type shim; compile with hash-verified private FPC toolchain.
- [ ] Run tiny p/status, square/interior/duplicate, sign, collinear and REACH fixtures; retain raw outputs and source/toolchain manifests.
- [ ] Compare C++ outputs and traces; freeze safe non-source fixture records for public regression evidence. Do not copy private source bodies into repository.

## Task 3: report/comparison adapter and minimal visual example

Files: create `benchmarks/reporting/btulshor/` driver and renderer; add opt-in target in `cmake/OptionalReports.cmake`; immutable output under `reports/algorithm-results/`; use existing publication discovery/staging patterns.

Interfaces: call source_modif_port/source_kpabep_port and direct functions from task1; keep method IDs separate from comparator providers and exact checker results.

- [ ] Capture common 2D/3D/4D deterministic clouds using raw legacy and existing supported QuickHull/LP/paper modules; record every refusal/inconclusive/incorrect outcome.
- [ ] Independently validate retained hulls; compare stable IDs/coordinates without modifying raw output.
- [ ] Produce English HTML, JSON/raw provenance, offline ZIP and labelled 2D input/output plot. Any timing uses existing measurement checks and records interval/environment/limitations.
- [ ] Integrate saved bundle with cumulative Pages publication; verify local links/renderer then actual deployed bytes, ZIP and desktop/mobile figure behavior.

## Task 4: integrate, review and close revised issues

- [ ] Independent mattpocock standards/specification reviews of fixed base/head; fix findings and re-review affected scope.
- [ ] Focused native and installed-consumer checks; exact-head full native/report CI; inspect release/package effect and source boundaries.
- [ ] Merge reviewed code and verify main publication. Update #2 and #6 with concrete module/comparison evidence; close only after selected deliverables pass.
