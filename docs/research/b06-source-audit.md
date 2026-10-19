# B06 primary-source control-sequence audit

Date: 2026-10-19. This audit resolves an OCR ambiguity in the displayed B06 linear minimax control sequence by visual inspection of the registered primary scan. It does not reproduce the linear minimax calculation or the nonlinear simulation.

## Source and reading

L09 is registered in the [source inventory](inventory.json) with SHA-256 `bb32b230e600fd0871322768dbf42d181fa7a0a288b97c717659a6448e3b72aa` (638,778 bytes). The local source matched that hash. Physical PDF pp. 10-12 were inspected visually for the generic disturbance notation, B06 numerical data, reported controls, and nonlinear terminal result.

## Disturbance domain in the numerical example

The general minimax formulation on physical PDF p. 10 writes the disturbance history as `w(·) ∈ W(0,T)`. This defines a symbol for the admissible history set but does not give its values. In the B06 numerical setup on physical PDF p. 11, the article says `w(t) ∈ R²` and prints

```text
D(t) = [[0.05, 0], [0, 0], [0, -0.04], [0, 0]],  t = 0,…,4.
```

It supplies no numerical bounds, vertices, or other set description for `W(t)` on the inspected numerical page. The matrix `D(t)` maps disturbance coordinates into the state; it does not constrain those coordinates. Therefore the printed data identify the disturbance channel but do not define the uncertainty set needed to compute a worst-case value. The reported plan count of 3125 enumerates the five control actions over five stages and does not determine the disturbance set.

The page defines the available actions as `{1, 0.3, 0, -0.3, -1}` and indexes the five controls by `t = 0, …, 4`. It prints the unique reported linear minimax program sequence as

```text
u^e(·) = {u^e(t)}_{t=0}^4 = {-0.3, 1, 0, 0, 0.3}.
```

Thus the first sign is negative and the final action is positive `0.3`. The extracted text's displaced minus signs should not be used to infer a different sequence.

On physical PDF p. 12, L09 states that the found program minimax control `u^e(·)` is applied to the original nonlinear system and gives terminal state `(30, 6.0345, 20, 4.4731)` and criterion `9.049`. This links the displayed linear sequence to the source-reported nonlinear row. It is a reported input association, not an independent reproduction of the nonlinear simulation.

## Printed objective check

For the B06 criterion printed on p. 11, exact rational evaluation at the p. 12 nonlinear terminal coordinates gives squared value `16378084179/200000000` (`81.890420895`). This lies inside the square of the nearest-thousandth interval for the reported `9.049`, namely `[9.0485², 9.0495²)`. The criterion at the rounded Table 2 coordinates `(30, 6.03, 20, 4.47)` has squared center `1635471/20000`; that center alone does not round to `9.049`, but the more precise state printed in the preceding text does. Exact calculations are saved in [B06 reported-cost evidence](evidence/b06-reported-rounding.json) and can be regenerated with the [checker](tools/check_b06_reported_rounding.py).

The linear Table 2 row's displayed center `(29.83, 6.73, 19.87, 5)` has exact squared criterion `4088109/40000`. Its square lies inside the square of the nearest-hundredth interval for `10.11`, `[10.105², 10.115²)`. These are center evaluations of displayed coordinates; they do not identify unrounded states or independently validate worst-case optimization.

## Remaining inputs

The linear finite-action minimax result described on p. 11 reports criterion `10.11`. Table 2 on physical PDF p. 16 (printed p. 6) gives a rounded nonlinear row `(30, 6.03, 20, 4.47)` and criterion `9.049`; the higher-precision nonlinear state is printed in the p. 12 prose above.

The reported worst-case result therefore remains non-reproducible from the transcribed inputs. The audit resolves the sequence's printed sign/order and its stated use for the nonlinear result, checks the printed objective values at their displayed centers, and records the exact boundary of the disturbance data on the source pages. It does not supply missing disturbance data, a historical run configuration, or independent validation of either reported optimization/simulation.
