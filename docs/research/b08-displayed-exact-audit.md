# B08 displayed-data exact audit

Date: 2026-10-16. Evidence variant: `b08-displayed-rational-v1`. Scope: the four-step **linear fixed-plan** minimax problem formed by treating the printed decimals in L04 as exact rational inputs. This is a reference derivation for [issue #6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), not a reproduction of the historical MATLAB project or the nonlinear plant.

## Source and model boundary

L04 is the supplied `papers/Shorikov_Kalev_AиT_New.pdf`, 390884 bytes, SHA-256 `6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f` in the [source inventory](inventory.json). Its physical PDF p. 12 prints the four-step model, five actions, disturbance bounds and Euclidean terminal criterion. Page 13 prints the plan `(0.6,0.6,-0.3,0)` and cost `67.12`. The local original matched the registered raw-byte hash during this audit. Its privately held bytes are not copied here. The [source-version matrix](publication-source-matrix.md) distinguishes this article from W07's different notebook data.

In coordinate order `(oxidizer flow, oxidizer working stock, fuel flow, fuel working stock)`, the displayed linear recurrence is `x[t+1]=A x[t]+B u[t]+D w[t]` with

```text
T = 4; x[0] = (1182.074, 119560, 459.832, 45260)
A = [[1,0,0,0],[-25,1,0,0],[0,0,1,0],[0,0,-25,1]]
B = (20.073,0,-10.473,0)
D columns = (1,0,0,0), (0,0,-1,0)
u[t] in {0.6,0.3,0,-0.3,-0.6}
|w1[t]| <= 0.1+0.1t; |w2[t]| <= 0.1+0.3t; t=0,1,2,3
objective = ||x[4]-(1200,0,450,0)||_2
```

No source assertion about unprinted full-precision arrays or a distinct generating revision is imported. The enumeration applies to the displayed unconstrained four-step model; unknown historical implementation choices remain open.

## Exact result and argument

The standard-library [reference checker](tools/check_b08_displayed_exact.py) enumerates all `5^4=625` plans and all `2^8=256` disturbance-history corners for each plan using `fractions.Fraction`. Its [versioned raw record](evidence/b08-displayed-exact.json) retains the exact fractions and a worst-case terminal witness. For a fixed plan, the terminal state is affine in the eight disturbances. Every box point is a convex combination of its corners, and the Euclidean norm is convex, so its maximum equals a corner maximum. Minimizing exact **squared** worst-case norms preserves the minimizers of the reported norm. No floating tolerance chooses the ties.

| Evidence | Value |
|---|---|
| Exact minimum worst-case squared norm | `112730080707/25000000` |
| Minimum norm, decimal display | approximately `67.15060110140489` |
| Published plan's exact worst-case squared norm | `112730080707/25000000` |
| Reported `67.12` squared | `2815684/625` |
| Exact minimizers | `(0.6,0.6,-0.3,0)`; `(0.6,0.3,0.3,-0.3)`; `(0.3,0.6,0.6,-0.6)` |

For the printed plan, one attaining disturbance corner has signs `(+,−,+,−,+,−,+,−)` in stagewise `(w1,w2)` order. Its exact terminal state is `(12011397/10000,−10931/400,4526063/10000,−24509/400)`. Substitution into the printed Euclidean expression yields the exact squared value above.

The three plans have the same control sum `s=0.9` and weighted sum `m=2.7`, where `m=sum((3-t)u[t])`. Since `A=I+N`, `N^2=0`, the control contribution to `x[4]` is `B s+N B m`; all three therefore have the same terminal center and disturbance image. Their exact tie is structural under the displayed model. Enumeration confirms that each other plan has a strictly larger exact worst-case squared norm.

The published plan is therefore an exact minimizer of this *displayed-data reference*, but its reported cost is different. The [earlier NumPy check](reference-b08.json) found the same three plans only within `1e-8`; this exact result upgrades that limited tie statement for the printed rational inputs. It does not establish that the unpublished original arrays, constraints, criterion implementation or nonlinear simulation produce the same tie. The separate displayed nonlinear-state norm discrepancy remains in [baselines](baselines.md).

## Reproduction and limits

Run `python -B -O docs/research/tools/check_b08_displayed_exact.py --verify-record docs/research/evidence/b08-displayed-exact.json` from the repository root. The checker has no private-file or package dependency, executes no archived code and raises an error if the exact minimum, minimizer list or saved record differs from the computed result. Its decimal square root is descriptive; the exact squared fractions establish the comparison. This is a deterministic arithmetic check, not a runtime benchmark. No historical 37-second timing, speedup, memory, nonlinear trajectory or complete optimal-control family is claimed.

Issue #6 remains open. The canonical B04 inputs and generating revision, B08 original unrounded arrays and nonlinear integration, source-to-result mappings, and full published baseline reproduction still require separately identified evidence. The [B04 saved-witness audit](b04-saved-witnesses.md) remains a distinct noncanonical variant.
