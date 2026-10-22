# L13 mixture-bound recovery

Status: owner disposition recorded on 2026-10-22. This resolves the bound
interpretation tracked by [issue #532](https://github.com/butahlecoq/controlled-systems-lab/issues/532); it does not recover the historical program or authorize a research run.

## Source and owner disposition

The owner checked the identified L13 source, `papers/Электронная версия_статьи.pdf`, SHA-256
`4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e`, and recorded the transcription and signed decision in [issue comment 6334291909](https://github.com/butahlecoq/controlled-systems-lab/issues/532#issuecomment-6334291909). The source PDF is private and is not copied into this repository.

- PDF p. 5 (printed p. 133), Eq. (11), gives the general state constraint `x(t) ∈ X₁(t) ⊂ ℝ⁴`, `t ∈ 0..T`, where `X₁(t)` is a polyhedron. The equation is typeset, not an image; it does not itself state a numeric mixture limit.
- PDF p. 11 (printed p. 139) says the mixture-ratio coefficient must not deviate from nominal `K` by more than 7% and identifies this as constraint (11).
- PDF p. 12 (printed p. 140) instantiates the state polyhedron as
  `X₁(t) = {57.5 ≤ x₁ ≤ 62.5, −30 ≤ x₂ ≤ 20000, 23 ≤ x₃ ≤ 25, −30 ≤ x₄ ≤ 8000}`.
  It also lists `U₁ = {1, 0.75, 0.5, 0.25, 0, −0.25, −0.5, −0.75, −1}`,
  `V₁ = {|v₁| ≤ 0.06, |v₂| ≤ 0.06}`, and the initial state
  `x(0) = (59.134, 18100, 24.385, 7150)ᵀ`.

The owner decision is that the 7% is relative to nominal `K`: for `K = 2.5`,
`|Kₘ − K| ≤ 0.07K = 0.175`. The state box is the operative numerical constraint;
the bound is not applied directly to the control. This supersedes the earlier
owner statement that the printed 7% was erroneous.

## Numerical check

The owner records `ΔK = −0.075`, `c₁ = 0.01`, `c₀ = 10`, and the mixture relation
`Kₘ = K + ΔK + c₁c₀ Σu = 2.5 − 0.075 + 0.1 Σu`. Therefore:

```text
|−0.075 + 0.1 Σu| ≤ 0.175
−1 ≤ Σu ≤ 2.5
```

The article prints the third row of `B` as `−0.534` and the initial flow as
`x₃(0)=24.385`. For the nominal calculation (`v=0`), the displayed dynamics
are `x₁ = 59.134 + 1.064 Σu` and `x₃ = 24.385 − 0.534 Σu`; endpoints from
literal printed decimals are:

| Quantity | `Σu = −1` | `Σu = 2.5` | Printed interval |
| --- | ---: | ---: | ---: |
| `x₁` | `58.070` | `61.794` | `[57.5, 62.5]` |
| `x₃` | `24.919` | `23.050` | `[23, 25]` |

The owner comment gives `x₃ = 23.051` at the second endpoint, but this is an
arithmetic error for the source's displayed coefficient:
`24.385 − 0.534·2.5 = 23.050`. The publication supplies the coefficient only
to three decimals; it does not establish an unrounded coefficient that would
produce `23.051`. The printed-box verdict remains clear: `23.050 ≥ 23`, with
`0.050` margin at that endpoint. At `Σu=−1`, the displayed calculation gives
`24.919` as stated by the owner.

Conversely, applying the printed state box to the nominal displayed `x₃`
dynamics gives `Σu ∈ [−1.151685…, 2.593633…]`, rounded to `[-1.152, 2.594]`.
Substitution in `Kₘ` yields deviations of approximately `−7.61%` and `+7.37%`
of `K`. These continuous nominal endpoints do not equal the stated 7% band.
The source also specifies a discrete control catalogue and a bounded model-error
input: the third state row of `D` contributes `−v₂`, with `|v₂| ≤ 0.06` at
each stage. Therefore this nominal endpoint check does not prove equivalence
between the 7% statement and the state box for arbitrary disturbed trajectories.
The box remains the source's operative numeric state constraint; any robust
implementation must account for the model-error terms separately. The `x₁`
interval is wider and does not tighten this nominal mixture check.

For the printed initial state, `59.134 / 24.385 = 2.425015…`, so the initial deviation from `K`
is `−0.074985…`, or `−2.999%` of `K`. It satisfies the relative bound with
`0.100015…` margin. The rejected absolute interpretation
`|Kₘ − K| ≤ 0.07` would exclude it by `0.004985…` (about `0.005`).

## Repository use and limits

The owner reports no scenario, check, or result record using these L13 bounds.
The repository search for L13/B09 numeric bounds found the older research notes
that discussed the ambiguity, but no benchmark scenario, test fixture, or
algorithm report record that applies them. L13's own Table 1 is the admissibility
check recorded above, and it satisfies the owner-selected relative bound.

No published value is changed; the article's printed 7% retains its historical
label. The state box is recorded as the printed operative constraint, and the
conversion to it remains an owner-documented derivation because the article does
not print that conversion rule. This finding does not identify the source code
that generated Table 2, reproduce its results, or resolve the broader B09
historical input and criterion questions in [the missing-input dossier](missing-inputs.md).
