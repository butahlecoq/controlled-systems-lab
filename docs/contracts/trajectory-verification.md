# Independent trajectory verification

`CSL::verification` exposes `verification::verify_trajectory` in
`<csl/verification/trajectory.hpp>`. It consumes an immutable `ResolvedProblem`
and an owning `TrajectoryRequest`; its returned report owns the supplied witness,
claims, original bounds and backend bound provenance even when admission fails.
No solver status substitutes for a trajectory check.

The numerical profile covers nominal open-loop affine discrete LTI/LTV models,
a known initial point, continuous controls, all T+1 state domains, all T control
domains, and full-history linear temporal constraints. Known external sequences
are prescribed original-problem inputs in each E*w term; the witness does not
choose them, and its controls never contain external coordinates. Uncertain
initial/external data, finite/mixed controls and observation-dependent control
semantics receive explicit unsupported diagnostics. Passive observation maps do
not block verification of a nominal open-loop state/control trajectory; this
verifier makes no claim about observation residuals. Singular A, rectangular B,
zero ports and T=0 require no inverse or artificial decision variables.

Each named scalar residual records violation, scale, actual threshold and result.
The comparison is `violation <= abs_tolerance + rel_tolerance * scale`, using the
finite nonnegative policy in the ExecutionContext. This is binary64 numerical
evidence, not outward rounding or a validated certificate. Nonfinite arithmetic
and lost nonzero products stop verification; no partial prefix becomes a pass.
Initial, dynamics, singleton, H inequalities/equalities, temporal rows and the
original terminal objective are recomputed from original data. Empty and
universal sets retain their exact membership meanings.

V membership requires an optional frozen registered LP provider. The verifier
builds a zero-objective nonnegative barycentric feasibility query from the
original vertices/rays and actual tested point, binds its identity to those
bytes, and independently checks sum, nonnegativity and reconstruction. Backend
infeasibility alone does not establish nonmembership. Missing or inconclusive
membership evidence is unsupported, not a constraint pass. Every attempted
query retains its admitted method/version and request/outcome identity record.

Problem identities on the witness, published family, outcome and every supplied
bound must match. A family's immutable identity and relation coordinates must
match the resolved original problem; its effective request objective and
relation representation are also checked. A caller verifying a reported family
must populate `TrajectoryRequest::expected_synthesis` with an
`ExpectedSynthesisBinding` containing the effective `FamilyRequest`, strategy
ID/version and ordered transformation lineage independently of the family.
The verifier compares each value to the family's immutable identity and rejects
missing expectations or mismatches through `bindings` and a field-specific
diagnostic. Witness-only calls remain compatible without this expectation. The
expected value records what the caller intended; it is not proof that the
strategy or transformations were mathematically correct.

The verifier checks evidence fields appropriate to the published outcome
variant, while `FamilyPublisher` controls which variants may be constructed. In
the current contract, a candidate may be published, but complete and partial
optimal families remain unsupported by the publisher. A candidate's
witness-scoped feasibility evidence never proves its whole relation feasible
or all its histories optimal. Backend program IDs are retained as provenance;
a program-to-original-objective transformation is not inferred. Unchecked
certificates and symbolic references are preserved, never elevated to verified
evidence. `bindings == numerical_pass` means all supplied identity expectations
and available original-problem, witness, coordinate and evidence bindings
passed; it does not establish optimality, family completeness or validated
evidence.

`SynthesisResult::incumbents` are `IncumbentCandidate` values: strategy output
and its feasibility support claim, not independently verified feasible
incumbents. The registry may retain a well-shaped candidate while preserving
the strategy's termination and outcome; the candidate alone does not contradict
infeasibility or establish an objective upper bound. Consumers that publish a
problem-aware run must verify each candidate's exact witness against the
resolved problem before recording a feasible incumbent. Problem-free archive
admission keeps the record at `identity_recorded` provenance.
Optimality, complete-family coverage and validated certification remain distinct
unsupported report fields even for a feasible witness and a claimed optimal
backend result. The original mathematical outcome is retained independently of
the verifier's termination.

Cancellation/deadlines are checked between operations and residuals. Explicit
residual and membership-query caps stop conservatively with resource_limit.
They are operation-count caps, not hard CPU or heap bounds; an admitted backend
call obeys its own interruption boundaries. A stop retains already recorded
checks and supplied evidence without certifying an unchecked suffix.
