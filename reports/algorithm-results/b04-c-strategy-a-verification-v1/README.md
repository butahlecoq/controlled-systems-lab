# B04-C registered Strategy A verification

This versioned page joins the exact represented-dyadic research record with the registered Strategy A functional test. The exact rational record and its independent checker establish the corrected-track optimum and optimizer family. The Native C++20 run linked from this report establishes that the prepared Strategy A request returns a completed `CompleteOptimalFamily` using the registered B04-C verifier and an objective interval inside the pre-registered confirmation band.

The CI check is functional evidence, not a benchmark or a saved numerical run record. The exact value and full family below come from the separate exact-rational record. No performance or timing claim is made.

Scenario `B04-c-exact-dyadic-20261102` uses the saved A39/A01/A40 coefficient family. It is distinct from `B04-historical` and `b04-reference-v1`, and does not claim to reproduce a historical result. A40's fourfold coefficient scaling retains an unresolved unit-convention question; the archived family coefficients are used without endorsing a normalization.

## Evidence

- Exact represented-dyadic objective: approximately `30.8991360300144`, inside the unchanged band `|J* - 30.899| <= 0.0005`. The other two pre-registered bands do not apply.
- The published rounded terminal point is reachable inside its coordinate-wise rounding box. Exact plane-functional residuals are retained in `record.json`.
- The complete minimizing relation is a bounded 16-control H-polytope with an exact affine lift to 84 joint state/control coordinates. Its induced terminal set is a singleton.
- The compiled test asserts completion, `CompleteOptimalFamily`, the exact relation coordinates and representation, an objective interval inside the pre-registered band, the registered verifier ID, and a full-history membership boundary query.
- The report preserves the published linear value `30.899` and nonlinear table rows `368.45`, `41.855`, `65.874`, and `7.922` as immutable context. The corrected-track result explains or reproduces none of the nonlinear rows.

The SVG shows one representative trajectory in both `(x1,x2)` oxidizer and `(x3,x4)` fuel phase planes. It does not imply that every minimizing history has these intermediate states.

## Reproduction

Recheck the mathematical record from the repository root with:

```sh
python docs/research/tools/check_b04_c_exact_fiber.py
```

Run the functional test with the repository's Release test build:

```sh
ctest --test-dir build -C Release --output-on-failure -R '^strategy_a_tests$'
```

The captured test source is identified by commit `cfe72885b4544e5b005c27395d805faec219a4fc`; its exact-head Native C++20 workflow run is [41467988977](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/41467988977). No benchmark was run for this report.
