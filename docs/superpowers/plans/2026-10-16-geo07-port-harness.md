# GEO-07 Registered Port Report Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reviewable, fixed-source public-API measurement harness for draft PR #344 without collecting timing.

**Architecture:** A non-installed C++ driver calls prepared `GeometryPort` and `ConversionPort` registrations on fresh literal fixtures. A Python collector admits only the reviewed source/harness, controlled MSVC Release graph, complete raw JSONL, and exact authored fixture catalogue; it retains failures and emits versioned records for later report rendering.

**Tech Stack:** C++20, CMake, doctest/CTest, Python 3.11 unittest, nlohmann JSON.

**Spec:** `docs/architecture/published-algorithm-results.md`; exact adapter source `41b4b58f2ef982e75554519862afdd803e30f717`.

## Global Constraints

- Keep #344 source unchanged and this PR draft; no timed collection before independent review and exact-head CI.
- Use numerical binary64 assurance; symbolic real-set equivalence is not a validated rounding enclosure.
- One excluded warmup and at least seven alternating measured batches, with every call checked and each accepted batch at least 20 ms.
- Preserve exact raw stdout/stderr even on failure; no comparator, limiter or speedup claim.

## Review Focus

- An affine or sum result with wrong center, generator columns, IDs or equalities must fail literal output/H checks.
- V conversion with wrong vertices, rays or lost/incorrect labels must fail against authored V data.
- Shared-ID Minkowski, constrained conversion, intersection, cap overflow and validated assurance must remain rejected with scoped diagnostics.
- A false `checked_calls`, changed fixture catalogue, wrong order, short interval or malformed JSON must reject admission.
- A non-Release or changed compiler/link graph, dirty source or wrong exact head must reject collection before timing.

---

### Task 1: Public driver and smoke path

**Files:** `benchmarks/reporting/geo07_port/adapter_driver.cpp`, `scripts/reports/geo07_port/check_smoke.py`, `CMakeLists.txt`, `cmake/OptionalReports.cmake`.

- [ ] Write smoke assertions for literal fixture inputs, expected output rows and rejection controls.
- [ ] Run smoke against absent target or incomplete driver and observe failure.
- [ ] Add three fixtures: affine image, disjoint constrained sum and bounded V conversion. Each fresh call uses prepared registrations, verifies literal H/V results and rejections, then returns its checked result.
- [ ] Build MSVC Release report target and run only the bounded smoke test.

### Task 2: Collector admission and provenance

**Files:** `scripts/reports/geo07_port/collect.py`, `tests/reporting/test_geo07_port_harness.py`.

- [ ] Write synthetic admission tests for exact authored catalogue/hashes and timed-scope string, warmup/order/count/literal rows, malformed/short/failure rows, raw retention, and Release graph.
- [ ] Run Python tests and observe the expected missing collector behavior.
- [ ] Implement fixed-source collector with clean-checkout/reviewed-delta gate, fresh Release rebuild/provenance, exact-byte raw capture, deterministic JSON/manifest and nonpublishable status.
- [ ] Run Python tests and bounded smoke; do not invoke `--measure` or the collector.

### Task 3: Review handoff

**Files:** `reports/algorithm-results/tooling/geo07_port/README.md`.

- [ ] Document fixture math, interval inclusions/exclusions, build/collection commands, gate and exploratory limits.
- [ ] Run focused CTest and Python tests, `git diff --check`, commit and open draft PR stacked on exact #344 head.
