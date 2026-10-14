# SYN-07 Runtime Lineage Receipts Implementation Plan

> For agentic workers: use `superpowers:subagent-driven-development` for implementation. Follow TDD and preserve the scope in the linked design.

**Goal:** Require verifier-owned evidence of the real Strategy B T-S01 build/extraction sequence before publishing its exact complete-family proposal.

**Architecture:** A private compiled execution adapter receives the registry-frozen request and provider dependencies, executes the actual Strategy B pipeline, retains immutable artifact snapshots, and seals a fresh per-run receipt. The compiled complete-family verifier checks receipt binding and sequence separately from the existing analytic completeness theorem. Public prepare/create/run interfaces remain unchanged.

**Tech Stack:** C++20; current registry and synthesis modules; doctest/CTest; existing CMake Release build.

**Spec:** `docs/superpowers/specs/2026-10-14-syn07-runtime-lineage-receipts-design.md`; originating ticket: GitHub issue #155.

## Global Constraints

- Never let a strategy or caller append arbitrary receipt records or submit a receipt/digest as proof.
- Receipts bind actual immutable inputs/outputs and are fresh per solve; a repeated run cannot reuse evidence.
- Keep the proof of analytic T-S01 family completeness independent from execution provenance.
- Preserve distinction between extracted feasible/optimal-level artifacts and the canonical exact relation.
- Other profiles remain fail-closed; do not broaden admission or numerical guarantees.
- Use behavior tests through the same prepare/create/run path callers use; run all project CTests.
- No algorithmic result/performance claim is produced, so this change does not create a numerical benchmark report.

## Review Focus

- Standards: private authority and ownership, type safety, no arbitrary callback or self-reported receipt path, readable lineage remains descriptive.
- Spec: actual successful build then extraction on bound artifacts; strict solve/request/version binding; failure/replay/forgery rejection; theorem and provenance remain separate.

## Task Ledger

- [ ] Task 1 — Add the private runtime receipt and verifier acceptance contract with failing behavior tests.
- [ ] Task 2 — Integrate the receipt-producing Strategy B execution path and adversarial caller-path tests.
- [ ] Task 3 — Run full verification, obtain independent Standards and Spec review, fix findings, and prepare the PR.

## Rulings

- Ruling: scope receipts to the exact registered Strategy B T-S01 profile — broader profiles need their own reviewed mathematical and execution contracts; the cost if wrong is a follow-up integration rather than accidental authority expansion.
- Ruling: keep public API unchanged and receipts in-process — serialization/remote attestation is not required by issue #155; the cost if wrong is future adapter work when remote execution is introduced.
