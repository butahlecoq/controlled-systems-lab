# Works source follow-up

Audit date: 2026-10-12. The owner supplied a further local `Works` folder. The [supplemental register](works-selected-sources.json) identifies all 14 immediate files by relative filename, byte count and SHA-256 (W01–W14). Original L/A identities and historical baseline records remain unchanged. Originals remain private; citations below refer to those hash-identified files, not downloadable public source.

This is static source inspection and inert notebook JSON/workbook XML inspection. No legacy function, solver, demonstration, notebook training loop or workbook formula was executed. The findings recover source variants and saved observations; they do not establish numerical correctness, chronology, authorship or performance.

## Relationships to existing sources

| Supplemental source | Relationship and limit |
|---|---|
| W08 `MinimaxOpenLoopControl.py` | All named top-level function/class definitions match L19 after ignoring positions; definitions are reordered. This supplies no repaired global worst-case oracle. |
| W12 `ReachableSet.py` | L26 with one blank line removed. Existing global-U, backward-B mutation and stage-index findings persist (`:3,12,21,26–27`); this is not independent corroboration. |
| W04 `LinearSystem.py` | A genuine L28 variant: uniform-grid stock self-coefficients are 1 (`:28`), whereas L28 uses 0. Other discrepancies remain below. |
| W01 `ClosedLoopControl.py` | Adds embedded open-loop/geometry/model helpers to the L16/L22 adaptive listing. Helper recovery does not prove a complete joint optimizer family. |
| W05/W06 `Main_mod.py` / `Main_Shor.py` | Python relatives of A15/A16 and A24/A25, with concrete algebraic differences. They are not assumed faithful ports. |

L19/L26/L28/L16 original hashes were checked before comparison. Repeated local copies are not independent evidence. A filename-only search of the earlier archive did not establish absence of renamed or compressed equivalents.

## Model and control variants

W04 documents state order as oxidizer flow/mass, fuel flow/mass (`:4`). Its uniform-grid stock-memory change is visible in source; no regression was run. The explicit-time branch still fixes the first control row to zero (`:25`), unlike the uniform branch (`:29`). Vector fitting writes slopes to mass coordinates B[1]/B[3] (`:31–37`), while scalar fitting writes to flow coordinates B[0]/B[2] (`:38–41`). Only slopes are retained, with no fitted affine intercept. The intended physical convention remains unresolved.

Its active demonstration (`:52–64`) uses x0=(1192.5,119500,454,45300), T=5, duration100, U=[−1,1] and nominal controls (0,0.1,−0.1,0.5,0.4). This is a separate configuration, not recovered B04 input or saved output. The [B04 restoration](b04-restoration.md) and [saved-witness](b04-saved-witnesses.md) inconsistencies remain open.

W09 `OpenLoopControl.py:7–46,55–102` supplies reachable-set, terminal minimization and control-witness recovery helpers missing from the standalone listing. It returns a finite witness collection, not the complete optimizer relation. W01 embeds such helpers into the adaptive source. W03 `LinClosedLoopControl.py` contains further parameter/recovery variants and a top-level call before its LinearSystem definition; compatibility and scientific correctness are unverified. These sources can inform replaceable recovery modules without promoting their current implementations to validated algorithms.

## Separate minimax configuration

W07 `MinimaxOpenLoopControl.ipynb`, zero-based cell7, describes T=4 and five actions (0.6,0.3,0.01,−0.3,−0.6), duration100/h=25, x0=(1182.074,119610,459.832,45220), flow-control coefficients 2208/110 and −1152/110, and two disturbance coordinates with corners [−1,1]². Its criterion is a negative unweighted four-residual norm. The cell source SHA-256 is `5867e4f0e69a635b9b1bea7845d8a8b7722b20c83bf037a2a5b40d020f5ca023` (UTF-8 joined source text).

The formal action product is 5⁴=625, not a verified feasible-plan or result count. All nine notebook cells have zero saved output objects; cell7 has no execution count. No fuel objective, trajectory or timing was recovered. The repeated L19-style local SLSQP worst-case calculation does not become a global maximization oracle. Preserve this configuration as its own source variant before any executable scenario conversion.

## Hull and representation conversion

W05/W06 line9 append an augmented ones row and original-column sum without the **+1** present in A16/A25 line6. Python ratio filtering uses `<0`, whereas the MATLAB routines use `<eps`; Python explicitly inverts the basis where MATLAB solves B\\M. W05 also differs in basis-column exclusion/deletion/reordering (`:20–26`). These are source differences, not measured correctness or speed differences. Their unseeded 4×1000 demonstrations and elapsed-time print statements are not benchmark results.

W14 `VFEnumeration.py:63` gives the empty affine-equality matrix width d, including the homogeneous coordinate; W12 `ReachableSet.py:136` uses d−1. This no-degeneracy representation discrepancy requires independent characterization before reuse. W14's literal fuel vertices (`:88–93`) are test inputs, not recovered B04 histories. Existing approximation and exact-polytope modules remain separate responsibilities.

## Saved rendezvous observations

W13 `Rendezvous-RL.ipynb` is a separate nonlinear radial/angular model, not the current linear fuel system. Cell2 specifies a 10-second/1000-step configuration, controls clipped to [−3,3] and initial (r,rdot,theta,thetadot)=(10,0,5π/180,0). Four output objects survive:

| Zero-based cell/output | Saved observation | Evidence limit |
|---|---|---|
| 4/0 | 1000 | Configuration print |
| 6/0 | Final displayed mean reward 0.14912488204173902 | Historical training log |
| 7/0 | Session functional 0.12882057853701992 | Single saved session score |
| 9/0 | [10,0.206632450,0.00264251506,−0.00106036872,−0.00616873884] | Displayed terminal array; first coordinate is time |

Cell2 accumulates the score near terminal time rather than simply evaluating a final norm. Execution counts show interactive ordering; no fixed seed, weights or full trajectory is saved. Unbounded training/sampling loops and `reward==np.nan` remain static implementation concerns. No adversarial agent is executed. These values are historical notebook observations, not rerun benchmarks, robust-game solutions or certified optima.

## Forecast data and next work

W02 `Forecast.py:9–15` consumes W10/W11 spreadsheets as 13 features and one target. Inert XML inspection found 1000×14 numeric cells in the first training sheet and 1×13 in the first test sheet; other sheets have no values and no formula nodes were found. Data provenance, units, physical meaning and relation to control experiments are unknown. Do not interpret these spreadsheets as fuel trajectories or performance tables.

Use the source variants to design independent tests for stock memory, control-coordinate conventions, witness recovery and homogeneous representation widths. Characterize Python/MATLAB hull differences before comparing performance. A future reproduced rendezvous experiment needs frozen dependencies/seeds/model/configuration and full histories. No original science issue or B04 gap is closed by this supplement, and no private source is redistributed.
