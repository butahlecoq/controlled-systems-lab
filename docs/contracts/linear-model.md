# Immutable affine discrete models

MODEL-01 supplies `<csl/model/linear_system.hpp>` and `CSL::model`, based on
[authored interface revision 1.2](core-interfaces.md). It depends on
`CSL::numeric` and transitively `CSL::contracts`; public headers contain no
native matrix, solver or test-library types. This is a C++20 source interface,
without a stable binary ABI.

## Construction and providers

`model::snapshot(const SystemModel&, span<const double> times)` returns
`Result<LinearSystem>`, either a privately constructed immutable handle or one
`Diagnostic`. Authored aggregates remain mutable and unvalidated. Snapshot
validates dimensions, storage, finite coefficients, providers, grid and
observation causality before publishing any handle. `check_model_shape` remains
the older dynamics-only structural guard; it is not this constructor.

The grid has T+1 finite, strictly increasing times, with at least one entry.
States are indexed `[0,T]` and transitions/controls `[0,T)`. The grid is copied
once and is the sole physical-time authority. Continuous or unknown time-domain
metadata returns `unsupported` at `model.time_domain`. Supplied discrete
transitions are used directly, with no discretization.

Dynamics are `x_(k+1)=A_k*x_k+B_k*u_k+E_k*w_k+a_k`, with dimensions n states,
m controls and p external inputs. A is n×n, B n×m, E n×p and a length n.
Singular A and absent m=0 or p=0 ports are legal; an absent port takes an empty
vector. A zero map with a present port keeps its port dimension. State dimension
zero is also representable. No invertibility, constraints or solver assumption
is imposed.

`Coefficients` stores one `LinearStage` for LTI, or exactly T indexed records for
LTV. Constant coefficients are copied once; stage lookups retain the same
immutable buffers. T=0 accepts valid constant coefficients or an empty indexed
provider, but no transition can be called.

Each observation channel stores `ObservationCoefficients`: one `ObservationStage`
or a vector with exactly as many records as its explicit schedule. Indexed
coefficients follow **sample order**, not transition index. Authored order is
preserved, including irregular or delayed samples; nothing is sorted. C is
r×n, Du r×m, Dw r×p, F r×q and b length r in
`y=C*x+Du*u+Dw*w+F*v+b`. Output/error dimensions r/q are constant within each
channel. Empty indexed channels need no invented dimensions; empty constant
channels still validate their single record. State/process inputs and
measurement error remain separate physical roles.

## Observation event clock

An `ObservationSample` names `state_stage`, `measured_at`, `available_at`, and
an optional joint `input_stage` for u/w. `ObservationPoint` contains a stage
and `ObservationTiming`. The causal event ordering is

```text
before_decision(k) < after_decision(k) < before_decision(k+1)
```

`after_decision(k)` means after the controller action, external input realization
**and completion of transition k**. Its physical time is times[k+1].
`before_decision(k)` has physical time times[k]. Thus after(k) and before(k+1)
share a timestamp but are distinct ordered events. Causality uses stage/phase
order, never timestamp comparison alone. Only before(T) exists at the terminal
stage: it is an observation event, not another control decision.

- x0 is released at before(0); x_s for s>0 is released at after(s−1).
- A measured event must not precede its state's release.
- A declared input stage j must lie in `[0,T)`; its u_j/w_j are released at
  after(j). Measurement must not precede this release.
- Availability must not precede measurement. Arbitrary delays within this
  event grid are allowed.

Consequently x_k with current feedthrough can be measured at after(k), and
x_(k+1) can also be measured there. Neither current input dependence nor the
next state can be measured at before(k). A delayed x0 sample with input stage
0 can be measured at after(1) and available at before(2).

With no `input_stage`, both feedthrough maps must be identically zero and the
evaluator takes empty u/w spans. A present input stage declares a dependency
even when its maps are zero; the evaluator requires full m/p input vectors and
the same causal release checks. There is no inferred input stage or revelation
policy. At T=0 only before(0) samples without input dependencies are valid.

`ObservationMetadata` contains the authored sample and three derived times:
`state_time=times[state_stage]`, `measured_time` and `available_time` from their
events. Source state time may precede acquisition and availability. `observation`
and `observe` identify the same channel/sample using distinct `ObservationIndex`
and `SampleIndex` types. `ObservationValue` owns its values and carries that
sample's metadata, so both survive the original model.

This clock does not express a post-action/pre-transition event, between-grid
sampling, pre-action revelation of w, independent u/w source stages in one
sample, or algebraic loops. These require a future source revision and suitable
information-pattern semantics. `observe` evaluates supplied vectors: the caller
must supply x from the declared state stage, u/w from the declared input stage,
and v for that sample. The stateless evaluator does not verify trajectory or
input provenance.

## Public operations and ownership

`LinearSystem` is a non-default-constructible owning handle. Copies, including
construction/assignment from rvalues, retain private shared const storage and
leave their source valid. It provides:

- `dimensions()`, `horizon()` and `channel_count()`.
- Checked `time(StageIndex)`, `stage(StageIndex)`,
  `sample_count(ObservationIndex)` and `observation(ObservationIndex,SampleIndex)`.
- `step(stage,x,u,w)` returning an owning state vector.
- `observe(channel,sample,x,u,w,v)` returning owning values plus metadata.

Accessors return `Result<T> = variant<T,Diagnostic>`. Stage and observation
records contain immutable, retaining numeric views returned by value. Reassigning
such a returned record cannot alter the model. Coefficients remain usable after
all producer buffers and model handles die; borrowed numeric spans/descriptors
still require a live retained view, as in [numeric-data](numeric-data.md).

Snapshot always copies authored buffers, even when called with moved/rvalue
data. A surviving mutable alias into an authored buffer cannot modify the
published snapshot. The grid and schedule metadata are copied too. The producer
must remain live and unmodified during the synchronous construction call;
evaluation spans likewise describe live initialized doubles for the call.
Allocation failures and standard container length errors propagate as exceptions.

Sharing separate copies of a model for concurrent reads is safe. Each evaluation
allocates its own output. Concurrent assignment to the same handle object still
requires caller synchronization. No workspaces or shared mutable arithmetic
scratch are hidden in a model.

## Arithmetic, diagnostics and costs

Evaluation returns `EvaluationResult<T> = variant<T,Diagnostic,OperationStopped>`.
Invalid indices, wrong vector lengths and nonfinite caller operands return
`Diagnostic{invalid_input,...}`. Construction uses `model.times`,
`model.dynamics.coefficients`, `model.observation.coefficients`,
`model.observation.schedule` and `model.observation.causality` fields.
Lookup failures use `model.time`, `model.stage`, `model.observation.channel` or
`model.observation.sample`. Vector errors use `model.step.state/control/external`
or `model.observe.state/control/external/error`.

All coefficients and operands must be finite doubles. Each row starts at zero;
products accumulate in increasing column order, in A/B/E order for step and
C/Du/Dw/F order for observe, followed by the offset. With absent observation
input dependencies, the known-zero feedthrough terms are skipped. Each product
and intermediate sum is checked. A nonfinite intermediate from finite valid
operands returns `OperationStopped{numerical_failure,...}` with no output; its
text identifies the operation, term and row (and column for a product). A
later cancellation of overflowing terms cannot rescue such a calculation.

This is ordinary double evaluation, not correctly rounded, exact, validated or
conditioning-aware arithmetic. Cross-toolchain bitwise agreement is not promised.
No optimization, feasibility, estimation, family-completeness or other evidence
claim is emitted. Invalid input and numerical failure never imply infeasibility.

Construction time/storage are O(K+T+S), where K counts stored coefficient
elements/records and S all scheduled samples; constant maps are stored once and
their zero-feedthrough check is cached across samples. Checked access and handle
copies cost O(1). Step costs O(n²+nm+np+n) arithmetic plus O(n+m+p) input checks,
and O(n) output storage. Observe costs O(rn+rm+rp+rq+r) with O(n+m+p+q) input
checks and O(r) output; absent-dependency feedthrough terms/input checks vanish.
No polynomial bound for a later solver or performance measurement is claimed.

## Caller and verification

```cpp
#include <csl/model/linear_system.hpp>

csl::SystemModel authored{{{1,1,0}, csl::TimeDomain::discrete,
    csl::LinearStage{{1,1,{3}}, {1,1,{2}}, {1,0,{}}, {-1}}}, {}};
const csl::Vector times{0,1,2};
auto result = csl::model::snapshot(authored,times);
// A caller handles Diagnostic before extracting the snapshot.
const auto& model = std::get<csl::model::LinearSystem>(result);
auto next = model.step({0},csl::Vector{2},csl::Vector{1},{});
// Handle Diagnostic / OperationStopped. Successful next is Vector{7}.
```

Use `find_package(CSL 0.1 CONFIG REQUIRED)` and link `CSL::model`. The
[source/installed client](../../tests/installed/model_client.cpp) calls the real
model seam using only public headers and, when staged, the installed package.
[Unit tests](../../tests/unit/model/linear_system_tests.cpp) use independent
literals `[2,7,16]` for LTI/LTV and `21` for all observation terms, rectangular
maps, singular/absent ports, provider/shape/time rejection, causal and delayed
events, finite arithmetic overflow, alias retention and independent readers.

Exact full-state observation is an explicit identity C with zero error,
feedthrough and offset; a partial map remains partial, and an empty channel list
grants no knowledge. Initial information, admissible sets, objectives and solver
configuration are separate. These tests cover T-M01 and the absent-port and
observation portions of T-M02. Singleton/universal/empty admissibility is a
MODEL-02 obligation; this module is not a problem validator or estimator.
