# EXT-05 Explicit Continuous-Model Discretization Design

## Intended outcome

Provide an executable, separate continuous-model intake path and a public C++ adapter that produces ordinary affine discrete transitions on an authored physical-time grid. A caller can inspect exactly which continuous coefficients, hold convention and numerical method produced each transition. Existing `csl.scenario/1` inputs remain discrete and continue to use their matrices directly.

## Boundary and representation

`model::ContinuousAffineModel` owns dimensions, a finite strictly increasing vector of physical state times, a zero-order hold declaration for both control and external input, and either one constant affine coefficient record or one pair of endpoint records per interval. A pair denotes coefficients linearly interpolated in physical time *inside that interval*; discontinuities between interval endpoints are permitted and explicit. Each record has A(n,n), B(n,m), E(n,p) and a(n). There is no mass matrix or nonlinear callback in this type. Invalid dimensions, providers, coefficients, grids or options fail before any discrete result is published.

`schemas/model/continuous-v1.schema.json` and `input::load_continuous_model` define a distinct `csl.continuous-model/1` document. It has `kind: continuous_lti` or `continuous_piecewise_linear_ltv`, explicit `times`, `dimensions`, `hold: zero_order_hold`, and `integration` tolerances/step budget. The strict native loader binds raw source bytes and rejects unknown fields, duplicate keys, malformed shapes, nonfinite numbers, quota overflow and discrete/descriptor/nonlinear kinds. This document is a model input, not an executable optimization scenario. `csl.scenario/1` continues to reject its reserved continuous kinds, avoiding an implicit reinterpretation of v1 problem identity.

`model::discretize` returns an owning `DiscretizedModel` containing a `SystemModel` with `TimeDomain::discrete`, the same physical grid, and one explicit `LinearStage` per interval. Its receipt declares source time domain, coefficient variation, hold convention, RK4 step-doubling method, requested absolute/relative local tolerances, accepted/rejected steps and observed maximum local difference estimate per interval. The estimate is a numerical diagnostic, **not** a certified global bound or validated enclosure. Downstream solvers operate on the resulting approximate discrete model, not on the original continuous dynamics. The adapter never silently routes a continuous `SystemModel` through `model::snapshot`.

## Numerical operation

For `x'=A(t)x+B(t)u+E(t)w+a(t)`, with u and w held constant over each authored interval, integrate the augmented transition map `Y=[Phi,Gamma_u,Gamma_w,g]` from `[I,0,0,0]`. The derivative is `Y'=A(t)Y+[0,B(t),E(t),a(t)]`. This yields `x_(k+1)=Phi*x_k+Gamma_u*u_k+Gamma_w*w_k+g`. A constant coefficient record is used for every interval without replicating authored data. RK4 step doubling compares one full step with two half steps; the accepted two-half-step result is used. The difference divided by 15 is recorded as a local estimate and scaled by `atol+rtol*max(|old|,|new|)` for step acceptance. Finite checks, a positive step budget, time-progress checks and cancellation prevent nonfinite or stalled results from publishing a transition.

## Evidence and delivery

Independent literal LTI zero-order-hold checks include a 2D double integrator, zero A with affine forcing, unequal physical step lengths and a singular A. LTV checks use analytic scalar references: `A(t)=t` gives `Phi=exp((t_1²-t_0²)/2)`, while `B(t)=t` with A=0 gives `Gamma_u=(t_1²-t_0²)/2`; an independently evaluated two-stage trajectory checks interval order. Malformed time grids, shapes, unknown kinds, unsupported descriptor/nonlinear inputs, tight step budgets, overflow and cancellation must refuse. Add an installed `find_package(CSL CONFIG)` client.

The public API and schema require a package-impact note in the PR. A saved versioned Pages report supplies a complete small 2D example, labelled state/control plot, raw inputs and observations, independent analytic oracle, frozen source receipt, and offline ZIP. If timings are shown, they are descriptive single-adapter measurements with exact interval scope and no speedup claim. Independent specification, standards and scientific reviews plus exact-head CI and live-byte Pages checks gate issue closure.

## Alternatives considered

- Extending `csl.scenario/1` to interpret reserved continuous kinds would change its closed grammar and let a nominal discrete problem appear to represent the original continuous plant. A separate schema and explicit adapter preserve the current problem identity contract.
- Exact augmented matrix exponential handles constant LTI intervals but needs a separate robust matrix-exponential implementation and still leaves genuinely varying LTV coefficients. The one adaptive integrator supports both declared coefficient classes with one receipt. It makes no exact-discretization or certified-error claim.
- Treating LTV records as piecewise constant would avoid within-interval integration and fail the intended varying-coefficient reference cases. Endpoint interpolation is an explicit, testable class rather than an inferred behavior.

## References

- [SciPy `solve_ivp` documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html) describes local tolerance scaling for adaptive Runge–Kutta integration; it does not make this implementation's local estimate a global bound.
- The LTI and LTV test oracles above are analytic integrations of the declared affine ODE. Their formulas, inputs and literal expected outputs will be recorded with the tests and report.
