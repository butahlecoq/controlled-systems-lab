# EXP-06 geometry pilot design

## Problem

Issue #423 requires one bounded legacy-versus-modern 2D hull comparison on the same exact input, checked by the independent geometry oracle and rendered from saved evidence. The existing A29/A30 artifact is a Python transcription with its own exact checker. GEO-06 is a fixed three-case C++ QuickHull benchmark. OBS-04 stores paired comparison records, but its current run reference only accepts `csl.run-statistics` records for controlled-system programs. Geometry executions need truthful immutable references without pretending to be solver runs.

## Usage

The pilot runs the checked-in square fixture through the existing A29/A30 port and the existing QuickHull library. Capture retains every attempt. The comparison artifact uses the canonical paired-record envelope and references method-run artifacts with explicit runtime and source identity.

```text
fixture.json -> A29/A30 Python port -> exact Fraction checker -> method-run artifact
fixture.json -> C++ QuickHull      -> exact Fraction checker -> method-run artifact
method-run artifacts + comparison spec -> csl.comparison-record/1
csl.comparison-record/1 -> saved-only HTML, SVG, CSV, ZIP and Pages staging
```

No public geometry algorithm API changes. The new artifact API adds a method-run record for computations that are not `csl.run-statistics` controlled-system executions.

## Shape

Keep the geometry pilot in a dedicated EXP-06 path. Do not change the existing GEO-06 three-fixture report contract. Keep A29/A30 and QuickHull as separate executable owners. Reuse the independent exact source-hull checker for both results.

The record model has four distinct layers:

- `GeometryFixture`: fixture ID, ordered binary64 point rows, canonical manifest bytes and digest.
- `MethodIdentity`: method ID/version, source-file hashes, deviation-file hash, runtime/interpreter or executable identity.
- `MethodRunArtifact`: common problem/configuration/request/input identities, terminal attempt status, method identity and opaque canonical result payload. The artifact is immutable and content addressed.
- `ComparisonAttempt`: arm and repetition indexes, status, run reference and method-specific measurement payload. The existing encoder continues to accept control `RecordedRunArtifact` values and gains a typed `RecordedMethodRunArtifact` path.

At the boundary, the encoder validates the `csl.external-method-run/1` structure and cross-checks run ID, content hash, problem ID, configuration ID, request digest, input-manifest attachment, arm identity and termination status against the comparison spec. It does not interpret geometry output. The EXP-06 saved-report validator checks output indices, exact hull coverage, checker budget/status, runtime identity, attempt counts and derived file hashes.

The comparison record remains `csl.comparison-record/1`. The comparison spec uses its versioned paired-arm format. `csl.geometry-hull-input/1` names the byte encoding attached to every method-run artifact. Unknown external run schemas remain rejected. Existing control-record callers and wire bytes remain unchanged.

Use distinct method IDs for `csl.geometry.quickhull-2d` and `csl.geometry.a29-a30-python`. Keep cross-runtime durations as method-local observations. They have no common performance group and produce no ratio, ranking or winner.

## Synthesis decision

Use the dedicated EXP-06 capture, artifact and report path from Candidate B. Preserve the existing GEO-06 fixed-fixture report. Graft Candidate A's explicit capture/collection/render phases and its emphasis on GEO-06 schema isolation. Do not reuse `csl.comparison-record/1` by fabricating control `RunStatistics`; instead extend the comparison artifact API with a separate typed method-run artifact that the comparison envelope can reference. This directly addresses the judge's main finding while keeping the program's comparison identity and attempt retention contract.

The arena judge preferred Candidate B for the paired shared-input experiment, but scored its run-record semantics 2/5 until this gap was resolved. The selected design resolves the gap with explicit validation for a versioned method-run artifact. The arena red-flags reference and cross-judge prompt files were absent from the installed skill package; the design was screened against the runner prompt's boundary, identity, shared-state, and interface-depth requirements.

## Tradeoffs accepted

- We accept a small extension to the artifact API in exchange for recording non-control algorithms without solver-shaped data.
- We accept one dedicated geometry report path in exchange for preserving the existing GEO-06 report meaning.
- We accept separate A29 and QuickHull runtime observations in exchange for honest provenance; their timings are inconclusive across languages.
- We accept one fixed fixture in exchange for meeting the bounded pilot without implying EXP-02 ladder completion.

## Alternatives considered

- Add A29 as another GEO-06 CSV method. This changes a fixed three-case QuickHull-only report into a different experiment and risks aggregating incomparable runtimes.
- Emit an EXP-06-only custom comparison envelope. This avoids touching the comparison artifact API but duplicates content identity, attempt ordering, reference validation and failure status rules.
- Encode hull runs as `csl.run-statistics`. This reuses a current type but misstates a geometry algorithm as a controlled-system program.

## Work phases and verification gates

1. **Baseline and contract:** captured the current GEO-06 smoke, A29 tests and source-provenance limitation before edits. Define the exact fixture bytes and method-run fields.
2. **Artifact bridge:** implement and verify method-run encode/decode and paired-record identity/status checks. Keep current run-record encoding tests green.
3. **Capture:** adapt the GEO-06 QuickHull driver for the shared fixture, add an A29 capture adapter, alternate warmup and measured attempts, enforce suite wall/virtual-memory limits, and retain raw output and failures.
4. **Independent checks:** run the exact source-hull checker for both methods and save negative controls for omitted corners and accepted redundant points.
5. **Saved report:** build content-derived report files and a deterministic 2D SVG from the saved record. Verify regeneration does not execute either method.
6. **Delivery:** add a dedicated explicit stager and main-only Pages workflow hook; run focused tests, native CI, and exact-head independent standards and specification reviews. Merge only after all required gates pass.

The falsifiable completion predicate is: both methods consume the same verified manifest hash; each successful attempt resolves to its immutable method-run artifact; the exact checker verifies both hulls and rejects the omitted-corner control while accepting redundant vertices; every warmup, measurement and non-success status remains in the record; the saved renderer reproduces the bundle; no cross-runtime performance claim appears; and the reviewed report route is publicly reachable after deployment.

## Open limitations

- The local archive source verifier cannot resolve its recorded Windows path on this Linux host. The port's previously verified A29/A30 source hashes, commit history and deviations remain the source evidence for this run.
- The original Pascal `btulshor.pas` is a separate A06 routine, not an A29/A30 or ITIS17 implementation. It is not substituted into this pilot.
- The exact checker proves hull equality for these represented binary64 points only. It does not prove MATLAB runtime parity or reproduce B03.
- A separate source-level performance limiter profile is not useful for cross-runtime speed comparison; no performance conclusion will be drawn.
