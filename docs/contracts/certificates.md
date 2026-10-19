# Certificate verification contract

## Supported validated claim

The current validated certificate profile supports exactly one mathematical
claim: infeasibility of an immutable linear program. The certificate is a
Farkas multiplier tuple over the LP's row and variable lower and upper bounds.
Its `ProgramIdentity` binds both the source problem and the particular
generated program. Multipliers for absent endpoints must be zero.

The verifier treats every finite binary64 LP coefficient, bound, and
multiplier as its exact dyadic rational value. It checks nonnegative
multipliers, exact stationarity, and a strictly positive exact contradiction
constant using integer arithmetic. It performs no floating-point tolerance or
rounded summation. The arithmetic proves a statement about those stored binary64
values; it does not by itself prove that they are an exact transcription of a
physical model or account for model error.

For row and variable lower/upper multipliers `l` and `u`, the verifier checks
the exact stationarity identity

```text
Aᵀ(row_upper - row_lower) + variable_upper - variable_lower = 0
```

and requires this exact contradiction constant to be positive:

```text
Σ(row_lower * row_lower_bound - row_upper * row_upper_bound
  + variable_lower * variable_lower_bound - variable_upper * variable_upper_bound)
```

`ExactFarkasEvidence` is sealed: only successful verification constructs it.
The LP result boundary rechecks it against the exact immutable LP and accepts it
only for an `infeasible` outcome. This certifies the generated LP only. The
synthesis boundary rejects generated-LP evidence as a source-level infeasibility
claim, even when its embedded problem ID matches: no checked source-to-generated
transfer certificate currently exists. Source-level validated infeasibility is
therefore unsupported by this profile; synthesis leaves its source claim's
support unestablished rather than attaching generated-program evidence.

## Claim scope and unsupported requests

Validated assurance is claim-specific. The current profile does not certify
feasibility of a candidate, objective bounds, optimality, set inclusion,
trajectory feasibility, family completeness, or model-error enclosures. The
existence of an exact infeasibility certificate cannot be promoted to any of
these claims. A validated request that needs an unsupported claim must return
an explicit unsupported diagnostic; numerical results and unchecked
certificate references remain non-validated evidence.

In particular, a validated optimal-family request is unsupported even when a
backend returns a family. Feasibility, optimality, and completeness remain
separate evidence fields. A witness or complete-family label does not extend
the Farkas verifier's scope.

## Rejection conditions and reference cases

The verifier rejects a mismatched program identity, wrong multiplier shape,
negative or nonfinite multipliers, nonzero multipliers for absent endpoints,
nonzero exact stationarity, and a zero or negative contradiction constant.
Exact cancellation, subnormal contradiction constants, and zero-dimensional
LPs are covered by the reference tests in
`tests/unit/optimization/linear_infeasibility_certificate_tests.cpp`. The
contract is limited to infeasibility of the represented LP; no certificate
here encloses rounding or uncertainty introduced before LP construction.
