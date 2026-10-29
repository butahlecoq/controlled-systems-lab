# Initial information and sampled observation replay

EXT-04 issue #68 first slice. The implementation is `CSL::controllers` and
`<csl/controllers/observed_replay.hpp>`. It composes the immutable
`model::LinearSystem` observation schedule with caller-supplied estimator and
controller callbacks. It does not change the shared problem, model, synthesis,
or evidence contracts.

## Initial-set quantifiers

`KnownInitial{x}` is a known point. `InitialSet{X, existential}` describes a
choice of some `x0` in `X`. If a synthesis method returns one plan from the
union of feasible histories over `X`, that establishes at most a witness for
some initial state, subject to its own feasibility evidence. It does not give
one plan or policy that works for every `x0` in `X`.

`InitialSet{X, universal}` requests all-initial-states behavior. A fixed
open-loop sequence would need to satisfy the requirements for every `x0` in
`X`; an observation-based policy may choose different actions after different
available histories. Its quantifier order is initial state, then observations
available at each decision, then the resulting action. Observation noise and
external inputs need their own declared quantifiers and information timing.
Neither a union of feasible histories nor a handful of sampled trajectories
proves that universal statement. Empty initial sets and empty external factors
also need explicit outcome semantics; this module does not infer quantified
truth from them.

The replay API accepts a single concrete initial vector. It cannot be passed
an `InitialSet` or a `Problem` and never returns a plan for a set. Existing
nominal synthesis strategies still reject unsupported initial uncertainty and
feedback requests. The finite replay module below provides auditable
policy-family evidence for an explicit scenario list. A separate continuous
affine-policy evaluator is described below. General initial-set synthesis and
policy classes outside that supported profile remain open under #68.

## Event and callback contract

For each transition `k`, replay releases observations whose declared
`available_at` is `before_decision(k)`. It then calls the estimator with that
released history, and the controller with the history and returned state
hypothesis. After the selected action and supplied external vector advance the
model, it releases observations available at `after_decision(k)`. At the end it
releases terminal observations available at `before_decision(T)` without asking
for a further action. Delayed samples enter the history at their declared
availability event. Channel and sample order follow the validated model; a
missing channel supplies no implicit state reading.

The estimator's vector is a *hypothesis*, not a verified reconstruction.
`ReleasedObservation` contains measured values, channel/sample identity and
the model's metadata, not the hidden physical state. The callback signatures
receive only released history and the estimate. As ordinary in-process C++
callbacks, they can close over other caller data; the sampled callback API does
not enforce nonanticipativity against arbitrary captures.
`FiniteObservationPolicy` provides a separate table representation: each
action is keyed by its stage and complete released observation history, and
construction rejects conflicting actions for the same key. The finite family
evaluator applies that table to each supplied scenario and returns its inputs,
trajectory, released observations, and per-step actions. Histories that are
equal under channel/sample identity, release event, and measured values
necessarily use the same table entry.

`ReplayInputs` owns one concrete initial state, one external vector per
transition, and measurement-error vectors indexed by channel and authored
sample. Dimensions and finite values are checked before callbacks run.
Model evaluation can still report a numerical stop. A successful `ReplayRecord`
retains those inputs, every physical state, each decision's available history,
estimate and action, and the ordered released observations with release events.
It is evidence for this one evaluated trajectory under
these exact inputs, not feasibility against problem constraints, state
reconstruction accuracy, optimality, family completeness, validated arithmetic,
or every disturbance/observation error.

## Finite policy-family scope

`FinitePolicyFamilyRequest` requires an explicit existential or universal
initial quantifier and a nonempty finite list of `ReplayInputs`. Each row keeps
its initial state, external sequence, and measurement errors together, so the
enumeration can preserve authored correlation among those values. The
For existential scope, the caller supplies exactly one selected witness row;
the evaluator checks that row and does not search for a feasible witness. For
universal scope, the evaluator checks every listed row. The type does not
accept a continuous `InitialSet`, does not establish
that the rows cover one, and does not quantify over unlisted external inputs or
measurement errors. The evaluator checks that the table supplies every action
needed by every row and that every table rule is exercised. Its returned
evidence establishes nonanticipativity and model replay only on that finite
enumeration; it does not establish constraint feasibility, optimality, or a
continuous all-initial-states/all-disturbances guarantee.

## Continuous affine observation policies

`JointVUncertainty` defines one bounded joint uncertainty set as the convex
hull of its complete authored generator rows. The coordinate layout places the
initial state first, then each stage's external input, then every scheduled
measurement-error vector. Each row carries all these values together, so
correlation across the initial state, stages, and observation errors is
preserved. This joint set is the source of truth for its initial-state
projection; it is not combined with a second independently supplied
`InitialSet`.

`AffineObservationPolicy` stores a state estimate and action map for each
decision stage. Each map names the observation components it may read. The
builder rejects a reference whose declared availability is later than
`before_decision(k)`. A post-decision observation at stage `k` can therefore
affect a later decision but cannot affect the action already chosen at `k`.
The policy has no callback entry point and cannot capture hidden future data.

`PolicyCoverage::all_joint_uncertainty` evaluates every authored generator of
the complete convex domain and returns per-generator, per-step states,
released histories, estimates, actions, and safety margins. Under the affine
model, affine policy, and linear safety-row assumptions, each safety margin is
affine over the domain, so generator checks cover the convex hull. The reported
assurance is `numerical`; binary64 propagation is not a validated proof. A
margin within the requested tolerance is `inconclusive`, and a negative
margin retains the generator trajectory that produced it.

`PolicyCoverage::selected_joint_witness` instead accepts nonnegative convex
weights over the generators and evaluates one selected joint point. It does
not search for a witness, establish a universal guarantee, or implement the
quantifier order `exists initial state, for all disturbances and errors`.
That alternation remains unsupported. Neither coverage mode searches for or
optimizes a policy. Safety constraints must be supplied as linear rows; the
evaluator does not verify estimator accuracy or objective optimality.

This API is distinct from `replay_observed_policy`, which runs one point
through arbitrary callbacks, and `replay_finite_policy_family`, which checks
an explicit finite list of scenarios. The former supports callback flexibility
without a continuous coverage claim; the latter enforces nonanticipativity
only on its listed rows.

## Supported variants and checks

The first contract test uses a two-dimensional system with a one-dimensional
noisy partial pre-decision channel and a delayed next-state channel. Its
independent literal trajectory is `(1,7) -> (2,7) -> (9,7)`, with released
readings `4` and `7`; the second reading is absent at decision zero and present
at decision one. A separate no-channel case checks that no state is silently
observed. Malformed measurement-error shape returns a diagnostic before any
positive record. These are distinct scenario variants, not a claim about all
possible observations or disturbances.

The finite-policy contract test separately enumerates two runs with the same
two-dimensional initial state and one partial pre-decision sensor, but with
measurement errors `-1` and `+1`. The released first-coordinate readings are
`0` and `2`, so the policy may select different actions using those noisy
readings. Its universal result covers only those two supplied rows; it does
not bound observation noise or certify unlisted disturbances.

The algorithm can produce numerical replay records. Its fixed-source harness
and versioned HTML/raw report are published at
[the observed-replay result](https://butahlecoq.github.io/controlled-systems-lab/ext04-observed-replay-eb0b06e560360611d2f2a16fba9b1204e0415b4ba5cd0d5210427c6349963b34/index.html).
Main Pages run 38921719235 succeeded; the published page and raw downloads were
verified against the reviewed artifact hashes (page SHA-256
`ab8f2e3b5039d3c52e73e8d7f6b052c891cf099a45845257f23e2258c0dd22e1`). The
report covers the configured sampled replay only and does not establish an
all-initial-states policy, universal disturbance coverage, or validated
guarantees. This report does not measure or validate the finite policy-family
or continuous-policy evaluators. The continuous evaluator supports affine
policies over an authored joint V-polytope or H-polytope. The H path solves one
feasibility LP for a numerical domain witness and one support LP for each linear
state/action safety row. It preserves correlations encoded across initial
state, external inputs and measurement errors. A satisfied row requires a
numerically feasible dual multiplier whose independently evaluated objective
is below the row bound. If that does not establish safety, a feasible primal
point is replayed and retained when it violates the row. Empty-domain claims,
unbounded support, missing dual witnesses, and tolerance-band cases remain
inconclusive.
Assurance is numerical, not validated. H-domain policy synthesis,
existential-initial / universal-disturbance quantifier alternation, and
validated arithmetic remain open work under #68.

The [two-state continuous-policy example](../examples/continuous-policy-2d.html)
shows a position-velocity rectangle and its terminal image under a
position-only affine observation policy. The runnable source is
`examples/continuous_policy.cpp`.
