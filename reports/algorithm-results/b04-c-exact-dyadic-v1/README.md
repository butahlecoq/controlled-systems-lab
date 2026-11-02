# B04-C exact dyadic mathematical dossier

This is a research dossier checked by an independent Python exact-arithmetic tool. It is not a registered Strategy A result: the profile has not passed the compiled verifier and prepared-request boundary required by ADR 0003 and issue #8. The report index lists it in a separate Research Evidence section; that entry does not admit it as a compiled algorithm result or satisfy #531.

Scenario `B04-c-exact-dyadic-20261102` is the authorized corrected-track case from issue #531. It uses the saved A39/A01/A40 coefficient family; the sixteen-stage execution is the issue's corrected-track scenario, not a recovered historical T16 generator. Source artifact identities are retained in the record. It is separate from `B04-historical` and `b04-reference-v1`; it makes no reproduction claim.

The exact profile treats each finite decimal or fraction that enters as a binary64 model value as the exact dyadic represented by those bits, following ADR 0003. In particular, `B=(2208/110, 0, -1152/110, 0)` and the initial decimal coordinates are converted to binary64 first. The objective's `64/9` weight and `8/3` cross coefficient are also separately converted to binary64. Integer coefficients, the exact transition entries `-25/4`, bounds, the 25/4-second stage duration, and the three registered acceptance-band edges remain exact. This records the numerical model that the checker proves; it does not resolve the A40 unit convention behind its fourfold coefficient scaling.

The versioned [record](record.json) contains an exactly feasible control vector, exact terminal replay, and a zero-multiplier KKT certificate. Its exact gradient is zero in all 16 controls and every hard control/phase inequality is strict. The exact rational correction solved the two independent stationarity equations; the previous numerical optimizer was not invoked for this profile and its archived candidate is only a feasible starting point. The terminal residual map has rank two, so the candidate correction produces the exact minimizer over the affine terminal image. Convexity proves global optimality for the represented-dyadic problem. Strict convexity in the terminal state makes the optimal terminal point unique.

The reported objective is approximately `30.8991360300144`, inside the pre-registered band `|J* - 30.899| <= 0.0005`. The bands are unchanged; the other two strict bands do not apply. The published rounded terminal point is independently shown reachable inside its coordinate-wise rounding box, with its flow and stock plane-functional residuals included in the record. This reachability fact is separate from the optimality certificate.

The Python checker reconstructs a mathematical set of minimizing histories as a 16-dimensional control H-polytope with exact terminal-state equalities and an affine lift to the 84-coordinate joint history `(x0,...,x16,u0,...,u15)`. This is research evidence only: it is not a compiled, registry-verified family payload, and the repository does not expose its membership or projection queries as a supported API.

The SVG plots one representative history in both `(x1,x2)` oxidizer and `(x3,x4)` fuel phase planes. It does not imply that every minimizing history has these intermediate states. The family is described in this research record, but is not published as a registered family.

The English [HTML report](index.html) summarizes the research audit and links to its raw record, independent verification output, source notes, and evidence manifest. The report index provides a research-only Pages route while compiled-verifier admission remains outstanding.

## Reproduce and check

From the repository root, run:

```sh
python docs/research/tools/build_b04_c_exact_fiber.py
python docs/research/tools/finalize_b04_c_exact_fiber.py
```

The builder uses the archived preliminary feasible history only as a starting point. It adjusts two controls by exact rational arithmetic. The finalizer runs the independent checker, renders the figure, runs the focused tests, and writes SHA-256 manifests. The checker reconstructs the represented-dyadic model, all constraints, the 16-stage replay, the KKT conditions, the published-point reachability witness, the terminal fiber, and the affine lift. It does not import the builder or its model-construction code. The tests include mutations that omit a constraint, change the KKT witness, narrow the terminal fiber, and alter an acceptance band.

Historical context remains immutable: the published linear objective is `30.899`; the four nonlinear table rows remain `368.45`, `41.855`, `65.874`, and `7.922` with their displayed terminal vectors in the record. This exact corrected-track result neither explains nor reproduces those values.
