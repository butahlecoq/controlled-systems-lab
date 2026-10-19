# Issue #4 candidate Volterra enclosure plan

## Scope

Compute a rigorous, same-control error enclosure for the 60-step, two-state
candidate `Volterra.m` recurrence identified by SHA-256 in the source dossier.
The computation uses the candidate's next-reference-sample matrix indexing,
initial state `(1, 2)` for both recurrences and controls in `[-0.3, 0.3]`.
It is a new mathematical check of that candidate, not a reconstruction of L05
Table 1 or a bound on its physical `(410, 300)` nonlinear trajectory.

## Method

1. Recheck the candidate source hash and record the exact recurrence and scope.
2. Enclose `pi` by the alternating Machin arctangent series and `sqrt(2)`
   with integer square roots. Form an outward-rounded interval for
   `T0 = pi/(18 sqrt(2))`.
3. Propagate fixed-decimal integer intervals for the zero-control reference,
   both same-control states, and their difference. Round out at every product
   and division. The bilinear term uses the current nonlinear state box.
4. Save exact machine-readable endpoint strings, a terminal 2D error-box
   illustration, the derivation, source identity and regeneration command.
5. Check small analytic one-step values independently, replay representative
   control histories at higher precision, and review the source correspondence
   and claim labels. No sampled trajectory is treated as the proof.

## Deliverables and gate

Commit the source-check note, reproducible checker, saved record, standalone
HTML/SVG and offline archive. Independently review the scientific claims and
repository standards before merging. Keep issue #4 open until the historical
generator, coordinate mapping, reference sets and all construction contracts
are resolved.
