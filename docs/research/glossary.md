# Glossary

Canonical English terminology for this project. Status: provisional, 2026-10-11. [Mathematical definitions](scientific-foundations.md).

## System and problem terms

| Term | Meaning / distinction |
|---|---|
| Controlled system | Dynamics whose evolution depends on selected inputs; the core abstraction is independent of fuel physics |
| State | Variables needed to predict evolution under the model, $x_t$ |
| Control / action | A decision input, $u_t$; “action” is especially useful for finite catalogues |
| Disturbance | An uncontrolled uncertain input, $w_t$, under explicitly stated admissibility |
| Observation | Measured output, possibly noisy or partial; not necessarily the full state |
| LTI | Linear time-invariant dynamics; stage matrices are constant |
| LTV | Linear time-varying dynamics; matrices may vary by stage/time |
| Discrete-time dynamics | Recurrence describing state transitions between stages; stage-transition coefficients are distinct from continuous-time differential-equation coefficients |
| Affine dynamics | Linear dynamics plus an offset; essential for general linearization in absolute coordinates |
| Descriptor system | Dynamics written with a matrix multiplying the derivative; a singular matrix may define a DAE |
| DAE | Differential-algebraic equation; consistency/index requirements exceed ordinary ODE integration |
| Linearization | Local derivative approximation of nonlinear dynamics |
| Reference trajectory | A nominal state/input history around which a model may be linearized |
| Deviation coordinates | State/input differences from a reference; distinct from absolute physical quantities |
| Linearization residual | Difference between nonlinear dynamics and their affine approximation; needs a bound for robust nonlinear claims |
| Discretization | Construction of discrete transitions from continuous dynamics and an input/uncertainty convention |
| State-transition matrix | Fundamental solution mapping states between times in an LTV ODE |
| Zero-order hold | Input held constant between switching times |
| Time grid | Ordered physical times; stage index and elapsed seconds are different |
| Horizon | Number of future transitions, T, or corresponding physical interval when stated |
| Terminal target | Desired state or admissible final set |
| Terminal objective | Criterion evaluated at the final state |
| Stage cost | Criterion accumulated at intermediate steps |
| Phase constraint | Historical term for a state constraint; avoid confusion with phase in multiphase optimization |
| Finite-action domain | A discrete catalogue of allowed controls; its convex hull is a relaxation |
| Hybrid mode | A discrete operating regime with its own dynamics and admissible continuous controls; it is distinct from a finite control action |
| Mode path | An ordered sequence of mode identities followed by a hybrid trajectory; parallel transition edges are distinguished separately |
| Guard | A condition on the pre-transition state that enables a particular mode transition |
| Reset relation | A relation from the pre-transition state to the post-transition state applied when an enabled transition fires |
| Mixed-integer control | Controls combining continuous values with integer/discrete decisions |
| Uncertainty set | Admissible values or models; distinguish deterministic sets from confidence regions |
| Stagewise independent uncertainty | Cartesian uncertainty admissibility over stages; a set assumption, not necessarily probabilistic independence |
| Fixed-parameter uncertainty | One unknown parameter persists across the horizon; replacing it independently each step usually enlarges uncertainty |
| Information pattern | What is observed and when decisions are made |
| Causality / nonanticipativity | A decision cannot depend on future observations or disturbances |

## Sets and reachability

| Term | Meaning / distinction |
|---|---|
| Reachable set | States realizable from allowed histories, under specified control/disturbance quantifiers |
| Reachable tube | Sequence of reachable sets over time; sometimes a continuous-time enclosure |
| Generalized reachable set | Archive term for all disturbance-driven states under a fixed control plan |
| Controllable set | Initial/current states from which a target can be reached under a specified admissible policy |
| Robust controllable set | States from which some admissible policy reaches the target for every modeled disturbance |
| Viability | Ability to remain in admissible states under the declared policy/uncertainty semantics |
| Predecessor | States that can transition into a target set with specified existential/universal quantifiers |
| Convex hull | Smallest convex set containing the given set |
| Polyhedron | Intersection of finitely many affine half-spaces/equalities; may be unbounded |
| Polytope | Bounded polyhedron, equivalently convex hull of finitely many points |
| Vertex / extreme point | A point not expressible as a nontrivial convex combination of other set points |
| V-representation | Polytope representation by vertices |
| H-representation | Representation by linear inequalities and necessary equalities |
| Double description | Polyhedral conversion machinery between generator and inequality descriptions |
| Redundant vertex | Candidate point already in the convex hull of other candidates |
| Redundant inequality | Constraint whose removal does not enlarge the represented set |
| Minkowski sum | All pairwise sums of points from two sets |
| Pontryagin difference | Translations whose sum with the subtracted set lies entirely in the first set |
| Projection | Image under a coordinate/linear map; can eliminate variables |
| Support function | Supremum of a directional linear functional over a set |
| Support point | An attaining point for a support query when one exists |
| Zonotope | Affine image of a box; compact generator representation |
| Constrained zonotope | Affine image of bounded generator factors subject to linear equality constraints |
| Matrix zonotope | Zonotopic set of matrices, often representing uncertain models |
| Ellipsoid | Set defined by a quadratic shape matrix and center; covariance and deterministic shape need different semantics |
| Lazy representation | Stores operations symbolically until a query requires evaluation/materialization |
| Ambient dimension | Dimension of the containing vector space |
| Affine dimension | Dimension of a set's affine hull; can be smaller than ambient dimension |
| Inner approximation | Subset of the reference mathematical set |
| Outer approximation | Superset of the reference mathematical set |
| Conservatism | Excess uncertainty or loss of feasible states due to sound approximation; metric must be stated |
| Wrapping effect | Growth of overapproximation through repeated representation/enclosure operations |
| Sampled point cloud | Finite observed/generated points; not a complete reachable-set certificate |

## Optimization and control policies

| Term | Meaning / distinction |
|---|---|
| Open-loop control / control plan | Entire sequence selected without future feedback; preferred English for historical “program control” |
| Feedback policy | Rule mapping available observations/state history to actions |
| Adaptive control, archive usage | Measured-state replanning over the remaining horizon; does not automatically mean parameter identification |
| Adaptive identification | Updating model/parameter information from new observations |
| Shrinking horizon | Replanning with the same final time and fewer remaining transitions |
| Receding horizon | Repeated planning and applying initial actions; may use a moving fixed-length or shrinking horizon |
| MPC | Model predictive control; behavior depends on policy, horizon, constraints, model and terminal ingredients |
| Minimax | Minimization by the controller of a worst-case criterion; policy and quantifier order are part of its definition |
| Worst-case oracle | Procedure returning a justified maximum or bound over modeled uncertainty |
| Robust feasibility | All admissible uncertainty realizations satisfy constraints |
| Robust containment | Entire uncertainty-reachable set lies inside the admissible set |
| Recursive feasibility | A controller remains feasible after successive admissible closed-loop transitions |
| Tube MPC | Controls a nominal trajectory with a structured uncertainty tube and suitable feedback/tightening |
| Scenario tree | Branching representation of uncertainty/observations with nonanticipative decisions |
| SLS | System Level Synthesis; parameterizes closed-loop responses under its modeling constraints |
| zoRO | Zero-order robust optimization; uncertainty/backoff updates separated from reduced nominal solves |
| RTI | Real-time iteration; preparation/feedback organization of limited optimization iterations |
| MHE | Moving horizon estimation of states/parameters from a recent observation window |
| LP / QP / SOCP / SDP | Linear, quadratic, second-order cone and semidefinite programming problem classes |
| Convex optimization | Minimization of a convex objective over a convex feasible set; convex maximization is generally different |
| Global optimum | Best feasible objective over the declared full problem/policy class |
| Local optimum / stationary point | Local optimization result; does not imply global worst-case certification |
| Incumbent | Best feasible solution currently found in a search |
| Objective bound / optimality gap | Certified bound and distance from incumbent to possible optimum; conventions depend on optimization direction |
| Branch-and-bound | Search using valid bounds to prune subproblems while preserving the promised global result |
| Warm start | Reuse of a compatible previous solve's numerical state |
| Constraint tightening / backoff | Adjusted nominal limits intended to cover uncertainty under specified assumptions |
| Chance constraint | Probability requirement; distinct from deterministic all-disturbance feasibility |
| Confidence region | Statistical set with stated coverage/model assumptions; not an unconditional physical bound |
| Koopman lifting | Representation using observables in an enlarged space; finite approximations need residual/validity treatment |

## Software and evidence terms

| Term | Meaning / distinction |
|---|---|
| Domain adapter | Physical-model/application integration into the common problem contract |
| Backend | Numerical/set implementation behind a shared interface |
| Capability | Declared supported operation/problem property and associated assumptions |
| Scenario | Identified mathematical problem instance: model, initial information, horizon, constraints and objective, independent of the selected solution algorithm |
| Scenario template | Documented example from which a user creates their own scenario |
| Run configuration | Selected algorithms, witness request, numerical settings and resource policy for solving a scenario |
| Scenario document | Versioned description of a scenario, optionally accompanied by separately identified run settings |
| Problem manifest | Recorded scenario definition with provenance and any separately identified run settings; avoid using this term for solver configuration alone |
| Solver workspace | Mutable per-solve/worker state, distinct from immutable problem data |
| Certificate | Evidence for a specific feasibility, inclusion or optimality claim; identify what it certifies |
| Validated numerics | Numerical procedures accounting for rounding/truncation to justify bounds |
| Residual | Measured mismatch in equations/constraints; tolerance-based evidence alone is not universal proof |
| Represented-dyadic input | Finite IEEE 754 binary64 value interpreted as the exact dyadic rational represented by its bits in the resolved computational model; does not imply equivalence to an authored decimal or physical value |
| Authored-real claim | Claim about intended source values or a physical model rather than the stored binary values; requires separately identified conversion, uncertainty, or model-error evidence |
| Tolerance profile | Versioned identity for one method profile's residual quantities, units/scales, requested/effective tolerances, and independent acceptance criteria |
| Numerical completeness support | Profile-specific evidence accepted by a compiled coverage verifier; it supports a numerical claim and is not an exact or validated certificate |
| Coverage verifier | Selected compiled profile component that checks the binding, soundness, and coverage evidence for a complete-family claim |
| Historical baseline | Published result with original assumptions and implementation context |
| Corrected reference | Baseline after a documented correction; separate from original reported values |
| Reproduction | Independent rerun matching an identified problem/environment sufficiently to compare |
| Characterization | Isolated experiment documenting actual legacy behavior without repairing it |
| Provenance | Source ID/hash, inputs, implementation version and environment behind an artifact |
| Throughput | Number of completed jobs per time interval |
| Latency | Time to obtain an individual result |
| Hard real-time | Required deadlines with suitable worst-case timing justification |
| Oversubscription | More runnable worker/library threads than the resource policy can efficiently support |
| Checkpoint | Persisted state allowing supported work to resume consistently |
| Determinism | Declared repeatability; bitwise equality and tolerance-level agreement are different |
| Unsupported result | Clear rejection of an incompatible operation/problem, not a numerical failure |
| External single-witness cross-check | One independently produced feasible witness used as auxiliary evidence for a specified case; not a paired comparison, benchmark, or performance claim |
| Owner-authorized reference variant | Separately identified case variant whose disputed or clarified inputs were explicitly affirmed by the owner; it does not alter the frozen historical scenario or establish reproduction |

## Optimal families and algorithm composition

| Term | Meaning |
|---|---|
| Optimal solution family | Representation of all supported feasible plans/trajectories attaining the primary optimum, with explicit coverage evidence |
| Joint trajectory relation | Constraints linking all states and controls across the horizon; preserves temporal dependence |
| Control fiber | Controls compatible with a specified state/trajectory condition in a joint relation |
| Terminal minimizer set | All reachable terminal states attaining the terminal-cost minimum; not one selected point |
| Optimal face | Face of a polyhedral feasible set exposed by an attained linear optimum |
| Family completeness | Evidence that a representation covers every optimizer in the declared problem/plan class |
| Witness selection | Extracting one consistent solution from a family using a declared selection rule |
| Secondary optimization | Selecting among primary optimizers using another criterion without changing primary optimality |
| Basis diagnostics | Optional LP data about basis/pivots/factorization, beyond primal objective and solution |
| Phase-I simplex | Auxiliary LP procedure to establish feasibility using an artificial basis; historical hull routines reuse its information |
| Algorithm strategy | Composition of mathematical operations and backend requirements into a solve method |
| Equivalent conversion | Representation change preserving the same mathematical set under declared assumptions |
| Set approximator | Algorithm producing a declared inner/outer enclosure of a reference set |
| Operation registry | Extensible resolution of operation implementations from representations, capabilities and requested guarantees |
| Ellipsoidal family | Collection of ellipsoids used through specified union/intersection and directional semantics; finite sampling need not be exact |
| Ellipsotope | Generator-based convex representation combining ellipsoidal and zonotopic geometry; operation capabilities are representation-specific |
| Hybrid zonotope | Generator representation with continuous and binary factors for nonconvex alternatives |
| Polynomial zonotope | Polynomial generator expression retaining dependence between factors; generally nonconvex |
| Constrained polynomial zonotope | Polynomial generator representation with equality constraints on factors |

The first public workflow requests optimal families only. Separate feasible/near-optimal requests are future extensions. See the [modular architecture](../architecture/modular-algorithms-and-solution-sets.md) and [representation source review](../architecture/set-representations-and-ellipsoidal-toolbox.md).

## Notation policy

Use $E_t$ for the discrete disturbance channel in curated mathematics, and $E_c$ for the continuous descriptor matrix. Original papers often use $D_t$ for disturbances and may use $w(t)$ for a time/state “position”; record translations when transcribing.

Reserve $X_t$ for admissible state sets, $R_t$ for reachable sets, and $S_t$ for target/predecessor sets. Use $U_t$ for controls and $W_t$ for disturbance domains. Use T for transition count and $\tau$ for physical time.

Do not translate historical “program” as “software program” when it means an open-loop plan. Do not use “exact,” “adaptive,” “robust,” or “optimal” without the relevant assumptions, policy class and numerical evidence.

The [linear-system interface contract](../architecture/linear-system-contract.md) uses C for the observation map, consistent with common A/B/C/D state-space notation; earlier source derivations also use H for that role. Code fields should identify the semantic role explicitly.
