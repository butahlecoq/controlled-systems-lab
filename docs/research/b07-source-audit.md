# B07 primary-source input audit

Date: 2026-10-19. This source-bounded audit transcribes the hash-identified L10 numerical example and checks whether its displayed inputs determine the reported robust minimax result. It does not substitute a guessed disturbance set or claim to reproduce the published run.

## Source and printed scenario

L10 is registered in the [source inventory](inventory.json) with SHA-256 `146ec36e96be4c779158541420eac1e242825262b5981d47b61ba86a9e2126a8`. PDF pp. 10-13 were visually inspected. The machine-readable transcription is [B07-historical](../../benchmarks/scenarios/b07-historical.json); it is explicitly non-executable.

The numerical example gives a five-step problem over a 100-second physical interval, initial linear state `(29.31,302,20.354,207)`, and five controls `{1,0.3,0,-0.3,-1}` at each of five control indices. It reports 3125 sequences, 365 retained as satisfying the robust phase constraints, the sequence `(1,0,0.3,-0.3,0)`, and worst-case objective `9.77`.

The printed linear matrices include `B=(0.7,0,-1/3,0)^T`, a disturbance matrix with coefficients `0.05` and `-0.04`, and stock-flow entries `-10/T` in `A`. The stated terminal criterion is

```text
sqrt((30-x1)^2 + x2^2 + 2.25(20-x3)^2 + 2.25 x4^2).
```

The example prints phase restrictions `29 <= x1(t) <= 31` and `19.5 <= x3(t) <= 20.5` for stages 1 through 5. Its reported nonlinear terminal state and criterion are `(30,5.81,20,4.39)` and `8.82`; the reported worst-case linear state is `(29.78,6.43,19.82,4.87)`. Runtime is reported as 66 seconds on MATLAB R2014a and an Intel Core i7-3770 at 3.4 GHz with 8 GB RAM. The listed GPU is not evidence that the computation used it.

## Terminal objective cross-check

Evaluating the printed objective at the centers of the printed terminal states gives `9.73802983` for the linear row and `8.78170399` for the nonlinear row, rather than the respective tabulated `9.77` and `8.82`.

For the linear row, all four state coordinates are printed to two decimal places. Under the conditional assumption that they were rounded to the nearest hundredth, the exact maximum squared objective over the closed coordinate-rounding box is `7600761/80000`, giving a maximum norm of `9.74728232`. A value printed as `9.77` to the nearest hundredth has squared lower endpoint `(9.765)^2 = 3814209/40000`, which is larger. Thus ordinary two-decimal rounding of the displayed linear state cannot account for the printed linear objective.

The nonlinear row prints `x1=30` and `x3=20` without decimal places, but `x2` and `x4` to hundredths. Under nearest-to-displayed-precision rounding, allowing `±0.5` for the integer coordinates and `±0.005` for the other two gives an upper norm of `8.83672910`; the reported `8.82` is compatible with that wider box. The center calculation is a discrepancy, but the printed precision does not establish a nonlinear state/objective inconsistency.

These checks do not identify which input, state, criterion or reported value generated either row. The linear result is a display-rounding incompatibility under the stated convention, not a diagnosis of its cause.

## Inputs that prevent reproduction

Equations (8)-(9) define a known admissible disturbance set `V1(t)` and the numerical example supplies the matrix `D(t)`, but the extracted text contains no numeric bounds, vertices, or stage/inter-stage dependence for `V1(t)`. Visual inspection of the numerical pages confirms that they print `D(t)` and the output, not `V1(t)`. Without `V1(t)`, the adversarial histories used for robust feasibility and worst-case cost are not determined; the counts 365 and the value 9.77 cannot be independently recomputed from the printed data.

There is also a direct initial-stock discrepancy. Equation (5) states `M(0)=M_nominal+delta_M`. Table 1 gives nominal oxidizer and fuel masses 300 kg and 200 kg, with both offsets equal to 5 kg, implying initial stocks 305 kg and 205 kg. The numerical example separately prints the stock components of `x(0)` as 302 kg and 207 kg. This is an arithmetic comparison of the paper's own values; it does not identify which values or equation are erroneous.

The example gives five stages over 100 seconds and defines a general interval `delta_T(t)`, but does not state each interval. The printed stock-flow coefficients are `-10/T`; the text does not explain how those entries relate to `T=5`, the physical interval, or `delta_T(t)`. The numerical example also prints only flow-coordinate phase bounds, while the preceding method condition assumes bounded state polytopes; no numeric stock-coordinate bounds are given there.

## Consequence

The source supports a useful transcription of the displayed problem and several reported outputs, but not a unique executable historical scenario. Keep the historical manifest non-executable until the disturbance set, stock initialization and time discretization are reconciled with authoritative data or the generating project is recovered. Any reference that explicitly assumes a new disturbance set or repairs the initial state must have a separate scenario identity and must not be reported as a reproduction of B07.
