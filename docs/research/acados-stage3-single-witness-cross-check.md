# Stage-3 acados single-witness cross-check

Status: nine case attempts are documented across the linked evidence records. The original four attempts and the previously authorized T-S01/T-S02 reruns remain recorded. On 2026-10-23 the owner authorized one further attempt each for T-S01, T-S02, and `b04-reference-v1`. The smoke cases passed independent checks; B04 again returned `ACADOS_MAXITER`. Acados remains optional, research-only evidence and is not a gate on the main comparison program. This is not a paired comparison, benchmark, performance measurement, or reproduction of a published result. The repository does not integrate acados as a backend or dependency.

## Pinned tool and method

The native Windows/MSVC build recipe and smoke result are in [the acados v0.6.0 recipe](tools/acados-v0.6.0-native-msvc-build.md). The source was pinned to release commit `503364817c872d474ab5bed219c26760ac267769`, with its recorded submodules and no source modifications. The selected solve path was acados OCP-QP with `FULL_CONDENSING_HPIPM`; the native build used MSVC Release libraries. The upstream documentation describes native MSVC support as preliminary, so these observations establish only the recorded host/configuration.

The original one-run limit was later superseded for T-S01 and T-S02 only. Each new attempt used a case JSON to generate the OCP-QP inputs, and an independent checker read that same JSON and the solver witness. The Linux outcomes and local evidence path are in the [T-S01/T-S02 evidence note](acados-ts01-ts02-cross-check-evidence.md). No timing result is used. The owner-authorized fuel variant `b04-reference-v1` uses the displayed L11/R40 model, printed initial state, continuous control interval `[-1,1]` on stages 0–15, and the stated flow box. Its owner-affirmed interval and date are recorded in the [case note](b04-reference-cross-check.md). The historical scenario manifest and published claim were not changed.

## Case outcomes

| Case | External solve | Independent check | Evidence |
|---|---|---|---|
| T-S01, two-step scalar integrator | The original Windows call returned status 0 and exit 0. The first authorized Linux call returned status 0, then its client exited with signal 11 during output extraction. The two later calls returned status 0 and exit 0. | The core-recovered and latest JSON-driven witnesses passed the declared `1e-9` exact-check tolerance. The latest witness's terminal family deviation is `8.933995765403324e-10`; its generated QP objective was positively scaled by 1/2, which preserves the minimizer. | [T-S01/T-S02 evidence](acados-ts01-ts02-cross-check-evidence.md) |
| T-S02, constant objective | All three OCP-QP calls returned status 0 and exit 0. The zero-variable objective was accepted. | The latest JSON-driven witness passed the exact checker: initial state, dynamics and controls hold exactly for its binary values. The canonical objective is 3, so every feasible history is optimal. | [T-S01/T-S02 evidence](acados-ts01-ts02-cross-check-evidence.md) |
| T-S03, horizon-3 double integrator | One OCP-QP call; status 0, exit 0 | A separate exact-rational checker validates constraints and objective and derives the exact optimum `8/13`; the reported witness is within `1.57e-10` in objective. This frozen case is generality evidence and is not asserted to be the later #421 fixture. | [T-S03 evidence](acados-ts03-horizon3-cross-check.md) |
| `b04-reference-v1`, T=16 fuel instance | Two OCP-QP calls; both returned `ACADOS_MAXITER` (status 2), exit 1 | An exact-rational checker proves the optimum for the frozen variant and checks both returned points. The project's HiGHS adapter returned numerical `optimal`, but exposes no certificate or bound; this remains inconclusive on the adapter-specific gate. | [B04 attempt note](b04-reference-cross-check.md) and [reviewable evidence bundle](evidence/b04-reference-v1/README.md) |

The 2026-10-23 follow-up added one run each for T-S01 and T-S02 (both status 0 and independently checked) and one for B04 (status 2, `ACADOS_MAXITER`). B04's exact witness check and reused HiGHS comparison remain supplemental evidence only; neither substitutes for the explicitly requested solver-success or adapter-certificate outcomes. The raw follow-up artifacts and manifest are retained locally under `/tmp/opencode/acados-stage3-linux`.

The B04 numerical witness is recorded as an unsuccessful solver result, not promoted to success because it is close to the exact optimum. One follow-up attempt was explicitly authorized and also returned `ACADOS_MAXITER`; no further attempt or fallback was made. The remaining acceptance gaps are visible but, per owner direction, do not block the main comparison work or the note issue.

## Acceptance disposition

The repository now contains the pinned build recipe, the four case records, exact-check material, the owner-affirmed variant provenance, and this combined summary. However, the intended external agreement is **not established for the full spike**:

- The authorized T-S01/T-S02 reruns used JSON generated from the frozen case definitions to create OCP-QP inputs, and the independent checker read the same JSON. T-S02 passed exact feasibility and constant-objective checks. T-S01's solver returned status 0, but the client crashed while extracting output. The core dump preserved the primal values and residuals, and the exact checker passed them within tolerance. The exact T-S01 family relation still has a nonzero violation. The two authorized additional attempts are spent.
- For `b04-reference-v1`, the original and follow-up acados calls returned `ACADOS_MAXITER`; the project adapter exposes no literal optimal-value certificate or bound. Exact rational analysis is independent evidence, but does not satisfy those solver-specific gates. The owner accepts this as an optional inconclusive cross-check; there is no further attempt authorization.

These evidence limits do not establish full agreement or a solver/certificate success for B04. The note issue may be completed with this inconclusive outcome because acados is optional, as directed by the owner; this does not claim the original #517 solver-specific criteria passed. No further attempt, benchmark, paired comparison, or reproduction claim is authorized by this record.

Owner disposition: issues #513 and #517 were closed as not planned beyond the attempts and evidence recorded here. The failed B04 solver/certificate criteria remain explicitly unmet; the closure means no more optional acados work is planned, not that those criteria passed.

## Primary sources

The build recipe links the pinned acados release, installation guide, OCP-QP C example, and CMake configuration at the exact release commit. Those sources were checked on 2026-10-20 as recorded in the recipe. The independent case definitions, exact checkers, raw outputs/exits, and manifests are kept in their linked evidence records; the B04 local compiled scratch artifacts remain outside the repository.
