This directory contains the reviewable text evidence for the single `b04-reference-v1` investigation attempt.

- `canonical-case.json` is the solver/checker input.
- `exact_check.py` verifies the rational global optimum and returned witness.
- `generate_harnesses.py` generated the committed C/C++ harness sources.
- `generated_b04_ocp_qp.c` and `generated_b04_highs_qp.cpp` are the exact harness inputs compiled for the recorded runs.
- `highs-output.log` / `solver-output.log` and their exit files preserve raw solver observations.
- The JSON reports preserve exact-arithmetic and converted-norm checks.
- `evidence-manifest.json` provides SHA-256 hashes for these files.

The compiled executables are not included. The acados invocation returned `ACADOS_MAXITER`; the bundle records a failed attempt and does not satisfy issue #517.
