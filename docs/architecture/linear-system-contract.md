# General linear-system contract

Date: 2026-10-11. Status: mathematical/interface contract. MODEL-01 implements the discrete affine and scheduled observation subset in [native source revision 1.2](../contracts/linear-model.md); broader problem/uncertainty capabilities remain separate.

Owner direction: begin with optimal control planning without disturbances, while designing abstractions with bounded disturbances, adversarial inputs, partial/noisy observations and unconstrained variants in view. The owner selected C++ for the main implementation, with C++20 as the working standard and Python allowed for independent verification. Specific native types are proposed in the [C++ contracts draft](../superpowers/specs/2026-10-11-cpp-core-contracts-design.md); numerical dependencies remain unselected.

## 1. Dynamics and observation

For the first discrete-time model family, use the affine LTV dynamics

$$
x_{t+1}=A_t x_t+B_t u_t+E_t w_t+a_t.
$$

A simple observation available before selecting the current control is

$$
y_t^{\rm pre}=C_t x_t+F_t v_t+b_t.
$$

Here x is the state, u the control, w the process disturbance or an external player's input, y the measured output, and v the measurement error. Process disturbances change the physical state; measurement errors change the information available to the controller.

| Data | Shape | Responsibility |
|---|---|---|
| A_t | n by n | Free state evolution |
| B_t | n by m | Control contribution |
| E_t | n by p | External/process-disturbance contribution |
| a_t | n | Dynamics offset |
| C_t | r by n | State-to-observation map |
| F_t | r by q | Measurement-error contribution |
| b_t | r | Observation offset |

The conventional state-space letters are A/B for dynamics/control, C for output and D for direct feedthrough. [MATLAB state-space documentation](https://www.mathworks.com/help/control/ug/state-space-models.html). The choice E for the process-disturbance channel preserves the convention used in this dossier; G is another common choice. Historical supplied papers often use D for that channel. Code should use descriptive field names so these notation differences remain harmless.

The earlier [foundations](../research/scientific-foundations.md) also use H for an observation map in some derivations. H and C in these contexts refer to the same mathematical role, not additional independent matrices.

Linear models have zero offsets; affine models allow a_t and b_t. LTI coefficients are constant views; LTV coefficients may be supplied as indexed matrices or a compatible parameterized provider. This does not require materializing T identical matrices.

## 2. Richer observation channels and timing

A more general output can include direct effects of the current inputs:

$$
y_t^{\rm post}=C_t x_t+D_{u,t}u_t+D_{w,t}w_t+F_t v_t+b_t.
$$

This equation specifies signal dependence, not by itself the time when information is available. Under the initial convention, this output becomes available after the current inputs have been selected; it may inform subsequent actions.

An explicit alternative is measurement of the next state,

$$
y_{t+1}=C_{t+1}x_{t+1}+F_{t+1}v_{t+1}+b_{t+1}.
$$

Every observation channel must declare its timestamp, pre/post-decision availability and dependence on inputs. A controller cannot select u_t from an observation that itself depends on the not-yet-selected u_t without a separate well-posed algebraic-loop contract. A disturbance revealed before the action also changes the information pattern.

In the implemented revision 1.2, C/Du/Dw/F/b are one constant record or records
indexed by an explicit sample schedule. Each sample declares its state source
stage, measurement event, availability event and optional joint u/w source stage.
The one validated state-time grid supplies source and event timestamps. Authored
sample order is retained; indexed records follow that order.

Initial feedback convention:

~~~text
receive pre-decision observation / update estimate
controller selects u_t from available history
external input is realized under its declared information pattern
state advances to x_(t+1)
receive any post-decision / next-state measurements
~~~

The native event clock orders before(k) < after(k) < before(k+1). Here after(k)
follows transition completion and has physical time times[k+1]; before(k+1) is
causally later at that same time. Both current-state feedthrough and next-state
measurement may occur at after(k). Measurement before a source is released and
availability before measurement are rejected, including reversed equal-time
events. Delayed old-state and historical-input samples are explicit. Only
before(T) exists at the terminal state; T=0 has no input/transition stage.

No input source means zero Du/Dw and empty supplied input vectors. An explicit
input source keeps its dependency even for zero maps. The stateless evaluator
cannot prove that caller vectors came from those declared historical sources.
Post-action/pre-transition events, between-grid sampling, pre-action disturbance
revelation, independent u/w source stages and algebraic loops require a later
contract. See [linear-model.md](../contracts/linear-model.md) for the full
ownership, numerical-stop and source-migration rules.

For an open-loop plan, u_(0:T-1) is selected before future observations. The observation model remains useful for simulation and later feedback, while a nominal planner with a known initial state need not call an estimator.

## 3. Composition of responsibilities

Proposed responsibilities, irrespective of the eventual language/type syntax:

| Component | Contains |
|---|---|
| LinearDynamics | State transition, named input channels, time domain, dimensions, coefficient providers and offsets |
| ObservationModel | Measurement maps, error channels, offsets, timestamps and information availability |
| SystemModel | Composition of dynamics and zero or more observation channels |
| ControlProblem | Model, horizon, initial-state information, admissible sets, criterion, policy class and requested output |
| UncertaintyModel | Bounded/statistical/model uncertainty, temporal dependencies and applicable assumptions |
| InformationPattern | What each decision maker can observe and when |
| Solver | Supported assumptions, algorithm, numerical backend and result evidence |

An input channel contributes a linear map and has a name/dimension. Its interpretation as selected control, adversarial action, exogenous signal or random disturbance belongs to the problem. Multiple control or external channels can be concatenated into block input matrices without changing state evolution.

Bounded disturbance and “second player” are not synonyms. An adversarial problem additionally specifies its objective, feasible actions, policy class and information. A general multi-player game can require more than the archive's minimax objective.

The physical model should be reusable across different admissible sets and objectives. Constraints are problem data: x_t in X_t, u_t in U_t, w_t in W_t, with extensions for coupled/state-dependent admissibility. The first nominal archival experiments use original stagewise state/control constraints. Optional linear temporal constraints remain representable in ControlProblem but require an explicitly compatible strategy; see the [exact slew-lift proof and algorithm boundaries](../research/temporal-coupling.md). The initial supported robust algorithms may still require separate stagewise independent sets.

## 4. Natural special cases

| Case | Mathematical specialization | Contract consequence |
|---|---|---|
| No process disturbance | No external channel, or W_t={0} | Nominal propagation; record which channel configuration is used |
| No control | No control channel, or U_t={0} | Autonomous/exogenous simulation and reachability; planner capability check |
| Exact full-state observation | C_t=I, F_t=0, b_t=0, no hidden feedthrough | y_t=x_t; explicit full-state information |
| Noise-free partial observation | F_t=0 but C_t reveals only part of x_t | Exact measurements do not automatically reveal the full state |
| No observation | Empty observation collection | Does not imply full-state knowledge; initial-state information remains separate |
| No state/control limits | X_t=R^n and U_t=R^m | Explicit universal sets; optimum can be unbounded or unattained |
| Known initial state | Initial-state set is a singleton | Distinct from uncertain initial-state estimation |
| Time-invariant model | Constant coefficients | No duplicated arrays required |
| Purely linear model | a_t=b_t=0 | Zero-offset specialization of affine model |
| Known exogenous input | External input sequence specified | Prediction with known forcing, not minimax uncertainty |

Absent ports can have zero dimension. Mathematically R^0 contains one empty vector, so concatenation/matrix multiplication can preserve the same equations. An implementation may use explicit optional channels and canonical zero operators rather than allocating zero-filled dense arrays.

A zero channel and an absent channel may produce identical state evolution but have different metadata and information roles. Normalize numerical operations without silently erasing those roles.

Defaults must be explicit: a missing observation specification must not accidentally grant full-state information, and a missing constraint specification must not be interpreted as an empty feasible set.

## 5. Solver scope versus representable model scope

A model can represent singular A, lower-dimensional sets and unbounded admissibility. A particular historical inverse-based algorithm may require nonsingular A; a vertex-based routine may require bounded sets; a convex solver may require continuous convex controls.

These restrictions belong to solver capabilities and validation. Representing a problem does not promise that every solver can solve it. Unsupported, infeasible and unbounded are separate result statuses.

Matrix uncertainty A(theta), B(theta), or state-dependent uncertainty requires a model-family/uncertainty contract. It cannot generally be encoded faithfully as an arbitrary independent additive error with an unexplained bound.

Continuous-time ODE and discrete-time systems should share high-level responsibilities while retaining explicit time-domain types and discretization semantics. A singular continuous descriptor matrix requires a separate descriptor/DAE capability, not merely one extra optional matrix.

## 6. First scenario

Confirmed: optimal control planning without process disturbances. Proposed simplest initial instance: known initial state, affine/linear discrete dynamics, explicit admissible sets, a terminal criterion, and full-state information if observations are needed.

The first solver uses continuous control actions on nominal dynamics while the contracts retain finite/mixed domain types, external-input and observation channels. MODEL-02 source revision 1.4 implements [immutable domain and information data](../contracts/problem-data.md): finite catalogues have explicit dimensions, mixed controls use continuous-then-discrete product coordinates, and initial sets retain explicit quantifiers. Known external sequences, exogenous set sequences and adversarial declarations stay distinct. External stage sets denote their Cartesian product with a whole-sequence quantifier; initial/external admissibility is uncoupled. Correlated histories, fixed-parameter reuse and initial/external coupling require another explicit representation and cannot silently become these marginals. Exogenous names no boundedness guarantee. Finite/mixed actions do not represent hybrid mode/guard/reset dynamics. Optional temporal CSR retains the full state/control history, with no solver or lift implied. Continuous controls do not imply continuous-time dynamics or convex admissibility. A first affine/polyhedral implementation remains the proposed initial solver class. More complex problems should be rejected by this solver with supported-assumption metadata until compatible algorithms exist.

Confirmed output: a representation of all optimal plans and consistent trajectories, with individual witness selection. Initially expose optimal families only. B04 is selected as the first end-to-end benchmark; see its [restoration audit](../research/b04-restoration.md). Its historical data are incomplete and inconsistent, so reported cost 30.899 is not yet an executable acceptance target. Supported stagewise continuous-domain shapes and concrete certificate support remain to be finalized.

## 7. C++ target and Python reference workflow

Accepted owner direction: use C++ as the main implementation language, with C++20 as the working standard and small Python references for mathematics and experiments. This decision is not a measured language-speed ranking. See [ADR 0001](decisions/0001-cpp20-core.md).

HiGHS supplies a C++ optimization library; cddlib supplies C polyhedral routines that can be wrapped behind a backend boundary. [HiGHS](https://highs.dev/), [cddlib](https://github.com/cddlib/cddlib). Numerical backends and their release/license constraints still require selection.

A backend implemented in another language can still be adapted behind native ports; for example, Clarabel has a native Rust solver with several language interfaces. [Clarabel](https://clarabel.org/stable/). Such integration does not change the selected C++ core language.

Before migrating any reference algorithm, stabilize its mathematical inputs/outputs and compare shared scenarios, trajectories, objectives, constraints and result evidence. Retain independent references after migration. Shared versioned scenario data avoids binding the mathematics to Python's object layout.

Do not start by transcribing every Python implementation detail into C++ classes. Keep model data, sets, problems, solver workspaces and numerical adapters separate. The [modular algorithm design](modular-algorithms-and-solution-sets.md) uses the selected C++20 target and proposes CMake, coarse runtime algorithm ports, templates inside kernels, immutable shared data and per-worker workspaces. These architecture decisions precede numerical benchmark validation.
