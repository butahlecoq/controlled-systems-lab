# SYN-07 request and stop boundary implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks inline in the already isolated worktree. The user has authorized autonomous implementation and a PR; do not merge or close issue #155.

**Goal:** Close malformed request-policy and provider-provenance gaps in the existing fail-closed synthesis boundary.

**Architecture:** Keep the immutable `OptimalFamily` publisher and `SynthesisResult` envelope introduced by merged PR #159. Share request validation across direct family publication, direct strategy execution, and registry preparation. Validate scoped provider provenance while preserving malformed original stops under contract rejection.

**Tech Stack:** C++20, doctest, CMake, MSVC Release, CTest.

**Spec:** [Cross-cutting API defaults](../specs/2026-10-12-cross-cutting-api-decisions-proposal.md), live issue #155.

## Global constraints

- Complete and partial family publication stay disabled until reviewed coverage and every-history optimality evidence paths exist.
- No numerical thresholds or validated-arithmetic backend are introduced.
- Preserve separate mathematical outcomes, exact typed stop reasons, retained evidence, and immutable previously published values.
- PR #177 already adds independent caller family expectations; do not duplicate that work.

## Review focus

- Direct publisher requests with negative/nonfinite policy fields must reject.
- Direct strategy requests must reject invalid policy or objective/profile before running the workspace.
- Mismatched execution policy must reject before running the workspace.
- Missing/half-populated provider provenance must yield contract rejection while retaining the original stop and supported evidence.
- Unknown-provider rejection with no actual provider identity remains admissible.

### Task 1: Shared effective-request admission

**Files:** `include/csl/contracts.hpp`, `src/contracts.cpp`, `src/registry/registry.cpp`, `tests/contract/registry/registry_tests.cpp`, `docs/contracts/core-interfaces.md`.

**Interface:** `Diagnostics check_family_request(const FamilyRequest&, const ProblemId&)` checks effective objective/profile and finite nonnegative policy. Use it before `StrategyPort` workspace execution, in `StrategyRegistry::prepare`, and in `check_family_evidence`.

- [x] Add publisher/direct strategy regressions for negative, infinite, and NaN tolerances, wrong objective, empty profile, and context mismatch; include an accepted zero policy.
- [x] Build/run `registry_tests`; observe rejection assertions failing against main.
- [x] Implement the shared admission check without changing policy values or family outcomes.
- [x] Run focused tests and retain their output.

### Task 2: Scoped stop provider provenance

**Files:** `src/contracts.cpp`, `tests/contract/registry/registry_tests.cpp`.

**Interface:** Internal provenance validation requires request/port/requested module, nonempty supplied versions, and a paired actual module/version; absence of both actual fields is permitted.

- [x] Add direct strategy regressions for malformed rejection and stopped provenance; assert retained candidate, bounds, incumbent, timings, and exact original stop. Include an unknown-provider admission case.
- [x] Run new tests and observe failures against the existing guard.
- [x] Validate provenance for `ScopedRequestRejection` and `ScopedOperationStopped` without rewriting original provider facts.
- [x] Run focused tests, full Release build/CTest, and `git diff --check`.
- [ ] Commit/push and open a partial PR with exact coverage/ledger/verifier blockers; leave #155 open.

## Execution evidence and remaining gates

- The two request admission regressions failed against the original code because malformed requests were accepted. After task 1 they passed; the provenance regression then failed because a rejection with no requested provider module remained accepted.
- After task 2, `registry_tests` passed 29 cases and 885 assertions. The full isolated MSVC 19.44 Release build succeeded and CTest passed 68/68, including the installed public client. No broad benchmark was run.
- Documentation verification passed for 174 Markdown documents and 459 local links with zero errors. Its generated verification inventory was restored rather than included as unrelated output.
- Ruling: reuse pinned dependency **sources** from the existing SYN-03 build while keeping all generated/native build outputs in this worktree's `tmp/native`; do not share mutable build state.
- Complete publication remains blocked on a reviewed and validated coverage-evidence procedure, arithmetic/tolerance policy, acceptance criteria and independent verifier. Partial publication remains blocked on reviewed every-history optimality support. A separately recorded independent runtime transformation ledger is still needed to prove the claimed lineage was executed. No new type or structural guard resolves those scientific gates.
