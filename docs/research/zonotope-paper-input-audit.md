# R29 zonotope example: printed inputs and reference interpretation

2026-10-16. This is a source-to-input audit for [issue #8](https://github.com/butahlecoq/controlled-systems-lab/issues/8), not a replay of the reported timing or a complete optimal-family result. The public [Shorikov–Kalev paper, R29](https://ceur-ws.org/Vol-1825/p13.pdf), pp. 107–108, is also retained privately as A21 (SHA-256 `8a70eddbd71571ea8443f92be1a799dc0ad6162fbfab902b88a931ab08981b4a`). Its editable English TeX source A22 (SHA-256 `08d20e71e9f6537982822a12b0f54d49607113628398ac2b7678a54173a30e4f`), lines 217, 248–254 and 273–334, preserves the same two printed anomalies. The [archive register](archive-selected-sources.json) identifies the private paths; this note does not redistribute them.

## What the printed example specifies

R29 p. 108 gives 16 transitions, states in `R^4`, scalar controls `u(t)` for `t=0,...,15`, and `|u(t)|<=1`. Its matrices and initial zonotope are:

```text
A = [[1, 0, 0, 0], [-6.5, 1, 0, 0], [0, 0, 1, 0], [0, 0, -6.5, 1]]
B = [4, 0, 2, 0]^T
c_X0 = [1150, 119600, 430, 44720]^T
G_X0 = diag(20, 500, 10, 300)
```

The paper defines a zonotope as `Z(c,G)={c+G ξ: ξ∈[-1,1]^m}` on p. 105 and proves the nominal recurrence `X(t+1)=A X(t)+B P(t)` on p. 107. It supplies no numerical terminal target or optimizer-family certificate for this example. This four-state, set-valued-initial-state reachability case is separate from [B04's displayed model](b04-restoration.md), which has different `A`, `B`, and `x0`.

## Two printed anomalies and the reference interpretation

| Location | Printed form | Source-grounded interpretation for a future reference case | Limit |
|---|---|---|---|
| R29 p. 108, Algorithm 1 phases 3–4; A22 lines 248–254 | The control image is labelled `B Z_P(t)` and its generators are `B l_i`, but its center and next-state center use `A c_2`. | R29 p. 107's derivation and the dimensions `A∈R^(4×4)`, `B∈R^(4×1)`, `c_2∈R` require `B c_2`; hence `c_(t+1)=A c_t+B c_2`, `G_(t+1)=[A G_t, B G_P]`. | This is a mathematical correction to a printed formula, not evidence that a historical executable used it. The example has `c_2=0`, so this typo alone would not change its center if dimensions were ignored. |
| R29 p. 108, example; A22 lines 273–334 | Immediately after specifying scalar `u(t)` and `B∈R^(4×1)`, the paper displays four-component `c_2=(0,0,0,0)^T` and `l_1=(1,1,1,1)^T`. | To model the stated scalar `|u|<=1`, use the one-dimensional input zonotope `P(t)=Z(0,[1])=[-1,1]`. Its state-space image is `B P(t)=Z(0,[4,0,2,0]^T)`. | The displayed four-component `l_1` cannot be multiplied by the printed `B`, and it is not the state-space image generator `B`. This interpretation reconciles dimensions and the scalar bound; authorial intent and the actual run inputs remain unverified. |

The corrected reference inputs preserve the published `A`, `B`, initial zonotope and scalar bound while recording both editorial inferences explicitly. They do not silently substitute the four-component control vector or invent a second control channel. In exact real arithmetic, the stated recurrence adds one generator per step, so an unreduced 16-step terminal zonotope has the four initial generator columns and sixteen control-image columns. This is a representation identity, not a claim about floating-point equality, vertex count, runtime, or complete trajectory recovery.

The archived A04 `Scientific Research/Zonotope.m` (SHA-256 `23b52c42f62dc9a692ccb5252debe4f927692589c88cb9517b42f84a24f0364f` in the [register](archive-selected-sources.json)) has commented four-state fuel matrices, but its active example instead uses a three-state matrix, a `3×2` input matrix and five steps; it also includes optional generator reduction and plotting. It is not a runnable source match for the R29 16-step case. The source audit therefore stops at a candidate reference-input contract: an independent exact/validated operation check, saved run provenance and a report are still needed before a corrected numerical baseline can be published. A complete joint optimal state/control family additionally needs an objective, history-preserving relation and verified coverage under the [architecture contract](../architecture/modular-algorithms-and-solution-sets.md#optimal-solution-families).
