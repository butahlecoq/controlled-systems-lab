# ADR 0031: Keep strategy lineage names and runtime receipts profile-specific

Date: 2026-11-26
Status: Accepted

## Context

The registry admits strategy proposals against a frozen strategy request,
delegates theorem content to a compiled verifier, and publishes only a verified
family. Complete-family strategies must also prove that their exact-profile
construction actually ran. Those execution facts are conveyed through private
runtime receipts instead of caller-supplied claims.

Several reviewed analytic profiles execute the same deterministic operation
sequence. T-S02 currently reuses the six reach-back steps of T-S01, and T-S03
reuses the two-transition Strategy A operation sequence. The immutable
`FamilyRequest` profile and objective distinguish the proof authority, so the
lineage name is the only profile-specific part of the recorded sequence.

## Decision

- Keep identity and context binding in the registry. It passes the
  already-frozen authoritative request to the compiled verifier, which validates
  theorem content only and does not re-bind identity. A proposal whose
  registered verifier identity, version, or proof payload does not match the
  frozen registration is rejected before verification.
- Represent runtime lineage as private, one-shot receipts created by the
  compiled runners. A Strategy B receipt records that the selected
  exact-profile construction/extraction path, or the approved T-S02 analytic
  relation from the retained feasible artifact, completed. A Strategy A receipt
  records the executed forward reachability, feasible recovery, terminal
  minimization, and optimal recovery stages before the reviewed analytic family
  was proposed. The verifier consumes a receipt once; ordinary strategy
  workspaces have no route to supply this evidence.
- Keep expected lineage names profile-specific even when profiles share an
  operation sequence. `expected_ts02_lineage` and `expected_ts03_lineage` may
  currently return the same steps as `expected_ts01_lineage`, but admission and
  receipt boundaries compare the profile-specific name so that a later
  divergence is not silently accepted.
- A verified family survives a contradictory solver status. Unverified
  incumbent candidates do not establish feasibility and do not change the
  reported outcome; an exact-optimal-relation family is retained only through
  its verified evidence.

## Consequences

Registry tests can distinguish missing execution evidence from a merely
well-formed proposal, and profile identity remains visible at admission and
receipt boundaries. Sharing an operation sequence between profiles is an
implementation economy, not a licence to share lineage identities. Adding or
diverging a profile requires updating its expected lineage and receipt path
together; the registry and compiled verifiers must continue to treat receipts
as private one-shot evidence rather than a public extension point.
