# Exact linear infeasibility evidence

`LinearInfeasibilityCertificate` records four nonnegative multiplier vectors for one immutable `LinearProgram`: lower and upper row endpoints, then lower and upper variable endpoints. A multiplier for an absent endpoint must be exactly zero. The certificate identity must equal the LP's `ProgramIdentity`.

The solver-independent verifier interprets each finite binary64 coefficient, bound, and multiplier as its exact dyadic rational value. It accepts only when every coordinate satisfies

```text
Aᵀ(row_upper - row_lower) + variable_upper - variable_lower = 0
```

and the exact constant

```text
Σ(row_lower * row_lower_bound - row_upper * row_upper_bound
  + variable_lower * variable_lower_bound - variable_upper * variable_upper_bound)
```

is strictly positive. The verifier uses integer significands and exact accumulation; it applies no numerical tolerance. Subnormal values therefore remain meaningful, and cancellation cannot turn a nonzero residual into zero. It rejects malformed dimensions, nonfinite or negative multipliers, nonzero absent-endpoint multipliers, identity mismatches, nonzero exact stationarity, and nonpositive contradiction constants.

Successful verification returns sealed `ExactFarkasEvidence`. The evidence contains the immutable raw certificate and its program identity; callers can copy or inspect it but cannot construct it directly. `check_program_result` re-verifies it against the exact LP supplied to that check. This exact evidence supports only an `infeasible` outcome. It does not support objective bounds, optimality, feasibility of a candidate, or family completeness.

At the synthesis boundary, validation additionally requires the evidence's embedded `ProgramIdentity.problem` to match the source problem ID and the outcome to be `infeasible`. The Farkas verifier itself establishes only that its supplied generated LP is infeasible. A strategy must separately justify that infeasibility transfers to its source problem before attaching the evidence to a source-level result.

Run-statistics JSON writes the raw certificate for auditability. Decoding cannot recreate sealed evidence without the immutable LP needed for re-verification, so decoded exact-Farkas support is downgraded to an unchecked `CertificateReference` containing the serialized proof payload.
