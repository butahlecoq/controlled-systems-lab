# B04 model variants and the published terminal row

Date: 2026-10-21. Evidence variant: `b04-model-variant-diagnosis-v1`. Scope: exact-arithmetic diagnosis of two published transcriptions of the B04 scenario. **No reproduction claim.** No published value is replaced, no private source is read or executed, no optimizer is run and no historical timing is measured. The [historical scenario manifest](../../benchmarks/scenarios/b04-historical.json) stays non-executable and keeps its recorded execution gate.

## Question

The [B04 restoration audit](b04-restoration.md) records an exact contradiction: the printed L11 model requires the stock invariant `12*x2(16) + 17*x4(16) = -2122.7`, while the published terminal point gives `-406.201`, and the printed model's unrestricted terminal-plane objective minimum is `160.880653946`, far above the published `30.899`. The [parameter cross-check](b04-parameter-crosswalk.md) adds that the printed input matrix is not the input slope of the printed nonlinear law, that the printed initial flows are not that law's flows at the printed mixture perturbation, and that a separate archived variant (A39/A01/A40) is internally consistent with the same law.

The cross-check deliberately stopped short of a verdict: *"That difference alone is expected to be possible under linearization and is not a source contradiction."* That caution is correct for the initial flows alone. It cannot survive a stronger test, because the terminal plane of a linear model is an exact property, not an approximation error.

This note performs that test: **which of the two published transcriptions of the scenario can contain the published terminal point at all, inside the printed rounding?**

## Sources

Both inputs are public transcriptions already in this repository. The printed model comes from the hash-identified article L11 (SHA-256 `e04c2f16…ce147`, PDF pp. 12-14) and the published counterpart R40; the saved-run variant comes from A01, A39, A40 and A41, whose identities are recorded in the [saved-witness record](evidence/b04-saved-witnesses.json) and repeated in the derived record of this note.

| Variant | Contents | Source |
|---|---|---|
| `printed-l11` | `A = I + N`, `N[1,0] = N[3,2] = -25/4`; `B = (17, 0, -12, 0)`; `x0 = (1216.904, 119500, 438.787, 45300)`; 16 transitions of `25/4` s | L11 printed equations (1.4)-(1.6) and Table 1, transcribed in the historical manifest |
| `saved-a39-a01-a40` | the same `A` and horizon; `B = (2208/110, 0, -1152/110, 0)`; `x0 = (1220.28265395983, 119500, 440.005764648976, 45300)` | A39 saved state, A01 driver input matrix, A40 nonlinear kernel, curated in the [saved-witness record](evidence/b04-saved-witnesses.json) |

The published row under test is the printed terminal state `(1200.7, -22.929, 450.2, -7.709)` with objective `30.899` and the printed criterion `sqrt((1200-x1)^2 + x2^2 + (64/9)(450-x3)^2 + (64/9)x4^2 + (x2-(8/3)x4)^2)`.

## Method

The four coordinates are (oxidizer flow, oxidizer working stock, fuel flow, fuel working stock). `A = I + N` with `N^2 = 0`, so `A^16 = I + 16N` and the terminal map has rank two:

```text
x(16) = b + B*s + N*B*m,   b = A^16*x0,   s = sum(u_k),   m = sum((15-k)*u_k)
```

`B` and `N*B` are independent, so the reachable terminal set lies in an affine plane (the image of `span{B, N*B}`). For an input matrix with flow rows `(B1, 0, B3, 0)` the weight pair `(w1, w3)` with `w1*B1 + w3*B3 = 0` annihilates the control direction; because the stock rows of `N*B` are `(-25/4)` times the corresponding rows of `B` - row 2 is `(-25/4)*(B1, 0, 0, 0)` and row 4 is `(-25/4)*(0, 0, B3, 0)` - the same pair annihilates the stock direction as well. Both functionals are therefore control invariant, and they are the two annihilators of the plane's direction space, so the test is a complete membership test:

```text
w1*x1(16) + w3*x3(16) = w1*x1(0) + w3*x3(0)
w1*x2(16) + w3*x4(16) = w1*(x2(0) - 100*x1(0)) + w3*(x4(0) - 100*x3(0))
```

The published point carries one decimal on the flows and three decimals on the stocks, so the rounding radii of the two functionals are `(|w1| + |w3|)*0.05` and `(|w1| + |w3|)*0.0005`. The radii are derived from the printed decimals by the checker, not asserted here, and the comparison is exact rational arithmetic; no tolerance is chosen after the fact.

The transition structure that this argument needs - the matrix, the horizon, the stage length and the resulting 100 s window - is read from the manifest and asserted by the checker, so a change in the transcribed model cannot pass unnoticed.

The nonlinear law is used as printed in equation (1.1) with `P = 528000`, `I = 320`, `K = 8/3`, `dK = 8/75`, `c1 = 8/75`, `c4 = -15`, `c5 = -12`:

```text
N(d) = P + c2*d^2 + c3*d
J(d) = I + c4*d^2 + c5*d
fuel(d) = N(d) / (J(d)*(1 + K + d))
oxidizer(d) = (K + d)*fuel(d)
```

with `d = dK + c1*u` and either the printed `c2 = -1675, c3 = 2250` or the kernel's scaled `c2 = -6700, c3 = 9000`.

The [checker](tools/check_b04_model_variants.py) and its [literal tests](tools/test_b04_model_variants.py) use the Python standard library only. The derived record is [b04-model-variants.json](evidence/b04-model-variants.json).

## Results

### 1. Only one input matrix is the law's reference input slope

The reference input slope of the law at `d = 0` is `c1 * d(flow)/dd`:

| Law | Oxidizer slope | Fuel slope | Equals the printed `B`? | Equals the saved `B`? |
|---|---:|---:|---|---|
| printed `c2, c3` | `1014/55` = 18.436364 | `-2439/220` = -11.086364 | no: `17` and `-12` | no |
| scaled `c2, c3` | `1104/55` = 20.072727 | `-576/55` = -10.472727 | no | **yes, exactly** |

The scaled coefficients of the A40 kernel are exactly four times the printed Table 1 values, and with them the kernel's input matrix is *exactly* the law's reference input slope.

Two qualifications belong with this comparison, and they are inherited from the [parameter cross-check](b04-parameter-crosswalk.md): it is **conditional** on identifying the scalar `u` of equation (1.1) with the incremental control of the linear recurrence, and the article prints no generating control-unit map for its numerical run. The identity is exact at the law's polynomial reference `d = 0`; at the scenario's operating point `d = 8/75` the scaled law's slope is `20.5125` and `-9.5270`, that is about 2.2% (oxidizer) and 9.0% (fuel) away from `B`.

### 2. Only one initial state is the law's flows

At `d = dK = 8/75` (`u = 0`) the law gives:

| Law | Oxidizer flow | Fuel flow | Matches `printed-l11` `x0`? | Matches `saved-a39-a01-a40` `x0`? |
|---|---:|---:|---|---|
| printed `c2, c3` | 1218.7533276 | 439.4543249 | no: -1.8493276, -0.6673249 | no |
| scaled `c2, c3` | 1220.2826540 | 440.0057646 | no: -3.3786540, -1.2187646 | yes: +2.1e-12, -4.2e-13 |

The printed initial state is a third quantity: it is not the printed law's flows and not the scaled law's flows. The saved initial state is the scaled law's flows at the printed mixture perturbation, to the recorded decimal precision of the saved state, not exactly.

Both initial states sit at the printed mixture perturbation. The saved one carries the ratio `K + dK = 208/75` to within 1e-14; the printed one carries `208/75 + 3.2e-6`, because its flows are rounded to three decimals.

### 3. The mixture sensitivity separates the two input matrices

The throttle acts on the mixture ratio, and the article prints that sensitivity as `c1 = 8/75`. The exact sensitivity of the state mixture `x1/x3` at the nominal flows `(1200, 450)` is

| Variant | `d(x1/x3)/du` | Equals the printed `c1`? |
|---|---:|---|
| printed `B = (17, -12)` | `49/450` = 0.108889 | no |
| saved `B = (1104/55, -576/55)` | `8/75` = 0.106667 | yes, exactly |

This identity is independent of the flow-law coefficients `c2...c5` and of the kernel's coefficient scaling. It is, however, not independent of section 1: because the law's `d = 0` point is the nominal `(1200, 450)`, the mixture sensitivity of a linear model whose input matrix is the law's input slope is algebraically that slope's `c1`. The saved variant therefore has **two independent exact identities** (the input slope and the initial state) plus one derived consistency check, and the printed variant has neither identity.

### 4. The terminal plane separates the two transcriptions, decisively

| Variant | Plane weights | Flow-plane residual (radius) | Stock-plane residual (radius) | Contains the published point? |
|---|---|---|---|---|
| `printed-l11` | `(12, 17)` | `-0.427` (`<= 1.45`) | `1716.499` (`> 0.0145`) | **no** |
| `saved-a39-a01-a40` | `(12, 23)` | `-0.524434` (`<= 1.75`) | `-0.011556` (`<= 0.0175`) | **yes** |

The published terminal point lies on the saved variant's terminal plane inside the printed rounding, with a stock-plane residual of `-0.011556` against a rounding radius of `0.0175`, and it is excluded by the printed variant's stock plane by `1716.499` against a rounding radius of `0.0145`. Rounding of the published coordinates cannot bridge that gap: the largest possible effect of rounding the two stock coordinates is `0.0145`.

This test cannot be explained by linearization error, because the terminal plane of a linear model is exact. Together with sections 1-3 it localizes the defect in the printed constants, and the [parameter cross-check](b04-parameter-crosswalk.md) states exactly how they are mutually inconsistent: the printed `B` follows from the printed pair `(alpha, beta) = (17, -12)` through equation (1.6), but the printed `x0` does **not** follow from that same pair through equation (1.4), which gives the nominal flows plus `(alpha, beta)*dK`, that is `(90136/75, 11218/25)` against the displayed `(1216.904, 438.787)`. The printed constants are therefore not one consistent set, and at least one of them is a damaged transcription. Which one is damaged is not identified by this test.

The two verdicts are also robust to the initial states' own precision. The printed exclusion survives any plausible initial-flow error: overturning it would need more than `1.0097` kg/s of error in the initial fuel flow, while the printed `x0` carries three decimals. The saved inclusion tolerates an initial-fuel-flow error of up to `2.6e-6` kg/s, and the A39 coordinates carry fourteen digits.

### 5. The printed criterion is intact

At the published terminal point the printed criterion gives the exact squared value `477371121/500000`, that is `30.898903573`, which is inside the three-decimal rounding interval `[30.8985, 30.8995]` of the published `30.899`. The criterion is therefore consistent with the published row; the model constants, not the objective, are what fail. This is a closed-form evaluation at an already published point; it is not a solve, and it does not touch the manifest's execution gate.

The physical reading of the criterion matches the archive owner's account of the device: the first and third terms are the oxidizer and fuel flow deviations from their nominal values, the second and fourth are the remaining working stocks, and the fifth is the non-synchronicity of the two components with the printed mixture coefficient `8/3 = 1200/450`.

### 6. The mixture band, the phase box and the control interval

`dK = 8/75` is exactly `1/25` of the nominal `K = 8/3`, that is `4.0%` of the nominal mixture ratio, and it is also `0.106667` in absolute mixture units. The reachable band of the mixture offset depends on what the unit control interval applies to, and the archive uses two conventions, so both are reported:

| Convention | Reachable `d` with the control in `[-1, 1]` |
|---|---|
| the law's accumulated action, one scalar per run | `[0, 16/75]` |
| a per-step control, as in the saved variant's inferred actions | `[-8/5, 136/75]` |

The printed phase box of the flow rows `1176 <= x1 <= 1224`, `432 <= x3 <= 468` implies the mixture faces `K + 1/6` (upper) and `K - 2/13` (lower). In the **linear** model the two flows are tied by the input matrix, so the reachable flow pair is a line segment, and the exact analysis is: for the saved variant the tie line meets the `x1` faces at `x3 = 438.066` and `463.110`, both inside the `x3` box, so the binding faces are the `x1` ones and the mixture ratio along the feasible segment stays in `[2.5394, 2.7941]`, strictly inside the face range `[2.5128, 2.8333]`. The box is therefore active, but through the `x1` bounds, and neither mixture face is attained by the linear model.

The unit control interval itself is a **provisional owner recollection** recorded in the manifest (`related_noncanonical_evidence.owner_control_interval_recollection`: *"Most likely u is in [-1,1]; not an exact quotation from the numerical tables"*), and the manifest instructs that it is not imported into `B04-historical`. Everything in this section is conditional on it, and nothing in this note changes the manifest's status.

## What this establishes, and what it does not

Established, in exact arithmetic on public transcriptions:

- The saved variant's input matrix is exactly the reference input slope of the A40 kernel's scaled nonlinear law, and its initial state is that law's flows at the printed mixture perturbation to the recorded decimal precision; the printed input matrix and printed initial state are neither.
- The saved variant's mixture sensitivity is exactly the article's printed `c1`; the printed variant's is not.
- The published terminal row is inside the saved variant's terminal plane and outside the printed variant's terminal plane, with margins that neither rounding of the published row nor rounding of the transcribed initial states can bridge.
- The printed terminal criterion evaluates to the published objective.

Not established:

- That the saved variant is the historical generator of the published row. It is the simplest reading consistent with the evidence, but the terminal-plane test cannot distinguish it from a third variant with the same weight pair `(12, 23)` and the same flow-plane and stock-plane values. The repository already holds an independent corroboration in the A39 artifact - the saved nominal terminal state rounds to the published row, with the matching affine moments (see [B04 saved witnesses](b04-saved-witnesses.md)) - but the generator of that artifact is itself unresolved, and the *article's* canonical run stays unattributed.
- That the published row is optimal. The check tests membership of the terminal plane, not optimality; no constrained optimum was computed, and the unrestricted terminal-plane minimum of the printed model (`160.880653946`, [b04-consistency.json](b04-consistency.json)) remains the printed model's own lower bound.
- Anything about the canonical `U` rows, the first-action convention, the stagewise control domain, the unit control interval or the nonlinear replay. The saved histories remain scoped evidence, not a canonical run.
- Nothing is repaired. The printed `x0`, `B`, `c2`, `c3`, the published `30.899` and the four nonlinear table rows keep their historical labels, and the manifest's execution gate is unchanged.

## Related finding: L13's "7%" constraint

The earlier note below was superseded by the owner's source recheck and signed
disposition in [issue #532](https://github.com/butahlecoq/controlled-systems-lab/issues/532#issuecomment-6334291909).
The exact source transcription, owner-selected relative bound, state-box
realization, Table 1 arithmetic, repository-use search, and precision limit are
now recorded in [L13 mixture-bound recovery](l13-mixture-bound-recovery.md).
The 7% refers to `0.07K = 0.175` for nominal `K=2.5`; the printed box is the
operative numerical state constraint. The earlier claim that the equation was
an image and that the corrected value remained undecided is withdrawn. No
published value changes, and the broader B09 historical-run questions remain
open.

## Owner direction recorded during the input-recovery review

Recorded in the review thread of [#521](https://github.com/butahlecoq/controlled-systems-lab/issues/521#issuecomment-6302807092) on 2026-10-20 and 2026-10-21, for the disposition sheet of that issue, and repeated there so that the public record carries them:

1. Articles are authoritative for the problem statement, the input data, the constants and the matrices. Their published numerical results are not authoritative; they are claims to be recomputed and possibly refuted.
2. A handover is a signed problem specification, not a file dump. The research group may reconstruct a specification from the article alone, recording its assumptions; the owner's signature is needed only where the article is ambiguous.
3. The control input is normalized to `[-1, 1]`, with the archive's corroboration for the saved-run family. The same statement is recorded in the manifest as a provisional owner recollection - *"Most likely u is in [-1,1]; not an exact quotation from the numerical tables"* - and is not imported into `B04-historical`, so section 6 stays conditional on it. The working stocks carry no nonnegativity constraint, because the published terminal state has negative stocks (`x2 = -22.929`, `x4 = -7.709`) and a nonnegativity constraint would exclude the published row itself.

Open owner decisions carried by this note: the authorization and acceptance criteria for the B04 corrected-track verification run; the scope of the unit control interval (the rocket-engine family only, and how L05's printed `|u| <= 0.3` and the B06/B07 disturbance sets are treated); the evidence standard for selecting a source variant; whether the printed L11 model is to be treated as a damaged transcription and the A39/A01/A40 variant as the candidate canonical model; and the L13 "7%" bound.

## Follow-up: the verification run that would settle the model choice

The diagnosis is falsifiable with one computation, which needs the owner's authorization because it is a research run on a scenario, not a documentation check. It would run on the **saved** variant, since the printed variant cannot contain the published row at all:

- **Reachability.** Does a control sequence in `[-1, 1]^16` exist that satisfies the printed phase box on stages 0-16 and reaches the published terminal point within the printed rounding?
- **Optimality.** What is `min Phi(x(16))` under the same constraints? Compare with the published `30.899` under the acceptance bands fixed before the run: `|J* - 30.899| <= 0.0005` confirms the diagnosis, `J* < 30.8985` means the published objective is not attained or beaten under this constraint set, and `J* > 30.8995` means the published objective value cannot be attained or beaten and the diagnosis needs revision. The published *point* may still be reachable in the last case, which the reachability test would separate.

The result would be recorded as a corrected-track B04 identifier with our own optimum as the result, and the published `30.899` as immutable context.

## Reproduce

```sh
python -B docs/research/tools/check_b04_model_variants.py
python -B -O -m unittest docs.research.tools.test_b04_model_variants -v
python -B docs/research/tools/check_b04_model_variants.py --verify-record docs/research/evidence/b04-model-variants.json
```

All three commands use only public transcriptions and the Python standard library. They do not read a private original, execute archived code, run a solver or measure a time. The checks are literal comparisons of exact rational values; they are not a proof of historical generator identity and not a constrained-optimality certificate. Exit code 0 means the derived record was reproduced (or printed) as expected; a stored record that differs from the recomputed one exits non-zero.
