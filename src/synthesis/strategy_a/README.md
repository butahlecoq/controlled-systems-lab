# Strategy A candidate composition

This is a partial implementation of SYN-03 #66. The public entry point is
`make_registration(Providers)` in `csl/synthesis/strategy_a/strategy.hpp`.
Caller registries select and check five generated-request providers in order:
native H projection, native V affine image/sum, native H conversion, LP, convex.
Checked registrations are borrowed until `StrategyRegistry::prepare`; prepared
strategies own immutable snapshots and their workspaces may outlive the registries.
Every concrete generated operation or optimization request is admitted by its
selected provider before a request-specific workspace is created.

The strategy implements the existing `StrategyPort` / `SynthesisWorkspace`
contract. Its general path admits `nominal_open_loop`, numerical,
`candidate_relaxation` requests with `csl.polyhedron.h` joint output. The
strict
`ts01_exact_integrator` profile is checked by the compiled T-S01 verifier. The
`ts02_constant_integrator` profile is the scalar two-step unit integrator with
controls in `[0,1]`, universal state factors, and constant terminal objective
`3` in linear, zero-quadratic, or zero-map residual-norm form; it is checked by
the shared compiled T-S02 verifier. The strict `ts03_singular_integrator`
profile admits `x1=u0`, `x2=u1` and objective `(x2-1)^2`; it is checked by an
independent compiled T-S03 verifier. Admission uses each verifier's strict
model/objective predicate. Each profile uses a request-dependent verifier key.
The registration freezes the deterministic six-step lineage, and a proposal is
emitted only after the transformations execute in order and the terminal
optimizer reports optimal. T-S01 publishes its analytic segment; T-S02
publishes the shared canonical H-relation for every feasible history; T-S03
publishes the entire line `x0=0, x1=u0, x2=1, u1=1`, `0<=u0<=1`. These avoid
dependence on floating-point H-row ordering. The registry checks the input,
effective request, coordinates, strategy/version, executed lineage, theorem,
bounds, proof identity, and canonical relation. Other exact or partial requests
remain rejected. A supplied family materialization limit is rejected rather
than assigned invented semantics. Operation-provider limits remain
independently enforced by those providers.

The Strategy A-only `strategy-a.nominal-linear-exact-v1` profile additionally
admits finite-horizon, discrete, nominal open-loop problems with known point
initial state, continuous control sets, native H/singleton/empty/universal
state and control factors, no external inputs or nonempty temporal map, and a
linear terminal objective. Its verifier reconstructs the joint history
relation from the resolved problem, interprets every finite binary64 input as
an exact dyadic, proves nonempty boundedness, minimizes the objective exactly,
and checks candidate equality with the complete optimal face by two exact
inclusions. Values outside the finite binary64 range, exact faces that cannot
be represented by finite binary64 H rows, unsupported inputs, empty relations,
failed exact decisions, output-construction budgets and other resource-limit
cases fail closed. This checks the
represented values exactly; Strategy A's forward construction still uses
binary64 providers, so it is not a validated-arithmetic claim. The exact
rational optimum is published using its tight outward binary64 enclosure,
including for non-dyadic values. The profile has its own request and verifier
identities and does not extend Strategy B coverage.

## Derivation and scope

1. `nominal_forward` constructs admitted reachable marginals and retains
   recovery factors, geometry evidence, selected provenance, and coordinate maps.
2. `recover_joint_history` constructs a fallback preimage of the forward terminal
   slice, retaining original constraints and every transition equality.
3. `TerminalOptimizer` optimizes that slice and constructs its entire candidate
   minimizer locus, including quadratic nullspaces and constant objectives.
4. `recover_joint_history` constructs the feasible preimage of that locus in
   canonical `[x0,...,xT,u0,...,u(T-1)]` coordinates.

Recovery joins transition fibers by retaining their shared state coordinates in
one H relation. It never multiplies state/control marginals, and never inverts A.
This uses merged PR #182's direct equation construction rather than the archived
single-witness inverse algorithm. It does not execute separate backward marginal
projections or implement an inverse-only fast path. Recovery assembles its H
inequalities and equalities directly in CSR form. The complete T-S01, T-S02, and
T-S03 profile payloads also retain CSR-backed H matrices, including the full
cross-stage relation. Matrix views let the compiled verifiers and selectors read
those matrices without changing the relation's coordinates or coefficients.
Recorded H attachments still serialize logical matrix coefficients in the
existing dense format. They do not preserve CSR storage.

`CandidateHistory::target` distinguishes the forward-slice fallback from the
terminal-candidate preimage. Merely retaining a terminal optimizer result does
not change the fallback's scope. `CandidateHistory::terminal` retains the actual
terminal program result, slice identity, and provider evidence even after a late
rejection or cancellation. These are scoped program facts. They are not copied
into original-problem bounds, optimum claims, or feasible incumbents, since
forward recurrence and terminal construction support remain `Unestablished`.
The synthesis outcome stays `undetermined`, including compiled-empty forward
cases whose authored infeasibility has not been independently established.

General-path published products use `HeuristicRelationEvidence` and `Unestablished`
feasibility. They are candidate relations, never complete or partial optimal
families. Ordered `FamilyIdentity` lineage records completed aggregate forward
stages, the fallback preimage, terminal construction when present, and final
preimage when present. All forward child operation evidence/provenance is retained
in the candidate payload on successful forward completion. During an incomplete
forward stage, the shared stop reports retain completed aggregate-stage lineage
and the active provider, but cannot export all child geometry/coordinate evidence
through the present stop schema. This known acceptance gap is not hidden by a
new shared contract. No shared interface is changed by this module.

## Supported assumptions and limitations

- Discrete nominal open-loop dynamics, known point initial condition, continuous
  controls, no external port/input, no declared temporal constraints.
- Native H, singleton, empty, or universal authored factors; every state factor
  uses the same ordered labels. Selected numerical forward providers can impose
  additional boundedness, representation, or capacity restrictions.
- Convex terminal objectives admitted by the immutable resolved objective and
  selected LP/convex providers. A terminal anchor is assumed globally optimal
  when constructing its candidate minimizer locus.
- Binary64 row assembly, transformation arithmetic, and forward coverage have
  no reviewed completeness procedure. The shared numerical policy is passed
  unchanged and a mismatching execution context rejects at `StrategyPort`.
- Cancellation/deadline checks occur between phases and inside selected providers;
  this module adds no scheduler, backend, or OS resource-enforcement claim.
  A direct deadline stop preserves `deadline_expired` and uses `cancelled`
  termination, as required by the current shared synthesis result guard.
- Witness selection, independent history verification, reviewed coverage,
  cross-strategy T-X01 comparison, and T-L02 barycentric diagnostics are not
  delivered here. Run export remains limited to the existing H attachment
  format, which materializes matrix coefficients rather than preserving CSR.

The T-S01 and singular T-S03 tests independently establish their complete
optimal-history relations, including equality rank and the literal parameter
interval `[0,1]`; T-S03 also exercises registered completeness verification on
the public StrategyPort path. Constant T-S02 tests preserve multiple terminal
points and all four corner histories. T-S01 evaluates the retained primal with the
original resolved objective and asserts literal cost zero. HiGHS withholds
optional program bounds; their absence is checked before any value access.
The nominal-linear exact profile also checks a stage-varying affine system with
a nonzero initial point and offsets, an intermediate state bound, and a complete
optimal relation that retains an independent control fiber.
For strict T-S01, T-S02, and T-S03, the registered Strategy A paths are exercised
end-to-end. T-S02 checks all four box corners and an interior history, rejects
an inconsistent transition point, verifies equality rank and literal control
bounds, and binds the shared canonical H payload and constant objective bound
through the T-S02 verifier. T-S03 checks its full H relation and zero optimum,
and rejects altered completeness evidence through its verifier. The recovered
T-S02 preimage independently retains the whole control box: all four affine
corner histories are feasible, the three literal dynamics equalities have rank
three, and the literal control bounds
exclude every history outside the box. Adversarial tests reject unreviewed
model/objective inputs at admission and altered lineage, relation bindings,
objective bounds, and enlarged or unrelated payloads at verification. For
T-S01, the pre-verification recovered
H relation is checked independently to be exactly
the five-coordinate canonical segment under an independent equality-rank and
interval-substitution oracle before the compiled verifier accepts the complete
proposal. These three exact analytic profiles do not establish general numerical
family coverage or transfer completeness to another source profile. Issue #66
must remain open.
