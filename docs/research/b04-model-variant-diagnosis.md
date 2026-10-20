# B04 model variants and the published terminal row

Date: 2026-10-21. Status: exact-arithmetic diagnosis of two published transcriptions of the B04 scenario. **No reproduction claim.** No published value is replaced, no private source is read or executed, no optimizer is run and no historical timing is measured. The [historical scenario manifest](../../benchmarks/scenarios/b04-historical.json) stays non-executable.

## Question

The [B04 restoration audit](b04-restoration.md) records an exact contradiction: the printed L11 model requires the stock invariant `12*x2(16) + 17*x4(16) = -2122.7`, while the published terminal point gives `-406.201`, and the printed model's unrestricted terminal-plane objective minimum is `160.880653946`, far above the published `30.899`. The [parameter cross-check](b04-parameter-crosswalk.md) adds that the printed input matrix is not the input slope of the printed nonlinear law, that the printed initial flows are not that law's flows at the printed mixture perturbation, and that a separate archived variant (A39/A01/A40) is internally consistent with the same law.

The cross-check deliberately stopped short of a verdict: *"That difference alone is expected to be possible under linearization and is not a source contradiction."* That caution is correct for the initial flows alone. It cannot survive a stronger test, because the terminal plane of a linear model is an exact property, not an approximation error.

This note performs that test: **which of the two published transcriptions of the scenario can contain the published terminal point at all, inside the printed rounding?**

## Sources

Both inputs are public transcriptions already in this repository.

| Variant | Contents | Source |
|---|---|---|
| `printed-l11` | `A = I + N`, `N[1,0] = N[3,2] = -6.25`; `B = (17, 0, -12, 0)`; `x0 = (1216.904, 119500, 438.787, 45300)`; 16 transitions of `25/4` s | L11 printed equations (1.4)-(1.6) and Table 1, transcribed in the historical manifest |
| `saved-a39-a01-a40` | the same `A` and horizon; `B = (2208/110, 0, -1152/110, 0)`; `x0 = (1220.28265395983, 119500, 440.005764648976, 45300)` | A39 saved state, A01 driver input matrix, A40 nonlinear kernel, curated in the [saved-witness record](evidence/b04-saved-witnesses.json) |

The published row under test is the printed terminal state `(1200.7, -22.929, 450.2, -7.709)` with objective `30.899` and the printed criterion `sqrt((1200-x1)^2 + x2^2 + (64/9)(450-x3)^2 + (64/9)x4^2 + (x2-(8/3)x4)^2)`.

## Method

The four coordinates are (oxidizer flow, oxidizer working stock, fuel flow, fuel working stock). `A = I + N` with `N^2 = 0`, so `A^16 = I + 16N` and the terminal map has rank two:

```text
x(16) = b + B*s + N*B*m,   b = A^16*x0,   s = sum(u_k),   m = sum((15-k)*u_k)
```

`B` and `N*B` are independent, so the reachable terminal set is a plane. For an input matrix with flow rows `(B1, 0, B3, 0)` the weight pair `(w1, w3)` with `w1*B1 + w3*B3 = 0` annihilates the control direction and, because the stock rows integrate the previous flows, also the stock direction. Both functionals are therefore control invariant:

```text
w1*x1(16) + w3*x3(16) = w1*x1(0) + w3*x3(0)
w1*x2(16) + w3*x4(16) = w1*(x2(0) - 100*x1(0)) + w3*(x4(0) - 100*x3(0))
```

The published point carries one decimal on the flows and three decimals on the stocks, so the rounding radii of the two functionals are `(|w1| + |w3|)*0.05` and `(|w1| + |w3|)*0.0005`. The comparison is exact rational arithmetic; no tolerance is chosen after the fact.

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

### 1. The two input matrices are not both the law's input slope

The reference input slope of the law at `d = 0` is `c1 * d(flow)/dd`:

| Variant | Oxidizer slope | Fuel slope | Equals its own `B`? |
|---|---:|---:|---|
| printed law, printed `B` | `1014/55` = 18.436364 | `-2439/220` = -11.086364 | no: `17` and `-12` |
| scaled law (`c2 = -6700, c3 = 9000`) | `1104/55` = 20.072727 | `-576/55` = -10.472727 | yes, exactly: `B = (1104/55, 0, -576/55, 0)` |

The scaled coefficients of the A40 kernel are exactly four times the printed Table 1 values, and with them the kernel's input matrix is *exactly* the law's input slope.

### 2. The two initial states are not both the law's flows

At `d = dK = 8/75` (`u = 0`) the law gives:

| Law | Oxidizer flow | Fuel flow | Matches `printed-l11` `x0`? | Matches `saved-a39-a01-a40` `x0`? |
|---|---:|---:|---|---|
| printed `c2, c3` | 1218.753328 | 439.454325 | no: -1.849893, -0.667028 | no |
| scaled `c2, c3` | 1220.282654 | 440.005765 | no: -3.379262, -1.218482 | yes, within 1e-6 |

The printed initial state is a third quantity: it is not the printed law's flows and not the scaled law's flows. The saved initial state is the scaled law's flows at the printed mixture perturbation. Both initial states carry the mixture ratio `K + dK = 208/75` exactly.

### 3. The mixture sensitivity separates the two input matrices

The throttle acts on the mixture ratio, and the article prints that sensitivity as `c1 = 8/75`. The exact sensitivity of the state mixture `x1/x3` at the nominal flows `(1200, 450)` is

| Variant | `d(x1/x3)/du` | Equals the printed `c1`? |
|---|---:|---|
| printed `B = (17, -12)` | `49/450` = 0.108889 | no |
| saved `B = (1104/55, -576/55)` | `8/75` = 0.106667 | yes, exactly |

The saved input matrix therefore reproduces the article's own throttle sensitivity, and the printed one does not. This is a third independent identity in favour of the saved variant, and it is independent of the nonlinear law's coefficients.

### 4. The terminal plane separates the two transcriptions, decisively

| Variant | Plane weights | Flow-plane residual (radius) | Stock-plane residual (radius) | Contains the published point? |
|---|---|---|---|---|
| `printed-l11` | `(12, 17)` | `-0.427` (`<= 1.45`) | `1716.499` (`> 0.0145`) | **no** |
| `saved-a39-a01-a40` | `(12, 23)` | `-0.524434` (`<= 1.75`) | `-0.011556` (`<= 0.0175`) | **yes** |

The published terminal point lies on the saved variant's terminal plane inside the printed rounding, with a stock-plane residual of `-0.011556` against a rounding radius of `0.0175`, and it is excluded by the printed variant's stock plane by `1716.499` against a rounding radius of `0.0145`. Rounding of the published coordinates cannot bridge that gap: the largest possible effect of rounding the two stock coordinates is `0.0145`.

This test cannot be explained by linearization error, because the terminal plane of a linear model is exact. Together with sections 1-3 it localizes the defect: the printed `B` (and with it the printed `x0`) is not the model that produced the published row.

### 5. The printed criterion is intact

At the published terminal point the printed criterion gives the exact squared value `477371121/500000`, that is `30.898903573`, which is inside the three-decimal rounding interval `[30.8985, 30.8995]` of the published `30.899`. The criterion is therefore consistent with the published row; the model constants, not the objective, are what fail.

The physical reading of the criterion matches the archive owner's account of the device: the first and third terms are the oxidizer and fuel flow deviations from their nominal values, the second and fourth are the remaining working stocks, and the fifth is the non-synchronicity of the two components with the printed mixture coefficient `8/3 = 1200/450`.

### 6. The mixture band reconciles the throttle, the phase box and the initial error

`dK = 8/75` is exactly `1/25` of the nominal `K = 8/3`, that is `4.0%` of the nominal mixture ratio, and it is also `0.106667` in absolute mixture units. With `c1 = 8/75` and `u` in the owner's declared unit interval `[-1, 1]`, the reachable band of the mixture offset is `d in [0, 16/75]`. The printed phase box of the flow rows `1176 <= x1 <= 1224`, `432 <= x3 <= 468` implies the mixture faces `K + 1/6` (upper) and `K - 2/13` (lower). The reachable band therefore exceeds the upper face, so the phase constraint is active on the upper side, while the lower face is not reachable.

This is the reading that makes the owner's recollection of "about ten percent" and "about sixteen percent" consistent: `8/75` is the throttle's authority in absolute mixture units, `1/6` is the phase box's upper face in the same units, and the printed `7%` of L13 is a different paper's constant (see below).

## What this establishes, and what it does not

Established, in exact arithmetic on public transcriptions:

- The saved variant's input matrix, initial state and mixture sensitivity are each exactly consistent with the article's own nonlinear law and with the published `c1`, while the printed input matrix and printed initial state are not.
- The published terminal row is inside the saved variant's terminal plane and outside the printed variant's terminal plane, with margins that rounding cannot bridge.
- The printed terminal criterion evaluates to the published objective.

Not established:

- That the saved variant is the historical generator of the published row. It is the simplest reading consistent with three independent exact identities, but a third variant with the same plane weights `(12, 23)` and the same initial-state combination would fit the same test.
- That the published row is optimal. The check tests membership of the terminal plane, not optimality; no constrained optimum was computed, and the unrestricted terminal-plane minimum of the printed model (`160.880653946`, [b04-consistency.json](b04-consistency.json)) remains the printed model's own lower bound.
- Anything about the canonical `U` rows, the first-action convention, the stagewise control domain or the nonlinear replay. The saved histories remain scoped evidence, not a canonical run.
- Nothing is repaired. The printed `x0`, `B`, `c2`, `c3`, the published `30.899` and the four nonlinear table rows keep their historical labels.

## Related finding: where the "7%" constraint lives

The "7%" of the owner's message is **not** in L11. In the supplied corpus the figure appears once, in L13 (B09, the third stage of «Союз-2-1б»), model example, PDF p. 11: *"запрещается отклонять коэффициент соотношения массовых расходов компонентов топлива больше чем на 7% от номинального значения K (ограничение (11))"*. The formula itself is an image in that PDF and is not recoverable from the text layer. L11 instead states the engine no-failure requirement in words around its phase constraint (1.7) and the interval condition (1.8), without a numeric mixture bound; L10 (B07) also refers to an engine no-failure condition without a numeric bound in the text layer.

That makes the reading decisive for L13's own consistency: L13's Table 1 (PDF p. 11) has `K = 2.5`, `dK = -0.075`, `c1 = 0.01` and a nine-position throttle catalogue. If the bound is `7%` in absolute mixture units, the initial state violates the article's own safety constraint by `0.005`; if it is `7%` of `K`, that is `0.175` and nothing is violated. The two readings differ by a factor of `K`, and the archive's own numbers cannot separate them without the formula image. The owner's instruction that the `7%` figure is erroneous is recorded; the corrected value and the affected cases remain an open owner decision, and no L13 constraint is used in this note.

## Owner direction recorded during the input-recovery review

Recorded from the review of [#521](https://github.com/butahlecoq/controlled-systems-lab/issues/521) on 2026-10-20 and 2026-10-21, for the disposition sheet of that issue:

1. Articles are authoritative for the problem statement, the input data, the constants and the matrices. Their published numerical results are not authoritative; they are claims to be recomputed and possibly refuted.
2. A handover is a signed problem specification, not a file dump. The research group may reconstruct a specification from the article alone, recording its assumptions; the owner's signature is needed only where the article is ambiguous.
3. Where a published result is arithmetically impossible from the published data, the historical row is retained unchanged and the case continues on a corrected track under a new identifier. For B04 this means the printed L11 model is treated as a damaged transcription and the A39/A01/A40 variant is the candidate canonical model, pending the verification run below.
4. The control input is normalized to `[-1, 1]`. The archive corroborates it for the saved-run family. The working stocks carry no nonnegativity constraint, because the published terminal state has negative stocks (`x2 = -22.929`, `x4 = -7.709`) and a nonnegativity constraint would exclude the published row itself.

Open owner decisions carried by this note: the authorization and acceptance criteria for the B04 corrected-track verification run; the scope of the unit control interval (the rocket-engine family only, and how L05's printed `|u| <= 0.3` and the B06/B07 disturbance sets are treated); the evidence standard for selecting a source variant; and the L13 "7%" bound.

## Follow-up: the verification run that would settle the model choice

The diagnosis is falsifiable with one computation, which needs the owner's authorization because it is a research run on a scenario, not a documentation check:

- **Reachability.** Does a control sequence in `[-1, 1]^16` exist that satisfies the printed phase box on stages 0-16 and reaches the published terminal point within the printed rounding?
- **Optimality.** What is `min Phi(x(16))` under the same constraints? Compare with the published `30.899` under the acceptance bands fixed before the run: `|J* - 30.899| <= 0.0005` confirms the diagnosis, `J* < 30.8985` means the published row is not optimal for this constraint set, and `J* > 30.8995` means the published row is unreachable and the diagnosis is refuted.

The result would be recorded as a corrected-track B04 identifier with our own optimum as the result, and the published `30.899` as immutable context.

## Reproduce

```sh
python -B docs/research/tools/check_b04_model_variants.py
python -B -O -m unittest docs.research.tools.test_b04_model_variants -v
python -B docs/research/tools/check_b04_model_variants.py --verify-record docs/research/evidence/b04-model-variants.json
```

All three commands use only public transcriptions and the Python standard library. They do not read a private original, execute archived code, run a solver or measure a time. The checks are literal comparisons of exact rational values; they are not a proof of historical generator identity and not a constrained-optimality certificate.
