# Synthetic affine and nonlinear controller study

Status: executable contract proposed for review, 2026-11-09, issue #607.
This document resolves the execution choices in the
[scenario design](../research/mpc11-nonlinear-study-design.md).
The [implementation plan](../research/mpc11-implementation-plan.md) identifies
the remaining code and evidence steps. It adds no numerical result. Both cases are authored synthetic models; fuel
state meanings and parameters are not a restoration of B04, B06, or L05.
The owner's autonomous benchmark authorization permits later implementation
and capture. The separate prohibition on acados runs and installation remains.

## Cases and identities

The scenario design defines the equations, parameters, units, initial states,
physical bounds, terminal targets, and dimensionless objectives for
`SYN-NL-FUEL-01` and `SYN-NL-LV-01`. Those definitions are inputs to this
contract. Each machine-readable scenario must include them directly, with a
canonical JSON hash; a link to prose alone is insufficient input evidence.

| Case | Raw state order | Scale vector | Final time | Interval count N | Hold interval |
| --- | --- | --- | --- | ---: | --- |
| SYN-NL-FUEL-01 | m_ox, m_f, q_ox, q_f | 100 kg, 30 kg, 3 kg/s, 1 kg/s | 20 s | 40 | 0.5 s |
| SYN-NL-LV-01 | P, R | 100, 80 thousand individuals | 3 day | 30 | 0.1 day |

All optimization variables and replay tolerance checks use scaled states
`z_i=x_i/scale_i`. Saved trajectories also retain physical coordinates and
units. The affine origin is a declared reference state, not an inferred
physical/deviation transformation. Observations are exact full-state values
from the named numerical execution integrator, without noise or delay.

Each case has three distinct mathematical/controller IDs:

- `affine-plan/affine-replay`: one CSL affine solve at t=0 and exact discrete
  affine replay of its complete held input history.
- `affine-plan/nonlinear-replay`: the identical saved control history and
  initial physical state executed on the original nonlinear ODE.
- `nominal-nmpc/nonlinear-replay`: local nonlinear optimization at each sample,
  first held input applied to that same ODE, with a shrinking horizon.

The affine witness ID is shared only between the first two variants. NMPC
predictions and its executed trajectory have distinct IDs. These are
controller/model experiments, not equal-problem algorithm parity. A completed
replay does not confer nonlinear feasibility, optimality, or family coverage.

## Common objective and shrinking horizon

Let t_j=j*dt, with final stage N fixed throughout execution. At update j,
NMPC optimizes controls j through N-1 and predicts the terminal state at t_N.
There is no prediction or fuel-reference evaluation after t_N. No solve occurs
at j=N. The objective is

`J_j = Phi(x_N) + sum(k=j..N-1, ell_k(u_k))/N`.

The denominator remains the original case interval count N. The tail contains
N-j terms; dividing by N-j would increase the relative input penalty as time
passes and define a different controller. Costs already incurred are constants
and are omitted from the local objective. The final executed objective is
always J_0 evaluated from saved executed controls and independently replayed
terminal state, including all N running terms. Partial execution has no
completed J_0; it retains the running-cost prefix and last state.

For fuel, Phi is the four-term terminal expression in the scenario design,
and `ell_k=.02*((u_ox,k-ubar_ox,k)^2+(u_f,k-ubar_f,k)^2)`.
For LV, Phi is its two-term terminal expression and
`ell_k=.05*(u_k/.05)^2`. Fuel nominal commands are sampled at interval
midpoints: `ubar_i,k=qbar_i/(Q_i*sqrt(mbar_i(t_k+dt/2)/m_i0))`.
These samples are held constant within each interval. The analytic continuous
reference defines linearization, while its sampled held commands need not
reproduce the original nonlinear reference exactly. That discrepancy is
measured by nonlinear replay.

Stage penalties are authored effort/reference-deviation costs. A penalty on
`u_k-u_(k-1)`, including do-mpc's convenience input-change penalty, must not
replace them. The collocation implementation uses a sample-indexed stage
penalty scaled to implement exactly the displayed discrete sum, without an
extra dt factor. Save the expanded NLP objective and independently compare its
value with the displayed formula on supplied decision values.

## Affine producer and constraints

Fuel uses the design's midpoint Jacobians of the physical vector field about
its analytic reference and midpoint nominal command. Within interval k, the
continuous Jacobians are frozen. The matrix exponential defines A_d,k and
B_d,k. The discrete offset is

`c_d,k = xbar(t_(k+1)) - A_d,k*xbar(t_k) - B_d,k*ubar_k`.

This is an authored endpoint-matching affine prediction model. It is not the
unmodified zero-order-hold discretization of the local Taylor offset. Save
A_d, B_d, c_d, reference samples, Jacobians, and the exponential method/version.
LV uses the single Jacobian at `(P,R,u)=(100,80,0)`, frozen for all stages;
its affine offset is the first-order Taylor offset and the exact constant
linear ODE discretization uses a matrix exponential. Save both physical and
scaled coefficients and the transform between them. No relinearization occurs
in either affine-plan variant.

Both optimizers use the common physical state and input bounds from the
scenario design. The affine solve additionally imposes its stated trust region
at every mesh state and input. Fuel deviations are measured from the analytic
state reference and midpoint held-command samples. LV deviations are measured
from `(100,80,0)`. NMPC uses the common physical bounds and does not impose the
affine trust region. The report lists this controller restriction explicitly;
objective differences cannot be attributed solely to model fidelity or solver
quality. Applied inputs must satisfy common actuator bounds in every variant.

The affine problem must be assembled and solved through actual CSL public
model/program/provider seams. Preserve the strategy or formulation ID,
provider/version, assurance, complete control witness, objective definition,
termination and solver evidence. The quadratic cost on the joint history must
be represented explicitly; a terminal-only objective that silently drops the
input terms is invalid. If the chosen synthesis strategy cannot express that
joint objective, use a documented public CSL joint-program formulation and
record that distinction. A Python-only affine solve is a reference, not the
required CSL producer.

## Nominal nonlinear controller

The initial implementation profile is do-mpc 5.1.2, CasADi 3.8.0, and its
bundled IPOPT/MUMPS plugin, with nominal full-state feedback (`n_robust=0`).
Use Radau collocation of degree 3 and one finite element per held interval.
State constraints apply to all collocation and mesh points, including the
initial and terminal states. Inputs are constant on each physical interval.
At update j, rebuild or parameterize the NLP for N-j intervals and log that
setup cost separately from the solve. Stage indices refer to absolute physical
time, so fuel reference samples are the tail of the original schedule.

Use IPOPT `tol=1e-8`, `acceptable_tol=1e-6`, `max_iter=1000`, and MUMPS.
At j=0, fuel input guesses are ubar and LV input guesses are .025 day^-1.
Fuel state guesses follow its reference but replace the first state with the
actual observed initial state. LV state guesses are the coexistence point,
again replacing the first state with the observation. Collocation stage guesses
use the corresponding state reference. Their infeasibility is permitted as an
initial guess and must not be described as a feasible witness.

At j>0, drop the first prior optimal input and state interval. The remaining
N-j inputs form the new input guess without adding a repeated terminal input.
Shift corresponding collocation/state guesses and replace the first state with
the newly observed execution state. Set dual multipliers to zero at every
solve; do not silently enable a different dual warm start. Save initial guesses
or their reproducible recipe and source solve ID. A refinement run changes the
collocation degree or element count under a new controller configuration ID.

Retain raw solver return status, success flag, iteration count, objective,
primal constraint residuals, dual variables and local stationarity diagnostics
when exposed. Missing stationarity data is explicitly unavailable. Local NLP
success is never a global optimum or minimax certificate. A failed, timed-out,
nonfinite or rejected solve stops execution before applying another input;
retain the partial trace and reason. There is no implicit fallback command.
A diagnostic primal violation does not disappear because the solver reports
success; the independent checker labels the witness accordingly.

## Nonlinear execution and independent replay

Execution uses CVODES per held interval with scaled-state absolute tolerance
1e-10 and relative tolerance 1e-9. Apply the first NMPC input, integrate exactly
to the next sample boundary, and expose that endpoint as the next observation.
The affine open-loop history uses the same execution procedure. Save execution
integrator/version/tolerances and every applied input.

Independently replay each complete or partial saved control history through
existing `CSL::simulation`, using its adaptive RK4 step-doubling method and
original derivative callback. Do not reuse optimizer or execution states as
replay output. Use scaled-state absolute tolerance 1e-10 and relative tolerance
1e-9, with 100000 step attempts per original hold interval. The constraint
checker splits each hold interval into 20 equal reporting subintervals with the
same constant input. The replay adapter's receipts retain attempted/accepted
steps and local estimates. Repeat at absolute 1e-11 and relative 1e-10; report
endpoint, objective and maximum constraint-violation differences. Different
integration methods and tighter tolerances provide sensitivity evidence, not
certified global error bounds.

Recompute Phi and every running term from the original equations/scales and
saved controls. Report physical and scaled violations at optimization nodes,
execution samples and independent replay points separately. No sampled grid
proves continuous-time safety or all-history containment. No nonlinear robust
claim is admitted without separate domain-wide residual, discretization and
arithmetic evidence. Model evaluation outside its declared real-valued domain
(for example negative fuel mass under a square root) terminates the trace with
an explicit model-domain error.

## Records, costs and figures

A `csl.mpc11.controller-attempt/1` record contains:

- case/scenario hash, model/affine-transform/controller/objective IDs, source
  commit, platform and dependency-lock hashes, strategy/provider identities;
- variant, repetition/order, initial state, complete physical grid and units,
  common constraints, affine-only restrictions, numerical settings and limits;
- each solve's update index, remaining horizon, guess identity, local status,
  objective, stationarity/primal/dual diagnostics or explicit unavailability;
- applied held controls, execution and independent replay trajectories,
  witness associations, check results, prefix/failure reason and completed J_0
  or explicit missing objective;
- separate setup, affine optimization, per-NLP optimization, execution
  integration, independent replay/checking and render/export durations;
- requested, enforced and observed CPU/memory/wall limits and accounting scope.

Raw solver logs and every failed/refused/cancelled/resource-limited attempt are
retained and hash-bound. Setup is excluded from solve duration but retained as
its own cost. Inclusive parent spans are not summed with their children.
Use the comparison-program process limits and at least five alternating tuned
Release repetitions plus a separate limiter profile for timing comparisons.
Correctness pilots are labelled descriptive and do not establish a winner.

Figures are generated only from saved records. Fuel has two aligned panels,
`m_ox (kg)` versus `q_ox (kg/s)` and `m_f (kg)` versus `q_f (kg/s)`.
LV has `P` versus `R` in thousands of individuals. Overlay the three variant
trajectories with initial/terminal markers, the target, and labelled time
samples; supply state/control time traces as companions. Preserve variant,
case, witness, model and integrator identities and explain omitted coordinates.
These are individual numerical trajectories. No hull, reachable-set boundary,
backward-winning set or intersection is asserted without separately computed
set evidence.

## Optional environment and delivery

The research environment is isolated from required CSL dependencies. A proposed
Linux x86-64 CPython 3.11 environment uses these publisher artifacts:

| Artifact | SHA-256 |
| --- | --- |
| do_mpc-5.1.2-py3-none-any.whl | 4c9b7d3c17c3104beebdc46900a00dbfc0ef0bddcb47cf9e92957b31d056cf63 |
| casadi-3.8.0-cp311-abi3-manylinux2014_x86_64.whl | bd49a1e4cb193c6203e20add2c2e3d5311eb1fc03fd3146ebe3abae460884282 |

Publisher metadata: [do-mpc 5.1.2](https://pypi.org/pypi/do-mpc/5.1.2/json),
[CasADi 3.8.0](https://pypi.org/pypi/casadi/3.8.0/json).
The executable integration must pin Python, NumPy, SciPy, pandas, Matplotlib
and all transitive distributions with hashes, record loaded plugin/build
versions, and retain actual wheel third-party notices. Top-level licenses are
[do-mpc LGPL-3.0](https://raw.githubusercontent.com/do-mpc/do-mpc/v5.1.2/LICENSE.txt),
[CasADi LGPL-3.0](https://raw.githubusercontent.com/casadi/casadi/3.8.0/LICENSE.txt)
and [IPOPT EPL-2.0](https://coin-or.github.io/Ipopt/LICENSE.html).
The [CasADi release manifest](https://github.com/casadi/casadi/releases/tag/3.8.0)
identifies bundled solver sources. This document does not qualify every bundled
binary license or prove this exact environment runs; those checks precede use.
No library release is needed for this documentation change. Later optional
harness/dependency integration requires its own delivery-impact review.
