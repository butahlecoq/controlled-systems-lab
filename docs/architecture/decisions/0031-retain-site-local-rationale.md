# ADR 0031: Retain site-local rationale that is not a cross-cutting decision

Date: 2026-11-26
Status: Accepted

## Context

The comment-debt audit recorded 3,353 candidate comments in the external
reconciliation ledger. The ledger classifies each candidate by the kind of
statement it makes and gives a disposition such as deleting a repeated
statement or reconciling a design decision with an ADR. The classification is a
starting point, not proof that every comment labelled "Decision Record" belongs
in an ADR: many are test-local derivations, literal fixture explanations,
measurement designs, public-contract guarantees, or provenance notes for saved
evidence.

Moving those statements into ADRs would separate them from the code or fixture
they explain and would bloat the ADR set with task-specific arithmetic.
Deleting them would remove the only readable statement of why a literal test
value or a saved-evidence decision is what it is. The applicable repository
rule already distinguishes these cases: keep a derivation with its test or
model, keep every operative guarantee at the declaration that owns it, and move
genuinely cross-cutting design choices to a numbered ADR.

## Decision

Disposition is explicit per ledger record, not by label alone:

- A comment whose bytes are pinned by a publication manifest, saved evidence
  record, or frozen publisher stays unchanged. The pin is the reason; see the
  batch reports for the exact manifest.
- A test-local derivation, fixture explanation, or literal scenario description
  stays with the test that depends on it. Tests are the owning site for the
  values they assert.
- An operative guarantee, tolerance rule, cache-key invariant, ordering
  constraint, or public-contract statement stays at the declaration or function
  that enforces it.
- A measurement-design or benchmark-binding rationale stays with the benchmark
  that consumes it, unless the same rule governs multiple independent
  consumers; then it moves to an ADR and the inline copy is removed.
- A publication, replay, or evidence-provenance note stays beside the helper
  and saved route it documents, because its exact wording and inputs are part
  of the reproducibility evidence.
- Cross-cutting implementation rationale that is not already recorded moves to
  the most relevant existing ADR before its inline copy is removed. A new ADR
  is created only when no existing decision record covers the group.
- A comment may be reclassified as retained only with a stated reason in the
  external disposition ledger. Reclassification is not a synonym for
  "unreviewed"; each record carries its status and reason.

## Consequences

The remaining inline comments are an intentional part of the reviewed sources:
they state operands, tolerances, fixture literals, ownership, and evidence
provenance at the point where a reader needs them. The numbered ADRs continue
to own cross-cutting choices, and the external ledger records the disposition
of every audited candidate, including the retained ones. Future audits should
apply the same ownership test rather than treating category labels as an
instruction to delete.
