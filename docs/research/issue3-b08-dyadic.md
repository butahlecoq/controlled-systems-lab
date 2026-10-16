# Issue 3 B08 exact-dyadic fixture audit

Date: 2026-10-16. Scope: one frozen public **linear, fixed-plan** B08 fixture and the existing finite-action numerical result for [issue #3](https://github.com/butahlecoq/controlled-systems-lab/issues/3). This is an independent source-bound audit of that fixture, not a general validated minimax solver or a reconstruction of the historical run.

## Sources and arithmetic boundary

The [L04 displayed-data audit](b08-displayed-exact-audit.md) identifies the privately held article by SHA-256 `6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f` and treats its printed decimals as **exact decimal rationals**. Its independent checker proves minimum squared cost `112730080707/25000000` and exactly three minimizing plans for that printed linear model. The archived L19 midpoint failure and supported convex-vertex argument are recorded in [the legacy audit](legacy-audit.md) and [fixed-plan contract](../contracts/fixed-plan-minimax.md).

This sidecar instead starts from the public Issue 3 [saved B08 input](../../reports/algorithm-results/issue3-finite-catalogue-b4632ce76510aa4f/evidence/accepted-001/accepted.stdout), SHA-256 `b4632ce76510aa4f2bb136baa193bc78da66506336a90d048cd8495c2d7926de`. It checks the input canonical JSON digest `47ec040f5631dd1b24012318223efb73fa2bb7aa2db76c03c56cb88f2a85e733`, then converts each binary64 coefficient and action with `Fraction.from_float`; disturbance vertices are decoded from their recorded binary64 hex strings. Thus `0.1+0.3t` uses the **saved binary64 vertex**, which need not equal either the literal decimal `0.1+0.3t` or a separately rounded expression. The product's affine source files at saved source commit `994f3ee4310b4087d289e2eb02adbdb9dfd97827` have identical Git blobs at the audit base `72e4637a31b21fa9169a47fc59f1c9ec020c1b28`.

The [independent checker](tools/check_issue3_b08_dyadic.py) enumerates all 625 ordered four-action plans and all 256 disturbance-corner histories per plan using exact rational affine recurrence. Universal safe sets make every plan feasible. For each plan it computes the maximum exact squared Euclidean residual; convexity puts a maximum at a box corner. It compares every indexed plan's status, action indices, terminal-row count, and reported worst value with a new untimed `--audit-b08` route in the existing optional public driver. The route reads the same `b08_request()` as the numerical report but exposes every `FinitePlanRecord`; it neither changes the solver nor the immutable published collection.

The audit row's `source_commit` names the saved numerical run, not the rebuilt
audit executable. Its `fixture_sha256`, checked against the current driver
file, and the sidecar's `product_driver_sha256` identify that rebuilt audit
code separately.

## Checked result

The versioned [JSON evidence](evidence/issue3-b08-dyadic.json) pins the saved raw, original fixture, current driver, input, aggregate result, and complete 625-score digest. It records:

| Quantity | This frozen binary64-input audit |
|---|---:|
| Exact squared minimax value | `231872326938210039429249200991359801692751261309588097080034965421/51422017416287688817342786954917203280710495801049370729644032` |
| Exact minimizing plan indices | `17, 33, 129` |
| Adjacent binary64 bracket for the exact norm | `67.15060110140709` to `67.1506011014071` |
| Previously saved numerical product value | `67.15060110140273` |
| A posteriori upper bound on this saved value's absolute discrepancy | `77/17592186044416` (about `4.38e-12`) |
| Largest a posteriori per-plan discrepancy bound across the 625 reported scores | `655/35184372088832` (about `1.86e-11`) |

The norm endpoints are also stored as exact dyadic fractions. The checker classifies the product's three `1e-8` near-minimizer indices with rational comparisons of adjacent norm brackets; any plan straddling the threshold fails the audit. Each reported score must lie within `1e-9` of its exact bracket, an explicit audit tolerance. These observed discrepancy bounds are derived **after** seeing this one binary64 product result. They do not supply an a priori rounding guarantee for the C++ solver, prove PSD admission, certify an independently supplied H/V conversion, or establish a verified optimal-plan family. The public API retains `Assurance::numerical`.

The printed-decimal rational minimum and this dyadic-input minimum are distinct exact numbers. Neither equals the article's reported `67.12`; the unavailable unrounded arrays, historical generator, nonlinear plant and feedback policy are outside this check. Issue #3 remains open for a general valid bound/certificate or explicit status contract on independently admitted inputs.

## Reproduce the audit

Build the existing optional Issue 3 report driver with `CSL_BUILD_ISSUE3_REPORT=ON`, then run:

```text
python -B -m unittest docs.research.tools.test_issue3_b08_dyadic -v
python -B scripts/reports/issue3/check_dyadic_audit.py <path-to-csl_issue3_finite_action_report>
python -B -O docs/research/tools/check_b08_displayed_exact.py --verify-record docs/research/evidence/b08-displayed-exact.json
```

The second command invokes only `--audit-b08`, checks all 625 public plan records against the exact replay and compares the result with the committed JSON sidecar. It does not time the algorithm, collect a new report, publish a page, or alter the earlier saved report. A changed driver source requires rebuilding after CMake reconfiguration so its compile-time fixture digest matches the source bytes.
