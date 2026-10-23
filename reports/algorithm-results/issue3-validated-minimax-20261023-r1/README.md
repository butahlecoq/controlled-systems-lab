# Issue #3 validated minimax capture

Seven measured batches per fixture after one excluded warmup. This report measures the validated bounds API with the public driver at source `c72f3480c8fea2575ba860890502857006e9b9f4` and harness `1c606969b0d15700b61e43effdbbd545e9d0ed73`. It is a single-adapter descriptive capture, not a comparison. No source-mapped limiter profile was collected.

The B08 capture uses exact-real semantics for the binary64 inputs represented by saved hexadecimal floats. It is not the separate printed-decimal rational audit, and does not establish a general solver guarantee beyond this API's documented contract.

`evidence/` retains the clean Release executable, build/configure logs, raw stdout/stderr, host/platform/compiler receipts, and source status. Regenerate the checked report with `python3 scripts/reports/issue3/validated_saved.py <capture-dir> <new-output-dir>`. Rendering reads saved JSONL and does not run the solver.
