# L13 Table 2 rounding-box criterion audit

This [issue #1](https://github.com/butahlecoq/controlled-systems-lab/issues/1) check asks whether ordinary rounding of L13's four non-reference Table 2 terminal coordinates could account for the criterion differences. It extends the [displayed-decimal audit](l13-displayed-criterion-audit.md), which evaluates the printed coordinates themselves. It does not identify a publication-generating source, reproduce a nonlinear trajectory, or replace the [reported baselines](baselines.md).

## Source and convention

The private L13 PDF (370,362 bytes, SHA-256 `4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e`) and A09 MATLAB routine (1,578 bytes, SHA-256 `59daeacc7727cb7ff5e0090368d76e401fa4d0c874ef359a97d6acb722467aa6`) matched the [registered originals](inventory.json) and [selected-source register](archive-selected-sources.json) by raw bytes in this review. L13 physical PDF p. 6, Eq. (16), prints Euclidean distance to `(60,0,24,0)`; physical p. 14, Table 2, prints the four terminal rows. A09 line 32 adds a squared synchronization residual `(2.5*x4-x2)^2` to that Euclidean squared norm. The [publication-to-source matrix](publication-source-matrix.md) does not establish that A09 generated Table 2.

For each printed coordinate and criterion, the [checker](tools/check_l13_rounding_boxes.py) takes the closed interval centered at that decimal with half a unit in its last printed place. For example, `20.3` gives `[20.25,20.35]`; an integer `60` gives `[59.5,60.5]`. This is a **conditional nearest-decimal convention**, not evidence of the paper's formatter or unrounded data. Using closed endpoints conservatively includes any tie choice; every candidate witness below is strictly inside the relevant intervals. All calculations use `Fraction` and squared nonnegative costs, so the comparisons introduce no floating-point or square-root rounding.

For the Euclidean expression, each coordinate's smallest absolute target distance is `max(0, |printed-target|-half_width)` and its largest is `|printed-target|+half_width`. The sums of their squares are exact extrema over the whole coordinate box. For the A09 candidate, one explicit rational state per row suffices to prove compatibility. Only `x2` changes from the printed coordinate; the other three coordinates stay at their printed centers.

| L13 Table 2 row | Reported criterion | Euclidean squared **upper** | Reported criterion squared **lower** | Candidate witness `x2` | A09 candidate squared at witness |
|---|---:|---:|---:|---:|---:|
| Simplified open loop | `115.79` | `2220113/800` | `536246649/40000` | `47.663343` | `6703662052435649/500000000000` |
| Simplified adaptive | `22.658` | `1739473/4000` | `82137969/160000` | `20.284693` | `256692473854249/500000000000` |
| Original open loop | `25.295` | `434691/800` | `2559246921/4000000` | `22.630245` | `12796741050401/20000000000` |
| Original adaptive | `22.657` | `17413/40` | `2053267969/4000000` | `20.284611` | `256669819671321/500000000000` |

Each Euclidean upper bound is strictly below the corresponding reported-cost lower bound. Thus **no coordinate state in any of the four rounding boxes can produce its reported cost under L13 Eq. (16)**, assuming the printed criterion was rounded to its shown precision from that same terminal state. Each listed `x2` lies strictly within its printed `±0.05` interval, and its A09 candidate squared value lies strictly between the exact squares of the reported criterion's rounding endpoints. This proves only that the A09-style expression **can** fit each row under the stated rounding convention. It does not prove that A09 was used, that all four witnesses came from one executable model, or that any witness is reachable by the nonlinear plant.

## Recheck and remaining gap

The standard-library checker needs no private files for the arithmetic. It can optionally hash-check both registered originals before producing the same result; a public run reports `private_sources_verified: false`.

```text
python -B -O -m docs.research.tools.check_l13_rounding_boxes
python -B -O -m unittest docs.research.tools.test_l13_rounding_boxes
python -B -O -m docs.research.tools.check_l13_rounding_boxes --l13-pdf <private-L13-PDF> --a09-source <private-A09-M-file>
```

The tests assert literal exact fractions and source-hash rejection. The actual generating revision, unrounded arrays, objective implementation, control/history mapping and nonlinear simulation remain unlocated. The A10 saved-workspace [criterion trace](l13-a10-saved-criterion-trace.md) is a distinct run and cannot close that gap. Issue #1 remains open.
