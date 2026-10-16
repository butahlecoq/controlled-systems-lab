# L13 Table 2 displayed-decimal criterion audit

This is an arithmetic comparison of the four non-reference states printed in L13's Table 2. It does not reconstruct an optimization, integrate the nonlinear plant, or identify the program that generated the published rows. The reported criteria remain historical observations, with no replacement values inferred here.

## Source and formulas

L13 is the 17-page PDF registered in the [initial inventory](inventory.json) with SHA-256 `4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e`. Equation (16), physical PDF p. 6, specifies Euclidean distance from the terminal state to `(60,0,24,0)`; Table 2, physical PDF p. 14, supplies the states and reported criteria transcribed in [baselines](baselines.md). The [publication-to-source matrix](publication-source-matrix.md) records the correspondence limits.

A09 `Minmaxopenloop.m`, registered in the [selected archive](archive-selected-sources.json) with SHA-256 `59daeacc7727cb7ff5e0090368d76e401fa4d0c874ef359a97d6acb722467aa6`, contains the terminal expression at line 32. Its local original matched that registered hash for this audit. A09 adds the squared synchronization residual `(2.5*x4-x2)^2` to the four Euclidean squares. A09 is a **related implementation and candidate criterion**, not a source-to-table-row match. A08's separate nonlinear reporting formula differs, and A10's saved state differs from the published row, as recorded in the [archive follow-up](archive-followup.md).

For each printed state `x`, the checker evaluates the following squared expressions using exact rational values of the printed decimals:

```text
E² = (x1 - 60)² + x2² + (x3 - 24)² + x4²
S² = E² + (2.5*x4 - x2)²
```

The decimal norm columns below are square roots shown for comparison; the fraction columns are the exact results for the displayed coordinates.

| L13 Table 2 row | Reported criterion | E² exact | E approximately | S² exact | S approximately |
|---|---:|---:|---:|---:|---:|
| Simplified, open loop | 115.79 | `5536289/2000` | 52.613159000 | `26836769/2000` | 115.837750755 |
| Simplified, adaptive | 22.658 | `864761/2000` | 20.793761084 | `514283/1000` | 22.677808536 |
| Original, open loop | 25.295 | `669809/1250` | 23.148373593 | `1594643/2500` | 25.255834969 |
| Original, adaptive | 22.657 | `21617/50` | 20.792787211 | `205697/400` | 22.676915575 |

For example, the simplified open-loop row has `2.5*(-22.2)-47.7=-103.2`; adding its square to `5536289/2000` gives `26836769/2000`. Neither expression exactly equals the reported criterion at the displayed coordinates. The augmented expression is closer for every row, especially the simplified open-loop row, but proximity does not identify the historical implementation.

Printed coordinates are rounded. These exact fractions describe those decimals only; they do not enclose results from unprinted higher-precision coordinates or justify an explanation of any remaining difference. The original numerical arrays, nonlinear trajectory, criterion implementation used for Table 2, and mapping from A09 to each publication row remain unresolved. Issue [#1](https://github.com/butahlecoq/controlled-systems-lab/issues/1) therefore remains open.

Run the standard-library [checker](tools/check_l13_displayed_criteria.py) and [literal behavioral tests](tools/test_l13_displayed_criteria.py) from the repository root:

```text
python -B -O docs/research/tools/check_l13_displayed_criteria.py
python -B -O docs/research/tools/test_l13_displayed_criteria.py
```
