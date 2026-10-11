# Affine model and observation test oracles

TEST-02 expands the [implemented discrete model contract](linear-model.md)
through public interfaces. The existing
[`linear_system_tests.cpp`](../../tests/unit/model/linear_system_tests.cpp)
minimum suite remains intact. New standalone suites are
[`affine_dynamics_test.cpp`](../../tests/unit/model/affine_dynamics_test.cpp)
and [`observation_model_test.cpp`](../../tests/unit/model/observation_model_test.cpp).
Expected numbers below are hand-derived literals. Neither the production
evaluator nor a duplicate evaluation helper computes the expected answers.

## Dynamics

The required scalar fixture is x0=2, A=3, B=2, a=-1 with u=[1,-2] and no
external port. Both compact constant and explicitly indexed providers must
produce **[2,7,16]**. Unit timestamps [0,1,2] and nonunit timestamps [10,13,29]
produce the same states: discrete matrices are transitions used directly,
not generators scaled by elapsed time.

The independent varying fixture has x0=[1,-2], u=[2,-1], w=[-1,2]:

| Stage | A | B | E | a | Expected next state |
|---|---|---|---|---|---|
| 0 | [[2,-1],[0,3]] | [[1],[-2]] | [[4],[1]] | [-1,5] | [1,-6] |
| 1 | [[0,2],[-1,1]] | [[-3],[2]] | [[1],[-2]] | [4,-3] | [-3,-16] |

Stage 0 sums [4,-6]+[2,-4]+[-4,-1]+[-1,5]. Stage 1 sums
[-12,-7]+[3,-2]+[2,-4]+[4,-3]. Asymmetric coefficients and different stages
detect transposition, stage reordering/reuse and lost input/offset terms.

Singular autonomous A=[[0,1],[0,0]], a=[1,-2], x0=[2,3] yields [4,-2], then
[-1,-2]. Acceptance by the model does not establish compatibility with an
inverse-based synthesis strategy.

For A=2, a=1, x=3, absent m=p=0 ports accept empty vectors and yield [7].
Present one-dimensional ports with B=3, E=-2 require one-element vectors:
u=w=0 gives [7], u=4,w=-3 gives [25], and u=-5,w=2 gives [-12]. Present zero
maps B=E=0 still require one-element inputs. Empty spans cannot stand in for
positive-dimensional zero-valued vectors.

Existing GEO-01 public factories and handle roundtrips separately preserve a
singleton {0} in R^1, universal R^1 and empty R^1. These establish distinct
**set representations**, not model domain enforcement. `LinearSystem::step`
does not receive admissible sets; it validates vector dimensions/finiteness
and evaluates supplied values. MODEL-02 owns admissibility and problem-domain
semantics. A zero map is distinct from both a missing port and a singleton
restriction.

Wrong A/B/E/offset shapes, malformed storage, wrong provider counts and
incorrect/nonfinite operands return input diagnostics. Source-buffer/grid
mutation after snapshot does not change the independent varying trajectory.

## Horizon and time domains

The selected existing policy requires at least one finite, strictly increasing
state timestamp. T transitions use T+1 state times: state times are indexed
[0,T], transitions and inputs [0,T). Boundary and maximum-size indices are
checked before lookup/evaluation.

T=0 accepts a valid constant dynamics record or an empty indexed provider.
The constant record is still validated. The sole time(0) exists, but stage(0)
and step(0) reject; a nonempty indexed provider is invalid. Only terminal
before(0) observations with no input source are valid. No extra transition,
post event or control decision is invented.

Continuous/unknown TimeDomain data return `DiagnosticCode::unsupported` at
`model.time_domain`, while malformed discrete data return `invalid_input`.
Neither result establishes mathematical infeasibility.

The original TEST-02 criterion also requires continuous data to be rejected
by the **initial loader/planner**. That boundary is **NOT YET VERIFIED** by this
suite: direct model snapshot rejection is current model evidence, not evidence
of an actual loader/planner call. Preserve that criterion for a bounded test
follow-up when the boundary exists; no loader/planner is implemented here.

## Observations

Separate full, partial and noisy channels use their own sample indices,
dimensions, maps, offsets and errors. With x=[3,-2]:

| Channel | Maps | Expected measurement |
|---|---|---|
| Full, no input/error source | C=I2, b=0 | [3,-2] |
| Noiseless partial | C=[0,1], b=0 | [-2] |
| Partial with error/offset | C=[0,1], F=2, b=5; v=3 or 0 | [9] or [3] |
| All terms | C=[[2,-1],[1,3]], Du=[[3],[-2]], Dw=[[-1],[5]], F=[[1,2],[-3,1]], b=[7,-4]; u=-1,w=2,v=[4,-3] | [8,-10] |

The all-term result sums [8,-3]+[-3,2]+[-2,10]+[-2,-15]+[7,-4]. With error
v=[0,0], it is [10,5]. The dynamics result for the same x/u/w before and after
observations stays [14,3]: measurement error changes output, not physical
state evolution. Missing observations produce no implicit identity channel;
channel lookup rejects. A partial measurement does not establish knowledge of
the unmeasured state or any estimator/controller capability.

Constant and explicitly sample-indexed identical observation records each
match literals. A distinct indexed fixture authors a delayed x0 sample before
an earlier x1 sample: C=[1,-2],b=3 on x0=[1,-2] yields [8], then
C=[-2,1],b=-4 on x1=[1,-6] yields [-12]. Records follow authored **sample order**,
not transition/state index or sorted timestamps.

Wrong observation shapes/storage/counts, changing output/error dimensions,
nonfinite coefficients and wrong/nonfinite caller operands are diagnosed.
Snapshot coefficients, schedule and times survive producer mutation. Retained
coefficient arithmetic and owning observation values remain usable after the
last model handle dies.

## Event clock

The implemented order is before(k) < after(k) < before(k+1). after(k) includes
completion of transition k and has time times[k+1]; before(k+1) is causally
later at that same physical time. For grid [5,11,23], a state-0/input-0 sample
measured after(0) and available before(1) has state/measured/available times
[5,11,11], with distinct phases and indices retained. Reversing measurement
to before(1) and availability to after(0) rejects despite equal timestamps.

Current control or external feedthrough before its release at after(0)
returns `invalid_input` at `model.observation.causality`. An explicitly declared
input source retains this dependency even for zero feedthrough maps. With no
input source, Du/Dw must be zero and observe requires empty u/w vectors even
when physical ports are present.

Next-state x1 can be measured after(0), but not before(0). Delayed x0/input0
measurement after(1), available before(2), preserves times [5,23,23] and the
historical input index. Terminal x2 can be measured before(2); after(2) and
input stage 2 are invalid. Tests assert source/index/phase metadata as well as
derived timestamps. The evaluator is stateless: caller vectors must match
declared historical sources; it does not establish trajectory provenance.

## Coverage and provenance limits

This expansion covers T-M01, model-port/observation and existing elementary-set
representation portions of T-M02, and singular-model/unsupported-time portions
of T-M03. Whole-problem domain membership, initial-information/temporal
capability validation, inverse-only strategy rejection, loader/planner
rejection, estimation and solver evidence are separate obligations.
Representable channels or disturbances do not imply support by the initial
nominal strategy. No phase extension, discretizer or solver is added.

MODEL-01's original worker report records meaningful public behavior tests
against unsupported production stubs, then 18 failing cases/79 failing
assertions before implementation; its final expanded minimum suite had
20 cases/318 assertions. This is attributed historical test-first evidence,
not a new TEST-02 RED run. TEST-02 independently expands working code; an
initial GREEN is valid. A reproduced behavioral defect must retain its oracle
and become a linked scoped fix with independent review, rather than weakening
the assertion or manufacturing a failure. Compilation errors are not RED.

These suites use finite small integer literals in ordinary double arithmetic.
They make no validated-arithmetic, complete-family, performance or additional
platform claim and impose no historical timing thresholds.
