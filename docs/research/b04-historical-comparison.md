# B04 historical table and restoration evidence

> Historical-only record. The B04 manifest is non-executable. This report contains no solver run or current benchmark measurement.

Scenario `B04-historical`. Restoration status: `displayed_data_inconsistent_with_reported_optimizer`.

## Reported terminal rows

Source: A11 Table 2; policy labels cross-checked A12 PDF p. 20 and R40 Table 2. Printed-coordinate evaluations are separate from reported objectives. The coordinate-rounding bound limits the effect of the displayed coordinate precision; it is not a source-data uncertainty model.

| Policy | Printed terminal state `(x1, x2, x3, x4)` | Reported objective | Computed at printed coordinates | Rounding bound | Interpretation |
| --- | --- | ---: | ---: | ---: | --- |
| Nominal reference, u(t)=0 | `1200 (±1/2), 0 (±1/2), 450 (±1/2), 0 (±1/2)` | `0` (±1/2) | `0` | `2.7233557730613653091117634459550806` | Separate nominal reference, not a zero-control solution from perturbed B04 initial state |
| Nonlinear, frozen-coefficient regulator u* | `1190.4 (±1/20), 101.7 (±1/20), 455.12 (±1/200), -72.817 (±1/2000)` | `368.45` (±1/200) | `368.60684134725443264279291958383919` | `0.088400603316191607690105540869517922` | reported Table 2 row |
| Nonlinear, optimal linear witness 1 | `1200.5 (±1/20), -2.695 (±1/2000), 449.72 (±1/200), 10.556 (±1/2000)` | `41.855` (±1/2000) | `41.854849205319089286931504332807995` | `0.051799292144455667905646535444926816` | optimal for the linear model; this row does not claim nonlinear global optimality |
| Nonlinear, optimal linear witness 2 | `1200.5 (±1/20), 0.50887 (±1/200000), 449.72 (±1/200), 17.561 (±1/2000)` | `65.874` (±1/2000) | `65.875930685244465343968244917319849` | `0.051781721839532013254760935688817443` | optimal for the linear model; this row does not claim nonlinear global optimality |
| Nonlinear, optimal linear witness 3 | `1200.5 (±1/20), -6.366 (±1/2000), 449.72 (±1/200), -1.475 (±1/2000)` | `7.922` (±1/2000) | `7.9197503327651265886362486052101466` | `0.051799292144455667905646535444926816` | optimal for the linear model; this row does not claim nonlinear global optimality |
| Linear, any of witnesses 1–3 | `1200.7 (±1/20), -22.929 (±1/2000), 450.2 (±1/20), -7.709 (±1/2000)` | `30.899` (±1/2000) | `30.898903572780701501316535212588709` | `0.14241898281713244516437153625477400` | reported Table 2 row |

## Restoration diagnostics

- Execution gate: Do not solve this manifest or compare against 30.899 until missing inputs and inconsistent model are resolved. A fully specified reference variant must use a distinct scenario ID.
- Stock invariant: required `-21227/10`; the reported point gives `-406201/1000`; gap `1716499/1000`; coordinate rounding radius `29/2000`.
- Unrestricted terminal-plane minimum: `160.8806539455271` with exact squared value `2958186538093451/114292546875`. This is a lower bound for constrained versions of the displayed model, not a constrained optimum or historical reproduction.
- Provisional interval: `[-1, 1]` is a separate owner recollection from L16; it is not an input to this historical manifest. The distinct article-derived case is `b04-reference-v1`.
- Missing controls and the first-action convention remain unresolved. The displayed model and reported terminal result remain inconsistent.

## Runtime and reproduction

- Historical reported runtime: `0.4` seconds. This is publication context, not a current measurement.
- Current measured runtime: unavailable.
- Reproduction: unavailable. The manifest is non-executable, has unresolved controls and first-action semantics, and contains a proved displayed-model/terminal-result inconsistency.

## Sources

- A11: B04 tables and figure captions recovered locally; SHA-256 `45d6d82e0447a3a1b988753b618097c20f9be56c30d2c2022789b8893a4f9de1`.
- A12: 23-page B04 draft containing tables; SHA-256 `8ade2a23baf0a99dd53022abb436f6d1975db3616487d8e7c97b3c2d4d7531af`.
- A14: Byte-identical copy of supplied L11; SHA-256 `e04c2f1609e2580c8878ab7fb91bc41151ccc8e0cf1f5deac4cef9fd860ce147`.
- R40: published_counterpart_with_tables; DOI [10.1134/S0002338819020094](https://sciencejournals.ru/view-article/?a=TeorSist1902009Kalev&j=teorsist&n=1&v=0&y=2019).

Manifest SHA-256: `92900c07ac4b1ce2f889a99023809e789110e77d7416cd192facc3ffc89d072d`. Audit SHA-256: `8e3e53324ec0b4b9fb35a66030b308138b1b71e12308683f5dc89dbff4b8b9dc`. Archive-register SHA-256: `89ab1a8c64f8f4074d5ce729e770f82d3621f588aeeda0949794aa1cb1399e99`.

Rebuild instructions and schema details are in [historical-versus-reproduced](../artifacts/historical-versus-reproduced.md).
