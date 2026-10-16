# A10 saved-workspace terminal criterion trace

This note narrows [issue #1](https://github.com/butahlecoq/controlled-systems-lab/issues/1) using one saved MATLAB workspace. It does **not** identify the source version that generated L13 Table 2, rerun the archived program, integrate either nonlinear plant, or reproduce a publication row. The printed criteria in [baselines](baselines.md) are unchanged.

## Source identity and expressions

The private originals matched the byte counts and SHA-256 digests for A08 `Minmaxclosedloop.m`, A09 `Minmaxopenloop.m`, and A10 `results.mat` in the [selected-source register](archive-selected-sources.json). All three are under the registered `Публикации/Минимакс/Adaptive_Samara/` archive directory. A08 lines 81 and 136 report nonlinear adaptive and open-loop `J` with an **unsquared** fuel-flow deviation `(x3-24)` inside the square root. A09 line 32 instead uses `(x3-24)^2` and adds the synchronization square `(2.5*x4-x2)^2`. L13 Eq. (16), physical PDF p. 6, prints the four-state Euclidean norm. The [displayed-decimal audit](l13-displayed-criterion-audit.md) evaluates Eq. (16) and A09's candidate at the rounded Table 2 coordinates; it makes no assertion about A10's saved coordinates.

For a terminal state `x=(x1,x2,x3,x4)`, this trace compares:

```text
L13 Eq. (16): sqrt((x1-60)^2 + x2^2 + (x3-24)^2 + x4^2)
A08 report:   sqrt((x1-60)^2 + x2^2 + (x3-24)   + x4^2 + (2.5*x4-x2)^2)
A09 candidate:sqrt((x1-60)^2 + x2^2 + (x3-24)^2 + x4^2 + (2.5*x4-x2)^2)
```

The A08 term may be a source error; the checker records it as written and does not silently correct it. All calculations below use ordinary binary64 arithmetic on saved MATLAB doubles, without a rounding enclosure.

## Saved-workspace observation

The hash-gated, read-only [checker](tools/check_l13_a10_saved_criterion.py) loads A10's `J`, `m`, `position`, `UU`, `UUU`, and four saved trajectory vectors. A08's final assignment at line 136 uses `m(:,end)`, so the saved `J` is compared with that endpoint. The final elements of A10's `mo`, `Mo`, `mg`, and `Mg` equal `position(:,end)` exactly as stored, allowing comparison with A08's adaptive expression at line 81. The file contains no provenance establishing that its producer was this exact A08 revision; agreement identifies a consistent criterion variant, not authorship or execution history.

| Observation from A10 | Value |
|---|---|
| Saved open-loop controls `UUU` | `(0.75,1,-1,0.25)` |
| Saved adaptive controls `UU` | `(0.75,0.75,-0.5,-0.5)` |
| Saved open-loop `m(:,end)` | `(60.50153367245107,18.08439396961137,23.72609163625532,3.9803245521003423)` |
| Saved adaptive `position(:,end)` | `(60,14.589974321147963,24,3.2502993802977542)` |
| Saved `J` | `20.224269632967587` |

| Expression on A10 endpoint | Open loop | Adaptive |
|---|---:|---:|
| L13 Eq. (16) | `18.526058690517537` | `14.94763515588071` |
| A08 nonlinear report | `20.224269632967587` | `16.28551543110981` |
| A09 squared candidate | `20.232894413366783` | `16.28551543110981` |

The saved `J` agrees with A08's unsquared **open-loop reporting** expression at the saved `m(:,end)` to `1e-12` in binary64. It differs from the A09-style squared result. The adaptive endpoint has `x3=24`, so it cannot distinguish the squared and unsquared fuel-flow terms; no saved adaptive `J` is inferred from this comparison.

L13 Table 2, physical PDF p. 14, prints original open loop `(60.26,22.6,23.86,5)` with criterion `25.295` and original adaptive `(60,20.3,24,4.5)` with criterion `22.657`. Neither A10 endpoint rounds to its corresponding printed row. The criterion match within A10 therefore does not bridge A10 to the publication, recover the original arrays or control/history mapping, or resolve the L04 nonlinear-row discrepancy. The [publication-to-source matrix](publication-source-matrix.md) remains the broader correspondence record.

## Recheck and limits

From the repository root, public CI can run the standard-library boundary and literal tests without private sources; the MAT integration test explicitly skips:

```text
python -B -O docs/research/tools/test_l13_a10_saved_criterion.py
```

With permission to access the local originals and NumPy/SciPy available, supply the directory root from the selected-source register:

```text
python -B -O docs/research/tools/check_l13_a10_saved_criterion.py --archive-root <private-archive-root>
python -B -O docs/research/tools/test_l13_a10_saved_criterion.py --archive-root <private-archive-root>
```

The checker verifies A08–A10 hashes and byte counts **before** loading the MAT file, reads only the named saved arrays, executes no archived MATLAB, writes no files, and omits the private root path from successful JSON. The tests pin independent literal endpoints, controls, `J`, and all three open-loop criteria; an altered A08 file is rejected before MAT loading. A public skip is not evidence that the private originals were checked in CI. Issue #1 remains open for the actual L04/L13 generating version, criterion/coordinate convention, and nonlinear-row reproduction.
