# Stage-3 acados single-witness cross-check

Status: six case attempts are documented across the linked evidence records. The original four attempts remain unchanged. The owner later authorized one additional T-S01 and one additional T-S02 attempt. This work is a research-only external cross-check, not a paired comparison, benchmark, performance measurement, or reproduction of a published result. The repository does not integrate acados as a backend or dependency.

## Pinned tool and method

The native Windows/MSVC build recipe and smoke result are in [the acados v0.6.0 recipe](tools/acados-v0.6.0-native-msvc-build.md). The source was pinned to release commit `503364817c872d474ab5bed219c26760ac267769`, with its recorded submodules and no source modifications. The selected solve path was acados OCP-QP with `FULL_CONDENSING_HPIPM`; the native build used MSVC Release libraries. The upstream documentation describes native MSVC support as preliminary, so these observations establish only the recorded host/configuration.

The original one-run limit was later superseded for T-S01 and T-S02 only. Each new attempt used a case JSON to generate the OCP-QP inputs, and an independent checker read that same JSON and the solver witness. The Linux outcomes and local evidence path are in the [T-S01/T-S02 evidence note](acados-ts01-ts02-cross-check-evidence.md). No timing result is used. The owner-authorized fuel variant `b04-reference-v1` uses the displayed L11/R40 model, printed initial state, continuous control interval `[-1,1]` on stages 0–15, and the stated flow box. Its owner-affirmed interval and date are recorded in the [case note](b04-reference-cross-check.md). The historical scenario manifest and published claim were not changed.

## Case outcomes

| Case | External solve | Independent check | Evidence |
|---|---|---|---|
| T-S01, two-step scalar integrator | The original Windows call returned status 0 and exit 0. The authorized Linux call returned status 0, then its client exited with signal 11 during output extraction. The saved core contains the solver result. | The canonical-JSON-driven exact checker passed the `1e-9` tolerance on the core-recovered witness. The witness is not an exact member of the full optimal family: `x2−1 = 1425/2251799813685248`. | [T-S01/T-S02 evidence](acados-ts01-ts02-cross-check-evidence.md) |
| T-S02, constant objective | Both OCP-QP calls returned status 0 and exit 0. The zero-variable objective was accepted. | The authorized Linux witness passed the canonical-JSON-driven exact checker. Initial state, dynamics, and control bounds hold exactly for its binary values. The canonical objective is 3, so every feasible history is optimal. | [T-S01/T-S02 evidence](acados-ts01-ts02-cross-check-evidence.md) |
| T-S03, horizon-3 double integrator | One OCP-QP call; status 0, exit 0 | A separate exact-rational checker validates constraints and objective and derives the exact optimum `8/13`; the reported witness is within `1.57e-10` in objective. This frozen case is generality evidence and is not asserted to be the later #421 fixture. | [T-S03 evidence](acados-ts03-horizon3-cross-check.md) |
| `b04-reference-v1`, T=16 fuel instance | One OCP-QP call; `ACADOS_MAXITER` (status 2), exit 1 | An exact-rational checker proves the optimum for the frozen variant and checks the returned point. The project's HiGHS adapter returned numerical `optimal`, but its diagnostics say certificates and bounds are unavailable; the requested literal adapter-certificate gate is not established. | [B04 attempt note](b04-reference-cross-check.md) and [reviewable evidence bundle](evidence/b04-reference-v1/README.md) |

The fuel attempt's numerical witness is recorded as an unsuccessful solver result, not promoted to success because it is close to the exact optimum. Its one permitted invocation is spent; the solver was not retried. No fallback was run. Failures and acceptance gaps remain visible.

## Acceptance disposition

The repository now contains the pinned build recipe, the four case records, exact-check material, the owner-affirmed variant provenance, and this combined summary. However, the intended external agreement is **not established for the full spike**:

- The authorized T-S01/T-S02 reruns used JSON generated from the frozen case definitions to create OCP-QP inputs, and the independent checker read the same JSON. T-S02 passed exact feasibility and constant-objective checks. T-S01's solver returned status 0, but the client crashed while extracting output. The core dump preserved the primal values and residuals, and the exact checker passed them within tolerance. The exact T-S01 family relation still has a nonzero violation. The two authorized additional attempts are spent.
- For `b04-reference-v1`, acados returned `ACADOS_MAXITER`; the project adapter exposes no literal optimal-value certificate or bound. Exact rational analysis is independent evidence, but it does not satisfy those two specifically requested solver gates. The one allowed solve has already been used.

These evidence limits do not establish full agreement. Do not close #513 or its fuel prerequisite #517 on the strength of this note. No additional acados attempt is authorized. In particular, do not rerun `b04-reference-v1`. Any later attempt needs a new explicit authorization and an accepted solver/certificate route. No benchmark or reproduction claim is authorized by this record.

## Primary sources

The build recipe links the pinned acados release, installation guide, OCP-QP C example, and CMake configuration at the exact release commit. Those sources were checked on 2026-10-20 as recorded in the recipe. The independent case definitions, exact checkers, raw outputs/exits, and manifests are kept in their linked evidence records; the B04 local compiled scratch artifacts remain outside the repository.
