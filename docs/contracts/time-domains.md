# Continuous coefficients and discrete transitions

`csl::model::ContinuousAffineModel` declares the physical-time equation

```text
x'(t) = A(t)x(t) + B(t)u_k + E(t)w_k + a(t),  t in [times[k], times[k+1]]
```

`times` contains at least one finite, strictly increasing state time. `A`, `B`,
`E` and `a` are rates per physical time. The only supported hold keeps both
`u_k` and `w_k` constant throughout an interval. A `LinearStage` coefficient
provider is constant for the whole grid. A vector of `CoefficientEndpoints`
contains exactly one start/end pair per interval; each matrix and offset is
linearly interpolated within that interval. Neighboring pairs may have a jump.

`model::discretize` returns `DiscretizedModel` or a diagnostic/stop. It integrates
the augmented transition and forcing maps with adaptive RK4 step doubling,
using the accepted two-half-step result. The local difference divided by 15
guides step acceptance against positive absolute and relative tolerances. Its
per-stage maximum is an observed estimate, **not a certified global error
bound**. Cancellation, nonfinite arithmetic, unresolved binary64 time steps and
the attempt budget stop conversion without publishing a partial model.

The output `SystemModel` is tagged `TimeDomain::discrete`; its stages are
already integrated transitions for their physical intervals. `model::snapshot`
uses them directly and never scales them by `times[k+1]-times[k]`. The receipt
records source and output domains, coefficient variation, hold, method,
tolerances, local-error scope, interval times and accepted/rejected steps. The
output time grid remains the input physical grid. Singular A is supported; no
matrix inverse is used. This API does not represent descriptor mass matrices,
nonlinear dynamics, other holds or continuous observations.

The separate `csl.continuous-model/1` document can be loaded with
`input::load_continuous_model`. It retains exact input bytes and their digest.
The existing `csl.scenario/1` grammar still describes supplied **discrete**
transitions and does not silently convert continuous coefficients. Callers may
pass the explicit converted `SystemModel` and grid to `model::snapshot`.

The [2D double-integrator input](../../tests/fixtures/input/continuous-double-integrator.json)
has physical times `[0,1,3]`. Under constant control 2 on the first interval
and -1 on the second, starting at `(position, velocity)=(0,0)`, the analytic
ZOH transitions produce `(1,2)` then `(3,0)`. The
[installed client](../../tests/installed/continuous_discretization_client.cpp)
checks this trajectory through the public loader, adapter and snapshot.
