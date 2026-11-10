# REVIEW-05 exact family query ladder implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Preserve independent specification and standards reviews before integration.

**Goal:** Measure matched complete nominal families and actual direction-based witness queries at scalar horizons 2, 4 and 8 for issue #95.

**Architecture:** Reuse bounded exact-H mathematics with distinct producer/verifier bindings for Strategy A and Strategy B. Generalize scalar witness layout from five coordinates to `2*T+1`. A proposal gains completeness only after an independently invoked verifier reconstructs the original problem and establishes both inclusion directions.

**Tech Stack:** C++20, pinned HiGHS, existing exact dyadic H arithmetic, Python result capture/checking.

**Spec:** Live issue #95 acceptance criteria and the admission/design audit recorded in its discussion; this document records the selected implementation design under the owner's autonomous execution authorization.

## Scope and invariants

The measured query is direction optimization followed by witness selection. Generic membership/slice APIs do not exist; report them as unsupported. Keep exact-H limits (32 variables, 4096 rows/stages, 100000 generated rows, five million operations, 8192 integer bits), explicit stops/refusals, and materialization limits. Do not promote HiGHS status or producer rows into completeness evidence. Preserve canonical T2 profiles. No new dependency is required. Selector direction semantics expand to T controls and require public delivery documentation.

## 1. Strategy B complete nominal exact-H profile

Files: `src/registry/nominal_linear_exact_verifier.cpp`, its private declarations, compiled-verifier registration, `include/csl/synthesis/strategy_b/direct_joint.hpp`, and `src/synthesis/strategy_b/direct_joint.cpp`.

- [ ] Locate all A-owned admission, proposal, verifier and lineage bindings and the existing B canonical-profile seams before extracting shared mathematical helpers.
- [ ] Add failing tests for B nominal exact admission at T2/4/8 and rejection of proposals carrying A producer/verifier/lineage metadata.
- [ ] Add B-owned profile and verifier identities; share problem reconstruction/exact face comparison while retaining distinct bindings.
- [ ] Build the ordinary joint LP, retain numerical/partial evidence, construct an exact-face proposal only for admitted completed runs, and independently verify it.
- [ ] Test omitted optimal histories, included nonoptimal histories, budget exhaustion and cancellation; run existing A/B exact-profile regressions. Commit the verified unit.

## 2. Horizon-aware scalar witness selection

Files: `src/synthesis/witness_selector.cpp`, public selector header/docs and existing selector tests.

- [ ] Add failing tests for T4/T8 scalar H families, malformed direction widths and returned primal sizes.
- [ ] Replace five-column/two-control assumptions with checked `2*T+1` width, state indices `[0,T]`, control indices `[T+1,2*T]`, and T finite direction values.
- [ ] Preserve registry-verified family requirements, exact optimum binding, distinctness rules and cancellation/shortfall records. Use the registry-verified coincident optimum as the witness objective value: verified membership in the exact optimizer face establishes equality to that original optimum. Independently evaluate the original fixture objective during replay, including nonzero constants. The current family API does not expose original coefficients; do not invent a payload API solely for this selector.
- [ ] Replay zero-optimum histories and distinct witnesses from a constant-objective non-singleton family. Preserve all canonical T2 behavior. Commit the verified unit.

## 3. Matched capture and independent evidence

Files: a separate driver and collector/checker under `benchmarks/reporting/review05`, plus its CMake target and documentation.

- [ ] Use original HORIZON01 zero-optimum fixtures at T2/4/8, requesting one witness; label constant-objective variants with distinct fixture identities.
- [ ] Retain synthesis/verifier/query/selector/replay timing, exact H shape and serialized size, all refusals/stops/shortfalls, full provenance and resources.
- [ ] Independently verify literal dynamics, bounds, objective and optimizer-family relation. Never infer uniqueness from repeated selector results.
- [ ] Capture repeated Release runs under limits; quantify enabled/disabled instrumentation overhead separately. Preserve raw artifacts and checksums.
- [ ] Provide a supported 2D illustration from the recorded control projection, labelling scalar state dimension and coordinates.
- [ ] Run installed-consumer/platform checks for the behavior expansion; record release impact and obtain independent reviews at the final base/head before merging. Keep #95 open for its other audited requirements.

## Execution ruling

The objective-value rule above follows the existing family API: only verified coincident bounds and verified optimizer-face membership are available to the selector. Original-data objective evaluation belongs to independent replay. Both implementation workers own separate worktrees; root retains this plan. Local builds share the host, so captures made during those builds are diagnostic pilots and cannot support uncontended performance claims.
