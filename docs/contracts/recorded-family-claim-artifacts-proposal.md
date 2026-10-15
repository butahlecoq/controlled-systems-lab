# Proposal: recorded complete-family claims in run artifacts

**Status:** Proposal for architecture and scientific review. This document defines no enabled behavior and does not relax the current fail-closed encoder or decoder. It is tied to [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [INP-02 #75](https://github.com/butahlecoq/controlled-systems-lab/issues/75), [SYN-07 #155](https://github.com/butahlecoq/controlled-systems-lab/issues/155), and the architecture concern in [#140](https://github.com/butahlecoq/controlled-systems-lab/issues/140).

## Problem and decision requested

The live strategy boundary can publish a complete family after a selected compiled verifier has checked its proposal against a prepared problem, effective request, strategy identity/version, coordinates, and ordered lineage. A saved artifact is different: its JSON and proof fields are caller-controlled input. Parsing them cannot recreate the runtime verifier's authority.

At main `3f7d657223b2ecc3954730c5baa8c982f6268c36`, `encode_run` rejects a live family carrying `RegisteredCompletenessEvidence` at `run.final.family.completeness.support`. The run-statistics decoder reconstructs families through the untrusted `FamilyPublisher`; the contract test verifies that a serialized registered-proof claim cannot publish a complete family. The T-S01 Strategy A/B verifier paths also require fresh runtime receipts tied to the prepared execution and its in-memory transformation outputs. There is no public artifact replay API.

Reviewers should decide whether the system wants a claim-preserving artifact with explicit re-execution replay, a separately reviewed profile-specific replay verifier, or no portable complete-family claim yet. Until that decision is made, existing encoder/decoder behavior remains authoritative.

## Proposed trust model

Keep three states distinct:

| State | Meaning | May be passed to `SelectorPort` or treated as a live `OptimalFamily`? |
| --- | --- | --- |
| Runtime-verified result | Produced in the current process by a prepared strategy whose selected compiled verifier accepted the family proposal and any required runtime receipt. | Yes, subject to the existing public family checks. |
| Recorded family claim | A versioned artifact preserves what the producing run claimed, including proof and relation data. The artifact may be structurally valid and bound to the resolved problem while the claim remains untrusted. | No. It is not `OptimalFamily`, does not set `registry_verified`, and cannot satisfy selector admission. |
| Replayed result | A new execution/replay operation has checked the recorded claim against an authoritative problem/request and a currently available approved replay authority. | Only the fresh result returned by that operation may be treated as verified in that process. Re-decoding its saved artifact returns to Recorded family claim. |

Content hashes, source hashes, a recorded `registry_verified` string, verifier IDs, and opaque proof text establish provenance or integrity only. None is authority by itself. A successful structural import or `decode_run(text, resolved_problem)` revalidates identities/content according to its existing contract; it does not prove completeness.

## Proposed versioned artifact shape

Do not deserialize a claim into the runtime `SynthesisFinal.family` / `OptimalFamily` slot. Add a versioned recorded-result DTO (proposed wire schema `csl.run-statistics/5`) whose synthesis final can retain an optional `RecordedFamilyClaim` alongside its outcome/evidence. The claim DTO is data-only and has no constructor or conversion that publishes a live family. Its fields should preserve:

- the claimed `FamilyIdentity`: problem, effective `FamilyRequest`, ordered joint-coordinate schema, strategy ID/version, and ordered `TransformStepIdentity` lineage;
- the claimed family target, representation, assurance, relation-attachment reference and attachment digest;
- the claimed optimum and bounds, support discriminators, completeness verifier ID/version, and opaque verifier payload;
- producer/run provenance and an explicit state such as `unverified_recorded_claim`.

The serialized relation attachment must identify its schema, byte count, and digest. The digest detects altered bytes; it does not validate the mathematics. Unsupported or unavailable relation encodings must preserve the run's typed unsupported diagnostic and must not silently omit the family while leaving a complete-family status.

A single artifact-import entry point may dispatch v1-v4 to their existing behavior and v5 to the recorded DTO. If the existing `decode_run` return type cannot represent this distinction without placing a claim in a runtime family slot, introduce a separate imported-artifact result type instead of weakening that slot. The exact C++ type names are an implementation decision after this proposal is reviewed.

## T-S01 and T-S02 bindings to preserve

The following are current registered profile identities, not a proposal for new proof algorithms or thresholds. Import must preserve them exactly; replay must use an explicitly selected implementation and compare every identity field, including lineage order.

| Profile | Verifier and opaque payload | Strategy identities and lineage constraints |
| --- | --- | --- |
| T-S01 `ts01_exact_integrator` | `csl.verifier.ts01-analytic@1`, payload `TS01-analytic-v1`. Canonical joint history coordinates are `(x0,x1,x2,u0,u1)` with `x0=0`, `x1=u0`, `x2=1`, `u0+u1=1`, and `u0` in `[0,1]`. | The standalone analytic strategy is `csl.synthesis.ts01-analytic@1` with empty lineage. Strategy B is `csl.synthesis.strategy-b@1` with ordered `syn04-build:<ProblemId>` then `syn04-extract:<ProblemId>` lineage. Strategy A is `csl.synthesis.reach-back@1` with the exact six-step `expected_ts01_lineage`: three nominal-forward stage steps, feasible preimage, terminal minimizer, terminal preimage. |
| T-S02 `ts02_constant_integrator` | `csl.verifier.ts02-constant-integrator@1`, payload `TS02-constant-integrator-v1`. The verifier admits the canonical five-coordinate joint-history set and the constant objective value 3 under its currently implemented profile checks. | Strategy B is `csl.synthesis.strategy-b@1` with exactly one `syn04-build:<ProblemId>` lineage step. Strategy A is `csl.synthesis.reach-back@1` with the exact six-step `expected_ts02_lineage` (currently the same deterministic six-step sequence as T-S01 Strategy A). There is no standalone T-S02 analytic strategy in the current compiled catalog. |

The authoritative code sources are `src/registry/compiled_verifiers.cpp`, `src/registry/strategy_a_lineage.hpp`, and `src/registry/strategy_b_lineage.hpp`. The run claim must store the complete ordered lineage values emitted by the registered strategy; the table is not permission to synthesize a receipt from names or reconstruct lineage from an untrusted artifact.

T-S01 Strategy A/B runtime verification additionally requires fresh execution receipts for their forward/terminal/recovery or build/extraction sequence. These receipts contain live output ownership and are not portable proof payloads. T-S02 uses profile-specific checks, but this proposal does not assume that the current `verify` routine is a standalone replay API. Replay authority remains a decision below.

## Import, replay, and unsupported behavior

Import performs bounded schema parsing, validates attachment metadata and digest, and (when supplied) checks the artifact's problem binding against the caller's immutable `ResolvedProblem`. Import returns the claim as untrusted recorded data in every case. It does not invoke a solver, selector, or registered verifier and never yields a registry-verified complete family.

The replay API must be explicit and fail closed. Candidate designs for review are:

1. **Strategy re-execution and comparison.** Run the requested registered strategy/providers against the resolved problem, let the existing prepared boundary establish a fresh result, then compare the resulting identity/evidence/relation against the recorded claim. This can be expensive and requires a precise comparison contract for relation attachments.
2. **Profile-specific compiled replay verifier.** Add a compiled verifier interface designed to check a portable claim without process-local workspace receipts. It must independently bind the resolved problem, request, strategy/version, coordinates, lineage, relation, objective evidence, and verifier payload. Each profile needs separate scientific and architecture approval. This is not implied by the existing runtime verifier.

Until one path is reviewed and implemented, replay returns a typed unsupported result with a field-specific diagnostic such as `artifact.replay.authority` / `no approved replay verifier`. A wrong or unknown verifier ID/version, unsupported profile, missing/malformed relation attachment, or identity/lineage mismatch also returns typed unsupported/rejected diagnostics. Preserve the original recorded claim and run evidence in the imported artifact; do not translate it into infeasibility, a candidate family, or a successful complete family. Do not invent fallback tolerances, proof rules, or accepted verifier aliases.

Even after a replay operation succeeds, only the fresh in-process result receives runtime authority. Saving and decoding it again produces an untrusted claim and requires replay again.

## Versioning and migration

- Keep v1-v4 decoding and their historical migrations unchanged. Do not reinterpret old registered-proof text as authority and do not silently upgrade an old schema to v5 trust.
- Add v5 as a distinct recorded-claim representation. Older readers may return a typed unsupported-version error; they must not drop the claim and report a complete result.
- `encode_run` may emit a v5 recorded claim only from a live family that the current process has already marked registry-verified. This is a producer eligibility check, not a wire trust bit. Unverified complete proposals remain rejected.
- v5 decode never grants runtime authority, even when all digests, schema checks, and identity fields match.
- A future replay operation is versioned independently from artifact parsing. Retiring a verifier or replay implementation makes the claim unsupported for replay; it does not invalidate the fact that the historical artifact recorded that claim.

Whether to replace the current `decode_run` result type, add a separate `decode_artifact` API, and increment the wire schema are public API/migration decisions. This proposal recommends the separate recorded DTO and schema v5, but does not authorize implementing it before review.

## Required adversarial and round-trip tests

Before enabling v5, tests should cover the following caller-visible behaviors using public artifact and registry APIs:

1. Encode verified T-S01 Strategy A, T-S01 Strategy B, and T-S02 A/B results. Assert literal profile/verifier/version/payload, exact FamilyIdentity fields, ordered lineage, objective bounds, relation attachment digest, and schema version in the resulting artifact.
2. Decode each artifact and assert the returned object is `RecordedFamilyClaim`, with exact claim bytes/fields retained and no live `OptimalFamily` publication. Assert no selector can consume the decoded claim.
3. Mutate each of problem ID, effective objective/family request, coordinate order, strategy ID/version, verifier ID/version, proof payload, and lineage order. Recompute ordinary content hashes where applicable. Structural import may preserve these as claims, but replay must reject them and publish no complete family.
4. Remove or alter the relation attachment, mismatch its declared schema/size/digest, use an unknown verifier version, and use an unsupported profile. Assert typed unsupported/rejection with the exact public diagnostic field and preserved run evidence.
5. Assert a valid-looking but self-authored v5 claim never becomes trusted solely by decoding, matching a verifier string, matching a digest, or supplying the resolved problem.
6. Preserve v1-v4 fixture behavior and add a v5 unknown-version case. Re-encoding an imported v5 claim must not set a trusted marker or change its claim into a live family.
7. Where replay is eventually approved, compare its returned fresh result to an independently executed current T-S01/T-S02 result. Only the replay operation can produce the trusted object; decode-after-save must again be untrusted.

No test may use a sampled witness list, residual threshold, or artifact hash as a completeness oracle. Numerical acceptance thresholds and any new coverage procedure remain open scientific decisions under #155/#8 and the profile strategy reviews.

## Review gates and ownership

This proposal does not close #75 or #83. Before code is enabled, architecture reviewers must approve the DTO/API and migration; scientific reviewers must decide whether runtime re-execution is sufficient for replay or define a profile-specific portable replay theorem/receipt. The chosen path must be reflected in #155 and the reviewed class-level architecture. Only then should implementation tickets split the DTO/schema, encoder, importer, replay verifier seam, adversarial tests, and the #75 consumer integration into separately reviewable slices.

Current live code does not establish that a serialized relation attachment can faithfully reconstruct the private T-S01/T-S02 relation payloads. The attachment schema/encoding and whether replay compares canonical mathematical relations or exact serialized representations are explicit open questions; this proposal intentionally does not choose a proof algorithm or numerical tolerance.