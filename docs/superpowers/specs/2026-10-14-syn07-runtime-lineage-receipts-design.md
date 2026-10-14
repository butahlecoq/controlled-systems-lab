# SYN-07 Runtime Lineage Receipts Design

## Goal

Close the execution-provenance gap for the registered Strategy B T-S01 complete-family profile. A strategy that copies the expected transformation IDs into a proposal must not pass the complete-family gate unless the trusted library execution actually performed the required transformations for the same prepared request and retained artifacts in the current solve.

## Chosen module and seam

Keep the public workflow (`StrategyRegistry::prepare`, `PreparedStrategy::create`, `run`) unchanged. Add a private compiled Strategy B T-S01 execution module behind that seam. It owns per-solve receipt state and observes the actual construction and extraction artifacts. `FamilyIdentity::lineage` remains a readable projection, not proof. Do not add a public recorder, caller-supplied digest, or arbitrary callback-based receipt API.

The receipt binds immutable prepared problem content, effective family request, coordinate schema, selected strategy and verifier versions, and the artifacts observed during its solve. Freshness follows the runner lifecycle: it clears stored receipt state at each `solve()` entry, creates a receipt only after successful extraction, and the verifier wrapper takes that receipt once for admission. The only accepted sequence is successful joint-feasible construction followed by optimal-level extraction from that exact retained artifact. The strategy cannot mint or edit receipts. Other strategies and profiles remain fail-closed under this mechanism.

## Proof separation and limits

Runtime receipts establish which trusted in-process transformations ran and which artifacts they consumed and produced. They do not establish floating-point equivalence, optimality, or family completeness. The exact T-S01 analytic verifier remains an independent proof input for the canonical complete relation; the extracted `syn04-optimal-level` relation must remain distinct from the canonical `ts01-optimal-histories` relation. The trust model covers supported C++ library calls, not modified binaries, arbitrary memory corruption, or undefined behavior.

## Verification

Exercise the ordinary registry caller path. A valid exact T-S01 execution must still publish its complete relation. Matching self-reported IDs without runtime execution, foreign/replayed receipts, missing extraction, reordered/duplicated steps, and substituted artifacts must be rejected. Existing candidate-only behavior and other verifier profiles must retain their current guarantees. No benchmark or performance claim is part of this change.
