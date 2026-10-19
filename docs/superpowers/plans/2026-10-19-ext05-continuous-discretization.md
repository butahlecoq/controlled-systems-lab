# EXT-05 Continuous-Model Discretization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an explicit continuous affine model intake and numerical discretization adapter with independently checked LTI/LTV behavior and saved 2D evidence.

**Architecture:** `CSL::model` owns a typed continuous model, RK4 step-doubling discretizer and immutable result receipt. `CSL::input` owns a distinct strict JSON model document and source binding. The existing discrete scenario loader and model snapshot retain their current fail-closed behavior.

**Tech Stack:** C++20, existing CSL matrix/value contracts, CMake/doctest, nlohmann JSON already pinned for `CSL::input`, Python saved-report tooling and GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-19-ext05-continuous-discretization-design.md`

## Global Constraints

- Source is finite affine continuous time on an explicit strictly increasing physical grid; both input channels use zero-order hold.
- Constant LTI and piecewise-linear-in-time LTV endpoint records are distinct declared providers; no inferred interpolation or descriptor/nonlinear equation.
- Every published output has `TimeDomain::discrete` and per-stage numerical provenance; local error estimates are diagnostics, not validated global bounds.
- Existing `csl.scenario/1` and `model::snapshot` continuous rejection remain authoritative.
- No new dependency, solver integration, binary release or historical-source claim.

## Review Focus

- A long interval or large coefficient must not produce a nonfinite map or success after step-budget exhaustion.
- An interval whose next binary64 time cannot advance must stop without an incomplete transition.
- A constant zero-width port must retain n×0 matrix shape and preserve affine offset.
- Indexed LTV endpoints must follow authored interval order, including discontinuous boundary values.
- The JSON reader must distinguish continuous coefficient input from discrete transitions and reject extra keys and unsupported descriptor/nonlinear forms at an explicit path.

---

### Task 1: Public continuous model and numerical adapter

**Files:** Create `include/csl/model/discretization.hpp`, `src/model/discretization/adapter.cpp`, `src/model/discretization/rk4.cpp`, `src/model/discretization/internal.hpp`, `tests/contract/model/continuous_discretization_tests.cpp`; modify `src/model/Module.cmake`, `src/model/Tests.cmake`.

- [ ] Add public-route tests for a 2D double integrator with two physical durations, scalar affine forcing, zero-width ports and singular A; assert literal matrices and receipt fields.
- [ ] Add analytic varying-coefficient LTV cases for `A(t)=t` and `B(t)=t` and assert stage order and a complete two-stage state trajectory.
- [ ] Add malformed shape/grid/options, unsupported source kind, cancellation, overflow and finite step-budget refusal tests; run the target and observe its initial failure.
- [ ] Implement validation, frozen input copies, augmented-map RK4 step doubling, adaptive acceptance/refusal and stage receipts. Run focused model tests and commit.

### Task 2: Distinct strict continuous-model document

**Files:** Create `include/csl/input/continuous_model.hpp`, `src/input/continuous_model.cpp`, `schemas/model/continuous-v1.schema.json`, `schemas/model/README.md`, `tests/contract/input/continuous_model_tests.cpp`, `tests/fixtures/input/continuous-double-integrator.json`; modify `src/input/Module.cmake`, `src/input/Tests.cmake`.

- [ ] Add tests for the complete document, source byte digest, model kind and integration metadata; verify the loaded model gives the literal double-integrator transition through the public adapter.
- [ ] Add tests for discrete kind rejection, descriptor/nonlinear unsupported forms, unknown/duplicate keys, incorrect matrix extent, nonfinite/underflow numbers, grid and quota errors; run them to observe absence of the loader.
- [ ] Reuse the existing bounded strict JSON tokenizer and input failures, translate the closed grammar into owned continuous types, and install the schema/fixture. Run focused input tests and commit.

### Task 3: Contract, installed client and package evidence

**Files:** Create `docs/contracts/time-domains.md`, `tests/installed/continuous_discretization_client.cpp`; modify `docs/contracts/linear-model.md`, `docs/contracts/scenario-input.md`, `docs/contracts/core-interfaces.md`, `cmake/RunInstalledClient.cmake`, model/input installation metadata.

- [ ] Document source and output time domains, interpolation, zero-order hold, local-estimate limits, the separate JSON schema and explicit caller route; record rejected descriptor/nonlinear capabilities.
- [ ] Add a `find_package(CSL CONFIG)` installed client that loads or constructs the documented input and calls the adapter, asserting a literal output and receipt.
- [ ] Run core build, focused baseline model/input tests and installed client, then commit.

### Task 4: Frozen numerical report and 2D example

**Files:** Add a public adapter report driver, capture/collector/saved renderer, reporting tests and an immutable bundle under `reports/algorithm-results/`; add an allowlisted stager to `.github/workflows/algorithm-reports.yml` and report catalog.

- [ ] Capture a 2D double-integrator case from one clean frozen source commit, including raw observations, independent analytic oracle, source/build receipts and explicit local-error limitation.
- [ ] Render a labelled 2D example, HTML report and offline ZIP from saved bytes; verify byte regeneration, manifest, catalog, link safety, responsive layout and reporting tests.
- [ ] Run required native/reporting verification and commit the bundle without modifying its frozen source.

### Task 5: Independent review, integration and cleanup

- [ ] Open a PR with public API/schema/package impact, no-release decision, source/measurement scope and unresolved limitations.
- [ ] Obtain independent specification and standards SubAgent reviews plus scientific saved-result review at exact base/head; post findings and scoped fix responses on the PR.
- [ ] Pass exact-head CI, merge with source ancestry intact, verify main-only Pages HTML/SVG/raw/ZIP bytes live, and close #54 with evidence.
- [ ] Check disk, registered worktrees, tracked/untracked/ignored status and remote/local branches; remove only validated merged disposable worktrees and branches, preserving authored artifacts.
