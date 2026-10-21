# Stage-3 acados single-witness cross-check

Status: four one-time case attempts are documented across the linked evidence records. This work is a research-only external cross-check, not a paired comparison, benchmark, performance measurement, or reproduction of a published result. The repository does not integrate acados as a backend or dependency.

## Pinned tool and method

The native Windows/MSVC build recipe and smoke result are in [the acados v0.6.0 recipe](tools/acados-v0.6.0-native-msvc-build.md). The source was pinned to release commit `503364817c872d474ab5bed219c26760ac267769`, with its recorded submodules and no source modifications. The selected solve path was acados OCP-QP with `FULL_CONDENSING_HPIPM`; the native build used MSVC Release libraries. The upstream documentation describes native MSVC support as preliminary, so these observations establish only the recorded host/configuration.

The issue's per-case run limit has been honored: no case was solved more than once, and no timing result is used. Raw text evidence and SHA-256 manifests are linked below. The owner-authorized fuel variant `b04-reference-v1` uses the displayed L11/R40 model, printed initial state, continuous control interval `[-1,1]` on stages 0–15, and the stated flow box; its owner-affirmed interval and date are recorded in the [case note](b04-reference-cross-check.md). The historical scenario manifest and published claim were not changed.

## Case outcomes

| Case | External solve | Independent check | Evidence |
|---|---|---|---|
| T-S01, two-step scalar integrator | One OCP-QP call; status 0, exit 0 | The exact checker reconstructs the printed values as dyadic rationals and finds a nonzero `x[2]−1` deviation (`6.3283e-13`); it therefore does not claim literal membership in the full optimal family. The harness/checker were not driven completely from the canonical JSON. | [T-S01/T-S02 evidence](acados-ts01-ts02-cross-check-evidence.md) |
| T-S02, constant objective | One OCP-QP call; status 0, exit 0; the zero-variable objective was accepted | The captured trajectory is exactly feasible for the represented binary values, and the canonical constant objective is exactly 3. As with T-S01, the canonical JSON did not drive both execution and checking. | [T-S01/T-S02 evidence](acados-ts01-ts02-cross-check-evidence.md) |
| T-S03, horizon-3 double integrator | One OCP-QP call; status 0, exit 0 | A separate exact-rational checker validates constraints and objective and derives the exact optimum `8/13`; the reported witness is within `1.57e-10` in objective. This frozen case is generality evidence and is not asserted to be the later #421 fixture. | [T-S03 evidence](acados-ts03-horizon3-cross-check.md) |
| `b04-reference-v1`, T=16 fuel instance | One OCP-QP call; `ACADOS_MAXITER` (status 2), exit 1 | An exact-rational checker proves the optimum for the frozen variant and checks the returned point. The project's HiGHS adapter returned numerical `optimal`, but its diagnostics say certificates and bounds are unavailable; the requested literal adapter-certificate gate is not established. | [B04 attempt note](b04-reference-cross-check.md) and [reviewable evidence bundle](evidence/b04-reference-v1/README.md) |

The fuel attempt's numerical witness is recorded as an unsuccessful solver result, not promoted to success because it is close to the exact optimum. Its one permitted invocation is spent; the solver was not retried. No fallback was run. Failures and acceptance gaps remain visible.

## Acceptance disposition

The repository now contains the pinned build recipe, the four case records, exact-check material, the owner-affirmed variant provenance, and this combined summary. However, the intended external agreement is **not established for the full spike**:

- For T-S01/T-S02, the reviewed evidence states that the canonical JSON was assembled after the runs and did not drive both the harness and checker. Those one-run cases cannot be corrected by rerunning under the issue's cap.
- For `b04-reference-v1`, acados returned `ACADOS_MAXITER`; the project adapter exposes no literal optimal-value certificate or bound. Exact rational analysis is independent evidence, but it does not satisfy those two specifically requested solver gates. The one allowed solve has already been used.

These are evidence limits, not reasons to infer agreement. Do not close #513 or its fuel prerequisite #517 on the strength of this note. Any further acados attempt needs a new, explicitly authorized task that resolves the one-run policy and specifies an acceptable solver/certificate route. No benchmark or reproduction claim is authorized by this record.

## Primary sources

The build recipe links the pinned acados release, installation guide, OCP-QP C example, and CMake configuration at the exact release commit. Those sources were checked on 2026-10-20 as recorded in the recipe. The independent case definitions, exact checkers, raw outputs/exits, and manifests are kept in their linked evidence records; the B04 local compiled scratch artifacts remain outside the repository.
