# B04 nonlinear parameters and linear input cross-check

Date: 2026-10-19. Scope: exact arithmetic on the decimals and rational values printed in the [publisher's B04 article](https://sciencejournals.ru/view-article/?a=TeorSist1902009Kalev&j=teorsist&n=1&v=0&y=2019), equations (1.1), (1.3)–(1.6), Table 1 and the numerical example. The [historical scenario](../../benchmarks/scenarios/b04-historical.json) remains an unchanged, non-executable transcription. This check does not identify its generating project or reproduce its optimizer.

## Source identities and calculation

The printed nonlinear law uses `P=528000`, `I=320`, `K=8/3`, initial mixture perturbation `dK=8/75`, and `c1=8/75`, `c2=-1675`, `c3=2250`, `c4=-15`, `c5=-12`. Let `d=dK+c1*u`. With the article's equation (1.1), the fuel and oxidizer flows are

```text
N(d) = P + c2*d^2 + c3*d
J(d) = I + c4*d^2 + c5*d
fuel(d) = N(d) / (J(d)*(1+K+d))
oxidizer(d) = (K+d)*fuel(d)
```

The [standard-library checker](tools/check_b04_parameter_crosswalk.py) evaluates these rational functions and their analytic first derivatives using `Fraction`, reading the printed values from the historical manifest. It cross-checks the distinct saved-run kernel against [the reviewed evidence record](evidence/b04-saved-witnesses.json): A40 `program.m`, 3,819 bytes, SHA-256 `581a91dbb1041973f9559a6cac07657279a5e3f40091f04606216be0f97bac46`, lines 2–11; A01 `ReachableSets.m`, 8,645 bytes, SHA-256 `e7010e0a830595029b9876b1511558514cec8398d2ffa290313a566ba6997558`, lines 23–34; and A39 `1st.fig`, SHA-256 `1120e70dbf3a300d1f8c9ee19d1082632c3adbb24f5ac445802954b164181f38`. The private originals are not redistributed or executed.

| Quantity | Calculation from printed parameters | Displayed linear example / separate saved run |
|---|---:|---:|
| Linear initial flow from equations (1.3)–(1.4): nominal flow + displayed `(alpha,beta)*dK` | `(90136/75, 11218/25)` ≈ `(1201.813333, 448.72)` | Displayed `(x0[1],x0[3])=(1216.904,438.787)` |
| Oxidizer flow at `u=0`, `d=dK` | `3862615640/3169317` ≈ 1218.753328 | Displayed `x0[1]=1216.904` |
| Fuel flow at `u=0`, `d=dK` | `928513375/2112878` ≈ 439.454325 | Displayed `x0[3]=438.787` |
| `c1*d(oxidizer)/dd` at reference `d=0` | `1014/55` ≈ 18.436364 | Displayed `B[1]=17` |
| `c1*d(fuel)/dd` at reference `d=0` | `-2439/220` ≈ -11.086364 | Displayed `B[3]=-12` |
| A40 kernel at `u=0`, `d=dK` | Oxidizer `3867462560/3169317` ≈ 1220.282654; fuel `464839250/1056439` ≈ 440.005765 | Agrees with A39 saved initial flows at their recorded decimal precision, **not** with the printed linear initial flows |
| A40 reference input slopes | `1104/55`, `-576/55` | Exactly match A01's `B=(2208/110,0,-1152/110,0)` |

The first table row is a **within-linear-equations mismatch**: equation (1.3) gives nominal flows `(1200,450)`, equation (1.4) initializes them as nominal plus `(alpha,beta)*dK`, and the numerical example's equation (1.6) supplies `(alpha,beta)=(17,-12)`. With the printed `dK=8/75`, the resulting `(90136/75,11218/25)` is not the displayed `x0` pair. This does not identify which printed value, convention or generating revision differs from the actual experiment.

The direct nonlinear-law `u=0` values differ from the displayed linear `x0` flows by about 1.849328 kg/s and 0.667325 kg/s. **That difference alone is expected to be possible under linearization and is not a source contradiction.** The derivative comparison is conditional: it identifies the scalar `u` in equation (1.1) with the incremental control in the linear recurrence and differentiates at the article's reference `d=0`. The article does not provide a generating control-unit map that proves this identification for its numerical run. The nonlinear initial-flow calculation uses the law's printed `dK` at `u=0` and has the same source-version caveat.

A40 uses `c2=-6700` and `c3=9000`, four times the printed Table 1 values. Its exact initial-flow and derivative matches to the separate A39/A01 variant establish consistency **within that variant**. They do not show why the article printed different coefficients or identify the historical T=16 optimizer. A01 currently has T=12. The displayed linear terminal invariant and 160.880654 unrestricted-plane lower bound in [the B04 restoration audit](b04-restoration.md) remain independent contradictions with the article's reported 30.899 result. No printed value is replaced.

## Reproduce and limits

```sh
python -B docs/research/tools/check_b04_parameter_crosswalk.py
python -B -m unittest docs.research.tools.test_b04_parameter_crosswalk
```

Both commands use the public repository's transcribed rational data and Python's standard library; they do not require or execute archive files. The calculations do not infer missing `U` rows, first-action convention, stage constraints, original unrounded coefficients, a nonlinear enclosure, a constrained optimum, or a complete optimal family. They give one more source-specific test for any proposed canonical B04 model: explain the printed nonlinear/linear initialization and input scaling before comparing numerical results. The separate archive search for a T=16 generating project remains bounded by the [prior source audit](b04-t16-source-audit.md).
