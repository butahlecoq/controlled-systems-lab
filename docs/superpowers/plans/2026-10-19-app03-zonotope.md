# APP-03 Zonotope Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship exact zero-generator removal and independently admitted budgeted outer zonotope enclosures with public evidence.

**Architecture:** A dedicated adapter builds native generator sets. Conversion handles physical equality; approximation handles outer inclusion. The existing approximation policy checks the latter independently using exact stored-binary64 arithmetic.

**Tech Stack:** C++20, CMake, doctest, Python report tooling, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-19-app03-zonotope-design.md`

## Global Constraints

- Preserve `FactorId` for every retained column and state the relaxation for omitted factors and equalities.
- Reject unsupported guarantee requests and capacity limits; do not invent tolerances or rounding guarantees.
- Keep saved numerical records separate from code and publish a minimal 2D visual example.
- Record public API, package and release impact in the PR.

## Review Focus

- Provider-asserted enclosure without a valid structural certificate must be rejected.
- A source factor shared with another set must not be silently relabelled when retained.
- Constraints must never survive only in evidence text while absent from the output.
- A generator budget must count native factor columns, including replacement axes.
- Binary64 sums that overflow a finite outer radius must fail closed.

## Task 1: Independent generator inclusion admission

**Files:** `include/csl/geometry/approximation.hpp`, `src/geometry/approximation/policy.cpp`, `tests/contract/geometry/approximation_policy_tests.cpp`.

- [ ] Add failing public-policy tests for valid and forged native generator outer enclosures, including source constraints, dependency IDs and insufficient budget.
- [ ] Run the named test and confirm the new cases fail for the missing certificate.
- [ ] Add `generator_axis_cover` to `StructuralBasis`; compare immutable source/output handles and exact dyadic per-row residual radii.
- [ ] Count native factor columns in `within_budget` and set the evidence support to describe the actual admitted basis.
- [ ] Run the named test and commit the independently verified policy change.

## Task 2: Registered conversion and outer adapter

**Files:** `include/csl/geometry/zonotope_reduction.hpp`, `src/geometry/approximation/zonotope.cpp`, `src/geometry/Module.cmake`, `tests/contract/geometry/zonotope_reduction_tests.cpp`, `src/geometry/Tests.cmake`, `docs/contracts/approximation.md`, `docs/contracts/generator-sets.md`.

- [ ] Add failing public-port tests for zero-column conversion, a 2D budgeted enclosure, constrained-source relaxation, rejection paths, stop handling and output identities.
- [ ] Run the named test and confirm adapter cases fail.
- [ ] Implement exact zero-column conversion and deterministic budgeted outer construction with independently rounded axis radii.
- [ ] Register methods in the target, document capabilities and limits, and run contract tests.
- [ ] Add an installed client and run install-tree consumer verification; commit the adapter.

## Task 3: Saved numerical evidence and visual example

**Files:** a new immutable bundle under `reports/algorithm-results/`, `scripts/reports/` collector/stager, catalogue entry, reporting tests, and the existing Pages workflow if routing needs extension.

- [ ] Freeze the reviewed adapter source commit and build a separate clean Release capture from it.
- [ ] Record literal low-dimensional expected supports, actual outputs, failures, provenance, and raw per-repetition timings; exclude warmups and make no comparative claim.
- [ ] Render an English HTML report, offline ZIP, manifest and labelled 2D example; verify all links and hashes locally.
- [ ] Obtain independent scientific/saved-data review, fix findings and commit the reviewed bundle.

## Task 4: Delivery and integration

- [ ] Run the complete relevant CTest, reporting tests, docs checks and installed public client.
- [ ] Open a PR with release/package impact and exact commit; request independent spec and standards reviews and post both as PR comments.
- [ ] Resolve findings, rerun exact-head CI, merge, verify main-only Pages deployment and live bytes, comment on and close issue #42.
- [ ] Clean merged branches and safe worktrees after checking status, target path and free space.
