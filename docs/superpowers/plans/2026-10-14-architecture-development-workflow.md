# Architecture development workflow implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent slices and native implementation for shared build/contracts. Track evidence per ticket; review the integrated branch before merge.

**Goal:** Implement the full approved scope of #251 through #252–#257 and merge reviewed changes.
**Architecture:** Domain-owned build declarations and narrow contracts keep changes local. Existing provider and reporting modules absorb repeated lifecycle machinery. Existing public ports and compatibility umbrella remain stable.
**Tech stack:** C++20, CMake/CTest >=3.31, Python >=3.11, pinned Eigen/HiGHS/Qhull/JSON/doctest.
**Spec:** GitHub issue #251, baseline bf567d3a57e04bf6dc4c74e762ec999a37390718. Child issues retain full corresponding acceptance.

## Constraints

- Preserve full optimal-family/evidence semantics and compiled verifier authority; test-only catalogs never install.
- Preserve existing exported CSL:: targets, native vendor pins/notices, public source compatibility and independent numerical oracles.
- Keep published report bundles/evidence byte-identical and maintain versioned URLs.
- Do not duplicate PR #250 or the CLI/general-profile feature backlog.
- Use separate mutable workspaces for independent changes. Do not delete unreviewed worktrees, source archives or evidence.

## Review focus

- Disabled adapters must remove vendor acquisition and dependent tests without silently suppressing the full configuration.
- A copied installed consumer must resolve all static transitive dependencies from the install alone.
- Contract extraction must not expose verifier factories or let callers forge family evidence.
- Collection timeout/malformed output must preserve raw stdout/stderr and failure context.
- Qhull must still honor stops after a solver returns; LP/QP policy differences must survive shared native code.

## Tasks

- [ ] #252: Correct current-state docs and add task/module navigation and safe workspace inventory. Verify commands against presets; link canonical glossary.
- [ ] #253: Move target/install/test declarations into domain-owned Module.cmake files; root retains composition. Add shared library/test policy, Windows/Linux presets, module labels and optional HiGHS/Qhull with explicit configuration checks. Verify core, full and selected-adapter configurations and copied installed consumers; preserve native/sanitizer gates.
- [ ] #254 (after #253): Extract primitive/value/error contracts, then model/evidence/geometry/optimization/execution/synthesis domain contract headers. Keep umbrella compatibility and migrate internal headers. Move corresponding primitive validation implementation where needed. Add standalone installed compile checks and structural include-dependency guard; run family/authority suites.
- [ ] #255: Migrate GEO-05 and a second kind to shared report lifecycle and publication safety. Move maintained Python/native driver code with compatible entry points; run existing reporting and new failure-path tests, validate old bundle hashes and offline staging.
- [ ] #256: Reuse RegisteredLPQueryRunner in Qhull and retain numerical translation/evidence/stops. Exercise providers, rejection/ownership/stops and independent conversion fixtures.
- [ ] #257: Extract common private HiGHS callbacks/session options, keeping mathematical policies distinct. Exercise LP/convex cancellation, repeated solves and workspace isolation.

## Verification and integration

- Capture baseline and after development observations (configure, incremental rebuild, focused/full tests and representative change touch points). Describe measurements as environment-specific observations, without an algorithm speedup claim.
- Build and run focused checks for each implementation; build full native Release and copied installed clients; use hosted Linux/MSVC/sanitizer gates before merging.
- Run independent Matt Pocock Standards and Spec reviews with pinned base/head. Publish findings, fixes and scoped re-review on PRs.
- Use one PR per child deliverable (stack shared prerequisites where necessary); close only acceptance-complete tickets. After all merges, audit #251 requirement by requirement against current main before closing.
