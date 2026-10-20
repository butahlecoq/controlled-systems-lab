# Missing primary inputs: dossier for human review

Date: 2026-10-20. Status: reviewer handoff, not a reproduction claim. This dossier does not change any baseline, manifest or published value.

Scope: the primary data and source identity that are still absent for the historical experiments B01-B09, the L05 reachability examples, the R29 zonotope example and the optional ellipsoidal comparison. It is addressed to the archive owner or another reviewer who can supply a file, confirm that it no longer exists, or authorize a deeper search. Original files remain private; only hashes and derived, non-source facts are recorded here.

Related live issues: [#1](https://github.com/butahlecoq/controlled-systems-lab/issues/1) (L04/L13 terminal criteria), [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2) (canonical inputs and missing implementations), [#4](https://github.com/butahlecoq/controlled-systems-lab/issues/4) (L05 inclusion and nonlinear error), [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6) (published baselines), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8) (replaceable algorithms and R29), [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10) (B04 canonical model).

This dossier is not a duplicate of #2. #2 remains the canonical recovery ticket and carries the implementation acceptance criteria; this document is the reviewer-facing inventory and disposition sheet that #2 and the per-baseline issues can point to. The reviewer request is filed as [#521](https://github.com/butahlecoq/controlled-systems-lab/issues/521).

## 1. Why this dossier exists

The implementation backlog has moved quickly: the last thirty pull requests delivered native box, parallelotope, zonotope and ellipsoid approximations, lazy support functions, continuous-model discretization, nonlinear replay, smooth-convex feasible directions and a large CI/documentation cleanup. Historical reproduction is now the slower side of the program, not the code.

The repository already records each gap in a dedicated audit. What it did not have is one reviewer-facing inventory that answers three practical questions for every baseline:

1. What exactly is missing?
2. What is already in hand, so it does not need to be sent again?
3. What is the smallest handover that would unblock the case, or the statement that would let the project close it as declared-unavailable?

This document is that inventory. It is deliberately conservative: a value is called missing only when the hash-identified source does not print it and no recovered artifact supplies it. "Absent" always means "absent from the bounded searches described in section 10", not "proved not to exist".

## 2. Status vocabulary

| Term | Meaning in this dossier |
|---|---|
| In repository | A public transcription, manifest, checker or derived record exists and is linked here |
| Hash-identified private | The original exists in the owner's archive, is registered with byte count and SHA-256, and is not redistributed |
| Candidate | A related source variant that does not match the publication row or run and must not be substituted for it |
| Absent | No matching artifact was found in the searched corpus; not a proof of non-existence |
| Not printed | The publication itself does not specify the value |
| Declared unavailable | The owner states that no accessible copy exists or that it cannot be released |
| Not required | The owner narrows the comparison goal so the historical artifact is unnecessary; no reproduction claim is made and the algorithmic comparison proceeds on shared synthetic fixtures |
| Historical replay | Executing a historical baseline with its historical inputs and original software to reproduce a published row; declared not required for B03, whose comparison uses C++ translations on shared fixtures |
| Corrected track | A new, separately identified experiment that repairs a demonstrable source inconsistency; never labelled a reproduction |

## 3. Highest-leverage requests

If only a small number of items can be reviewed, these are the highest-leverage ones.

| Priority | Artifact | Exact missing input | What it unlocks |
|---:|---|---|---|
| 1 | B04 / L11, T=16 | Original T=16 project or complete owner-authenticated input package: `U` rows and witness mapping, first-action convention, every stage bound, generating revision, coefficient/unit authority | The owner-selected first end-to-end benchmark, the terminal-invariant contradiction and issues #10/#6 |
| 2 | B06 / L09 and B07 / L10 | Numerical disturbance sets `W(t)` and `V1(t)` (bounds or vertices, stage dependence); for B07 also stock initialization and stage time grid | Executable finite-action minimax baselines, including the 365-feasible-plan count and reported worst cases |
| 3 | L05 Example 2, 4D | The revision and driver that produced the modified row `153 vertices / 34764.47`, including the retention schedule and rank-tie behavior | The only unreproduced Table 1 cell in the four-state example; closes the B02 modified-construction question |
| 4 | B08 / L04 and B09 / L13 | The generating MATLAB revision, original unrounded arrays, nonlinear integration and the actual criterion implementation | The `14.048` versus `16.42069149` and `22.657` versus `20.792787211` terminal-row discrepancies in issue #1 |

A separate item, specific to L05 Example 1, is the exact `T0` grouping, reference trajectory samples and coordinate map from the physical start `(410,300)` to the linear start `(1,2)`. It is lower cost than the four above but blocks every quantitative comparison in the two-dimensional example.

B03 is no longer an input-recovery priority. The owner directed that B03 compare algorithms rather than reproduce the historical sets or software run: baseline MATLAB/Python hull algorithms are translated into C++ and run with the modern algorithms on shared fixtures. The original clouds, seeds and timing scope are not required; see [section 4.3](#43-b03---l07-reachability-and-hull-comparisons).

## 4. Per-artifact register

### 4.1 B01 - L01/L02 general terminal control

**Reported evidence:** L01/L02 contain a foundational terminal-control formulation and, in L02, a production-planning example. No numerical baseline is registered as executable.

**Already in hand:** the supplied articles and extracted text; the mathematical description in [scientific foundations](scientific-foundations.md).

**Missing:**

- [ ] The intended numerical instance: dimensions, every `A/B` matrix, initial state, control and state polytopes, objective weights and units.
- [ ] A statement of which article example, if any, should become the first B01 reference.
- [ ] The source revision and any saved output behind the example.

**Blocked:** B01 cannot be transcribed into a manifest, let alone executed. No comparison claim is made.

**Handover that counts:** a one-page transcription of the chosen example with page anchors, or an explicit decision to leave B01 as mathematical background rather than a baseline.

**Tracking:** [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2), [baselines](baselines.md), [source map](source-map.md).

### 4.2 B02 - L05 nonlinear reachability approximation

#### Example 1: two states, 60 stages

**Reported evidence:** general algorithm `0.05 s / 120 vertices / 4.62`; modified algorithm `0.01 s / 16 / 4.34`; nonlinear reference `120 / 4.68`. Printed data: `a=0.9`, `b=0.003`, `c=0.8`, `d=0.002`, `e=0.85`, `T=60`; nonlinear start `(410,300)`; linear start `(1,2)`; scalar control `|u(t)| <= 0.3`.

**Already in hand:** hash-identified L05 PDF; candidate `Volterra.m` (SHA-256 `c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1`); saved `4.fig` and `1.fig`; an independent 60-stage reconstruction that matches all saved general-linear polygons to floating precision; exact checks of the saved terminal polygons; a same-control candidate model-error enclosure with `L-infinity` upper bound `11.384829795848264`.

**Missing:**

- [ ] The exact `T0` grouping: the printed form is `2π / T√(ac)` without parentheses around the denominator. Confirm whether `T0 = 2π / (T sqrt(ac))` or `(2π/T) sqrt(ac)`.
- [ ] The reference trajectory samples `x̃(t)` used to build the time-varying `A(t)`, and the indexing correspondence between printed `t` and the candidate loop index.
- [ ] A justified coordinate map between the physical nonlinear start `(410,300)` and the linear start `(1,2)`. No shift, scale, reference offset or inverse transform is printed.
- [ ] The actual retention/support predicate and its tolerances for the 16-vertex modified construction.
- [ ] The versioned Table 1 driver that produced the saved figures, including the code revision, plot order and timing scope. The candidate's single `tic/toc` covers reference construction and plotting, not the two algorithm rows.
- [ ] The full text of L05 reference [6] (Bulaev, 2017), needed to assess the point-discard proof, plus a statement of whether it was the implementation source.
- [ ] Evaluated nonlinear, discretization and rounding bounds over a justified domain, if a physical enclosure claim is intended.

**Blocked:** Table 1 is numerically associated with saved figures but not reproduced from a versioned generator; the modified construction has no proved completeness argument; no nonlinear inclusion claim is possible.

**Handover that counts:** the original Table 1 driver and configuration, or the exact `T0`/reference/coordinate definitions with page anchors, or a declaration that the driver is unavailable (which keeps the result as a source-bound reconstruction only).

**Tracking:** [#4](https://github.com/butahlecoq/controlled-systems-lab/issues/4), [Example 1 dossier](l05-example1-source-dossier.md), [source check](issue4-volterra-source-check.md), [saved-figure audit](l05-saved-figure-audit.md), [candidate enclosure](issue4-volterra-enclosure.md), [primary-claim audit](l05-primary-claim-audit.md).

#### Example 2: four states, eight plotted sections

**Reported evidence:** general `4.19 s / 756 vertices / 40808.17`; modified `0.76 s / 153 / 34764.47`; nonlinear reference `436 / 47795.76`.

**Already in hand:** candidate `Dim4.m` (SHA-256 `f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a`), `ConvSM_mod.m`, `Simplex_Hull_mod.m`, `Approx_mod.m`; saved `2.1.fig`, `2.2.fig`, `2.3.fig`; independent enumeration of all `4^7 = 16384` corner-control histories. The general row is matched at `756 / 40808.16557488733`; the nonlinear row is matched at `436 / 47795.758789498876`; the active filter reproduces the general hull; the commented `Approx_mod` path gives `148 / 34421.17014411157`, not the printed modified row.

**Missing:**

- [ ] The revision and driver that produced `153 vertices / 34764.47`. The current active path does not; the commented `Approx_mod` call does not; a terminal-only reduction gives `142 / 32089.220837141474`.
- [ ] The stagewise reduction schedule and retention predicate actually used, including whether state constraints were active in the loop.
- [ ] The MATLAB release and `sortrows` tie behavior. The translated result is rank-order sensitive: stable ties give 148 vertices; a quicksort sensitivity check gives 150. The archived MATLAB was not run.
- [ ] The generating revision of the saved figures. The current script plots axes `(1,3,4)`, while `2.3.fig` is labelled `(1,2,4)`.
- [ ] The initial-coordinate convention: the source reference start is `(1,1,1,1)`, the plotted starts are `(1,-1,1,1)`, and the article prints nonlinear `(1,1,1,1)` versus linear `(1,-1,1,1)`.
- [ ] The common physical/deviation coordinate map and any omitted stage constraints.
- [ ] The timing scope for the two reported algorithm rows.

**Blocked:** the modified four-dimensional row is the only remaining unreproduced Table 1 cell. The source/figure revision mismatch also prevents a claim that the saved plots belong to the current script.

**Handover that counts:** the versioned driver/configuration that generated the modified row and the three figures, with its MATLAB release and any reduction parameters; or a declaration that it is unavailable.

**Tracking:** [#4](https://github.com/butahlecoq/controlled-systems-lab/issues/4), [candidate reconstruction](l05-example2-candidate-reconstruction.md), [active-filter audit](l05-example2-retention-audit.md), [reduction hypothesis](l05-example2-approximation-hypothesis.md).

### 4.3 B03 - L07 reachability and hull comparisons

**Reported evidence:** at `t=15`, baseline `5.466993 s / 158399 simplex iterations` versus modified `3.583817 s / 116497`; hull construction for 5000 points from Normal, Uniform and Sphere sampling in dimensions 2-5; MATLAB R2014a, Intel Core i7 at 2.7 GHz.

**Already in hand:** the L07 report; recovered hull/simplex routines A15/A16, A24-A34 and Python relatives W05/W06; a 2D QuickHull implementation in the modern library; the comparison-program fixture ladder (`250`, `1000`, `5000` points; dimensions `2, 3, 4, 8, 16`) as a planning decision.

**Missing:**

- [ ] The exact 5000-point clouds and all intermediate arrays for dimensions 2-5.
- [ ] The RNG algorithm, version, draw order, dtype and seeds. The publication reports none.
- [ ] The timing scope: whether vertex generation, conversion, plotting and repeated solves are included in `5.466993 s` and `3.583817 s`.
- [ ] The generating revision of the baseline and modified algorithm rows, and the exact machine/library configuration beyond "MATLAB R2014a, i7 2.7 GHz".
- [ ] The full result arrays behind the 158399/116497 iteration counts.

**Owner disposition (2026-10-20):** the comparison program does **not** seek the exact historical point sets, a replay in the original MATLAB/Python software, or the published runtime/iteration row. B03 is an **algorithm comparison**: translate the baseline and modified hull algorithms from the archived MATLAB/Python sources into C++, run them with the modern algorithms on bit-identical shared fixtures, and compare quality and performance. The exact artifact pair behind the L07 baseline and modified rows is not yet named; selecting it is the first port step. The missing items above remain missing for a future historical replay, but they do not block this comparison.

**Historical replay:** not reproducible from the current evidence and not required for B03's algorithm comparison. The published row remains immutable reported context; no B03 reproduction is claimed.

**Handover that counts:** none for the algorithm comparison. A handover would only matter if historical replay later becomes a separate goal.

**Tracking:** [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [baselines](baselines.md), [hull/V-H coverage](comparison-hull-vhv-coverage.md), [legacy runnability](comparison-legacy-runnability.md).

### 4.4 B04 - L11 nominal terminal control, n=4, T=16

**Reported evidence:** terminal point `(1200.7, -22.929, 450.2, -7.709)`, objective `30.899`, runtime `0.4 s`; three nonlinear witness rows in the published counterpart.

**Already in hand:** L11/A14, A41 and R40 tables; three saved witness histories A39; nonlinear replay kernel A40; a public replay check with 120000 paired samples; inferred effective actions under the sourced `B`; the exact terminal-invariant audit and the unrestricted terminal-plane lower bound `160.880653946`.

**Missing:**

- [ ] The canonical T=16 `U` rows and their mapping to the three saved witnesses. The saved histories do not share a fixed first action, and the original optimizer variables were not recovered.
- [ ] The first-action convention and stage indexing: the article indexes controls 0-15, while a later p. 13 expression begins at index 1.
- [ ] Every stagewise state/stock bound and the numerical control bounds. Only the flow box `1176 <= x1 <= 1224`, `432 <= x3 <= 468` is printed; `[-1,1]` is a hypothesis from a table/recollection, not a printed numerical input.
- [ ] The generating project/revision and the saved arrays for `x0`, every `A/B/D`, the objective and the reported terminal point.
- [ ] Coefficient and unit authority: the printed `B=(17,0,-12,0)` versus the saved-run `B=(2208/110,0,-1152/110,0)`; Table 1 `c2=-1675, c3=2250` versus A40 `c2=-6700, c3=9000` (a factor of four); the unrounded coefficients behind the terminal invariant.
- [ ] The frozen-controller generator and objective version. The saved row prints `368.45` while the saved objective is `368.609780868`; the replay ends at `99.99 s`, not `100 s`.
- [ ] A source-backed reconciliation of the displayed model with the reported optimum. The printed model requires `12*x2 + 17*x4 = -2122.7` at the terminal point, but the reported point gives `-406.201`; the unrestricted terminal-plane minimum is `160.880653946`, above the reported `30.899`.
- [ ] Permission/provenance for any release of the original project or arrays.

**Blocked:** B04 remains non-executable and cannot be the first end-to-end reproduction. The three saved witnesses are scoped evidence, not a canonical run.

**Handover that counts:** any one of (a) the original T=16 MATLAB project/configuration with `U` rows, stage bounds and revision identity; (b) a complete owner-authenticated model/input package that names the generated row and its deviations; (c) a declaration that no such artifact exists, which permits a corrected-track B04 variant under a new ID while preserving the historical record.

**Tracking:** [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10), [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2), [restoration](b04-restoration.md), [T=16 source audit](b04-t16-source-audit.md), [saved witnesses](b04-saved-witnesses.md), [parameter cross-check](b04-parameter-crosswalk.md), [version matrix](publication-source-matrix.md).

### 4.5 B05 - L08 adaptive optimal control, T=16

**Reported evidence:** ten Table 2 rows; one open-loop variant `0.4 s`, adaptive simulation `10 s`; nonlinear terminal costs `48.261`, `39.837`, `51.021`, `44.228`, `46.339`, `37.935`, `48.906`, `45.372`, and linear `47.988`; reference `(1200,0,450,0)`.

**Already in hand:** L08 draft and the published Part II PDF; mapping of the ten Table 2 policy labels to their embedded equation streams E01-E10, with stream hashes and byte counts; confirmation of the row grouping and terminal/objective tuples.

**Missing:**

- [ ] The canonical optimizer source and the historical inputs: model arrays, `x0`, constraints, objective weights, control catalogue and adaptive policy schedule.
- [ ] The adaptive semantics: how the horizon shrinks, what is observed, whether the simulation is closed-loop with a measurement model, and how replanning is timed.
- [ ] Seeds, solver tolerances, backend versions and thread count.
- [ ] The generating revision and run provenance; the table mapping resolved labels, not the run.
- [ ] The remaining 75 of the 85 `Equation Native` streams and the figures in the draft, if the complete draft is to be used as evidence.
- [ ] The timing decomposition between one optimization solve and the full adaptive simulation.

**Blocked:** B05 rows cannot be reproduced, and an adaptive-versus-open-loop comparison is not fair without the policy and timing semantics.

**Handover that counts:** the original adaptive project/config with saved rows, or the adaptive algorithm description and run parameters with page anchors; otherwise a declaration that only the published table is authoritative.

**Tracking:** [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2), [baselines](baselines.md), [L08 embedded equations](l08-embedded-equations.md), [version matrix](publication-source-matrix.md).

### 4.6 B06 - L09 five-step unconstrained minimax

**Reported evidence:** `3125` plans; worst-case `10.11`; nonlinear state `(30, 6.0345, 20, 4.4731)` and cost `9.049`; runtime `300 s`; unique linear minimax sequence `(-0.3, 1, 0, 0, 0.3)` for control indices 0-4.

**Already in hand:** the hash-identified L09 PDF; the visually confirmed control sequence and its stated application to the nonlinear system; exact rational checks of the printed nonlinear cost (`9.049`) and the linear table center (`10.11`); the shared model, actions and disturbance matrix `D(t)`.

**Missing:**

- [ ] The numerical disturbance set `W(t)`: bounds, vertices or another set description, including stage dependence. The paper prints `w(t) in R^2` and `D(t)` only; the general assumption that `W(t)` is a convex, closed, bounded polyhedron does not supply its values.
- [ ] The historical run configuration and solver tolerances behind the `3125`-plan enumeration and the `10.11` worst case.
- [ ] The exact objective implementation and any unrounded terminal state.
- [ ] The generating revision, if the `300 s` timing or the nonlinear row is to be reproduced.

**Blocked:** the reported worst case cannot be independently recomputed; the nonlinear `9.049` is validated only as arithmetic at the printed coordinates.

**Handover that counts:** the disturbance set and run configuration, or a declaration that the numerical uncertainty set is not recoverable. A corrected-track B06 reference may use an explicitly named new disturbance set, but must not be called a reproduction.

**Tracking:** [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [B06 audit](b06-source-audit.md), [baselines](baselines.md).

### 4.7 B07 - L10 five-step constrained minimax

**Reported evidence:** `3125` plans, `365` robustly feasible; optimal plan `(1, 0, 0.3, -0.3, 0)`; worst-case `9.77`; nonlinear state `(30, 5.81, 20, 4.39)` and cost `8.82`; runtime `66 s`.

**Already in hand:** hash-identified L10 PDF; a non-executable historical manifest `benchmarks/scenarios/b07-historical.json`; printed matrices, actions, flow bounds and terminal criterion; objective checks at the displayed states.

**Missing:**

- [ ] The numerical disturbance set `V1(t)`: bounds or vertices, stage/inter-stage dependence. The paper prints `D(t)` and the output, not `V1(t)`.
- [ ] The initial-stock reconciliation: equations (5) and Table 1 imply `(305, 205)`, while the numerical example prints `(302, 207)`.
- [ ] The per-stage physical intervals `delta_T(t)` and the meaning of the printed `-10/T` stock-flow entries relative to `T=5`, the 100-second interval and `delta_T(t)`.
- [ ] The numeric stock-coordinate bounds. The example prints flow-coordinate bounds only, while the method assumes bounded state polytopes.
- [ ] The unrounded linear terminal row. The displayed two-decimal state gives at most `9.74728232` under nearest-hundredth rounding, which cannot produce the printed `9.77`.
- [ ] The generating project/revision and the full run configuration.

**Blocked:** the manifest stays non-executable; the `365` count and `9.77` cannot be independently recomputed.

**Handover that counts:** the disturbance set plus the stock/time conventions and generating revision, or a declaration that B07 is not recoverable as a unique historical scenario.

**Tracking:** [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [B07 audit](b07-source-audit.md), [historical manifest](../../benchmarks/scenarios/b07-historical.json), [baselines](baselines.md).

### 4.8 B08 - L04 four-step minimax

**Reported evidence:** `625` plans; optimal plan `(0.6, 0.6, -0.3, 0)`; worst-case `67.12`; nonlinear state `(1200.139, -2.294, 450.406, -16.254)` and cost `14.048`; runtime `37 s`.

**Already in hand:** the complete displayed model, disturbance box `|w1| <= 0.1 + 0.1t`, `|w2| <= 0.1 + 0.3t`, actions and criterion; two independent references: a floating enumeration of `625 x 256` plan/corner pairs with minimum `67.150601101407`, and an exact rational audit with squared worst case `112730080707/25000000` and three exact minimizers.

**Missing:**

- [ ] The original unrounded arrays and the generating MATLAB project.
- [ ] The nonlinear plant integration, time grid and trajectory behind the `14.048` row. The printed nonlinear state evaluates to `16.42069149` under the printed Euclidean criterion.
- [ ] The actual criterion or coordinate convention used for the nonlinear row.
- [ ] Any additional constraint that would make the published plan unique. The printed rational data produce three exact ties.

**Blocked:** the linear displayed-data reference is complete; the nonlinear row and the uniqueness claim are not reproducible. B08 is the closest baseline to an executable comparison but is not a full reproduction.

**Handover that counts:** the generating project with the nonlinear integration and original arrays, or a statement that only the printed displayed-data reference is authoritative.

**Tracking:** [#1](https://github.com/butahlecoq/controlled-systems-lab/issues/1), [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [exact audit](b08-displayed-exact-audit.md), [version matrix](publication-source-matrix.md), [reference record](reference-b08.json).

### 4.9 B09 - L13 adaptive minimax, T=4

**Reported evidence:** reference `(60,0,24,0)`; simplified open loop `115.79`, simplified adaptive `22.658`; original open loop `25.295`, original adaptive `22.657`; nine actions over four steps, then shrinking horizons.

**Already in hand:** hash-identified L13; A08 `Minmaxclosedloop.m`, A09 `Minmaxopenloop.m`, A10 `results.mat`; a saved-workspace trace showing A10's controls and endpoint differ from the published row, while its saved `J` agrees with A08's unsquared open-loop expression.

**Missing:**

- [ ] The exact publication-generating source revision and the saved arrays behind each Table 2 row.
- [ ] The original numerical errors, nonlinear plant integration and row-to-control/history mapping.
- [ ] The actual criterion implementation: L13 prints a plain Euclidean norm and gives `20.792787211` at the printed original-adaptive state; A09 adds `(2.5*x4 - x2)^2` and gives `22.676915575`; A08 uses an unsquared `(x3 - 24)` term in one reporting expression, which cannot distinguish the variants when `x3 = 24`. None of the recovered expressions reproduces the reported `22.657` exactly.
- [ ] The adaptive error bounds and the shrinking-horizon schedule.
- [ ] A10 provenance: which revision produced it, and why its controls `(0.75, 0.75, -0.5, -0.5)` and final stocks differ from the published row.
- [ ] Any authority for the `22.657` row beyond the printed table.

**Blocked:** B09 rows and the adaptive optimality claim remain unreproduced; A08-A10 are related evidence, not the canonical run.

**Handover that counts:** the generating revision plus arrays/plant integration/criterion, or a declaration that A08-A10 are the closest surviving artifacts and the published row is authoritative.

**Tracking:** [#1](https://github.com/butahlecoq/controlled-systems-lab/issues/1), [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2), [version matrix](publication-source-matrix.md), [A10 trace](l13-a10-saved-criterion-trace.md), [displayed-criterion audit](l13-displayed-criterion-audit.md), [baselines](baselines.md).

### 4.10 R29 - zonotope example

**Reported evidence:** 16 transitions, four states, scalar control `|u(t)| <= 1`, `A`, `B`, initial zonotope center `(1150, 119600, 430, 44720)` and generators `diag(20, 500, 10, 300)`. The paper reports no terminal objective or optimizer-family certificate.

**Already in hand:** public R29 PDF, private A21 copy and editable A22 TeX source; a corrected scalar-input reference with exact-rational unreduced propagation and per-stage checks; the two printed editorial anomalies are documented.

**Missing:**

- [ ] Authorial intent and the actual run inputs for the printed four-component `c_2=(0,0,0,0)^T` and `l_1=(1,1,1,1)^T`, which cannot be multiplied by the printed `B` under the stated scalar control.
- [ ] The objective, terminal target and history-preserving relation needed for any optimizer-family comparison. The example supplies reachability data only.
- [ ] Saved outputs, the generating code revision and the timing scope.
- [ ] A source match to A04 `Zonotope.m`: its active example is three-state, five-step and uses a `3x2` input matrix, so it is not the R29 run.

**Blocked:** only a corrected-track reference is possible; the historical run and any complete-family claim remain open.

**Handover that counts:** the original R29 script/configuration with the intended control zonotope, or confirmation that the printed four-component objects are a typo and the scalar interpretation is authoritative.

**Tracking:** [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8), [R29 input audit](zonotope-paper-input-audit.md), [corrected reference](r29-corrected-scalar-reference.md).

### 4.11 Ellipsoidal toolbox comparison - APP-04

**Reported evidence:** APP-04 has a native directional-ellipsoid route and a saved three-case report. The optional external ET comparison was not executed.

**Already in hand:** the native route, its contract, installed consumer and saved report; A05 `ELL_OD.m` and A23 study notes.

**Missing:**

- [ ] A pinned Ellipsoidal Toolbox version and a runnable environment with its CVX/MPT3/MATLAB dependencies.
- [ ] The `ell_enclose` implementation referenced by A05. It was not located in the scanned archive.
- [ ] The exact ET inputs, configuration, outputs and an independent inclusion certificate.
- [ ] A statement of whether the ET comparison is required at all, or remains optional context.

**Blocked:** no external ellipsoidal comparison can be claimed. This does not block the native APP-04 route.

**Handover that counts:** a pinned ET version plus inputs and an inclusion checker, or a decision to keep the ET comparison out of scope.

**Tracking:** [#34](https://github.com/butahlecoq/controlled-systems-lab/issues/34), [approximation coverage](comparison-approximation-coverage.md), [ellipsoidal comparison](ellipsoidal-comparison.md).

### 4.12 Document-level and execution inputs

These are not separate baselines, but they block specific evidence claims.

| Item | What is missing | Why it matters |
|---|---|---|
| L03 chapter draft | Formula images and the suspicious Step 2.2 compatibility sentence; the original DOCX must be inspected with its formula objects rendered | The extracted text contradicts the baseline wording on whether a compatible point is added or declared redundant ([algorithm inventory](algorithm-module-inventory.md)) |
| L06 explanatory report | Image-based equations that paragraph extraction does not recover | L06 cannot be used as a mathematical source; L07 is the current authority |
| L08 draft | 75 of 85 `Equation Native` streams and the figures | Only Table 2 labels are audited; complete draft evidence is not |
| L11 supplied draft | Table/figure placeholders in the local PDF | The published R40 counterpart supplies Table 2, but the draft alone is incomplete |
| L12 draft | Selected embedded equations were checked, but not a unique original object for the full criterion | The first-action range contradiction and model/result mismatch remain |
| A06 Pascal | `BIBTUSH`, `DIALOGS`, `term`, `funfnx` units; no Free Pascal on the host | Native execution and a faithful projection port are blocked |
| A17 GeoCalcLib | External `libgeocalc` MEX dependency | The V/H enumeration adapter cannot run natively |
| Native environments | MATLAB/Octave, Free Pascal and Python 2 are absent on the audit host | Native-original runs are unavailable; C++ translations are the comparison route, with Python 3 usable for behavioral transcription |

## 5. Cross-cutting metadata that is missing for almost every case

Even where the numbers are transcribed, the following fields are usually absent. They should be requested together with any recovered project.

| Field | Why it is required | Typical state |
|---|---|---|
| Generating revision | A hash-identified article is not a hash-identified executable; the report must name the code revision that produced the row | Missing for B02-B09 |
| Original unrounded arrays | Printed decimals are not enough to reproduce a solver run or a terminal row | Missing for B03, B04, B08, B09 |
| Seeds and PRNG identity | Seed alone does not promise replay across languages; algorithm, version, draw order and dtype are needed | Missing for B03; absent for W05/W06 demonstrations and W13 |
| Solver/backend versions and tolerances | A reported optimum or timing depends on them | Missing for all baselines |
| Time grid, units, index convention | Zero- versus one-based control indexing and physical intervals change the model | Missing or contradictory for B04, B05, B07, B09 |
| Coordinate map | Physical and deviation/linear coordinates are not interchangeable | Missing for L05; ambiguous for B04/B09 |
| Objective implementation | The printed formula and the implemented expression can differ | Contradictions in B04, B08, B09 |
| Timing scope | End-to-end, solve-only and simulation-only durations are not comparable | Missing for B02, B03, B05, B06 |
| Provenance and permission | Source identity, authorship and redistribution rights | Missing for every private artifact |

For B03, the run-recovery fields above (original clouds and arrays, seeds, historical solver versions, timing scope, and the generating revision of the reported row) are needed only for a historical replay, which is not required. The algorithm comparison does not use them. Source identity and provenance for the translated algorithm files, plus the model and fixture semantics the port implements, are still required for a faithful C++ port.

## 6. What is already recovered and should not be requested again

- The standalone `OpenLoopControl.py` gap is closed by W09 (SHA-256 `abf68dc0d493c5a90837a5cfe78929b8a972de2453465e5b11dad129fe75e4a4`). What remains is its link to a canonical publication run, not the file.
- A distinct minimax-adaptive MATLAB implementation is recovered as A08/A09, with a saved workspace A10. The gap is source-to-row matching, not availability.
- The B08 displayed-data reference is complete and independently checked, including the three exact ties. The missing part is the unrounded generator and nonlinear row.
- The L05 saved figures and the general/nonlinear rows of both examples are reconstructed and checked. The missing part is the versioned driver and the modified four-dimensional construction.
- The B04 three saved witnesses, their replay kernel and the terminal-invariant audit are complete. The missing part is the canonical T=16 optimizer input.
- The published counterparts R40 (B04) and the Part II PDF (B05) supply tables absent from the local drafts.
- The B06 control signs and printed cost centers are resolved. The missing part is the disturbance set.

## 7. Handover protocol

The smallest useful handover is one artifact plus an identity statement. A complete package is not required.

Preferred record for each item:

```text
Artifact ID:            B04 / B06 / L05-Ex2 / ...
File or archive path:
Byte count:
SHA-256:
Produced which row:     article, table, row and printed value
Known deviations:       changed x0, B, criterion, units, index convention
Environment:            MATLAB/Octave version, toolboxes, OS, hardware
Permission:             private reference only / derived facts publishable / redistribution allowed
If unavailable:         state "unavailable" and the search scope already covered
```

Handling rules:

- Keep originals local. Do not attach archive source to a public issue or PR; a private path, an opaque source ID and a hash are enough.
- A screenshot or transcription is useful, but it is labelled as a transcription, not as the generating executable.
- The project verifies hashes and byte counts before reading, records only derived non-source facts, adds regression tests, and never silently "repairs" a historical value.
- If an item is unavailable, one sentence is a valid outcome. The case then moves to the corrected track under a new ID, and the historical row remains unchanged.
- If a deeper search is possible, authorize the scope explicitly: containers (`.rar/.zip/.7z`), MEX/binaries, Simulink `.slx` internals, MAT/MCOS objects, or unregistered archive neighbours.

## 8. Reviewer decision sheet

For each row, one of `supply`, `unavailable`, `authorize deeper search`, or `not required` is enough to close the review item.

| Artifact | Decision | Notes |
|---|---|---|
| B01 numerical instance |  |  |
| B02/L05 Example 1 driver, `T0`, coordinates |  |  |
| B02/L05 Example 2 modified driver |  |  |
| B03 seeded clouds and run scope (historical replay only) | Not required | Owner, 2026-10-20: compare C++ translations of the baseline and modified algorithms on shared fixtures; do not reproduce the historical sets, software run or timing row |
| B04 T=16 project and `U` rows |  |  |
| B05 adaptive inputs and policy schedule |  |  |
| B06 `W(t)` disturbance set |  |  |
| B07 `V1(t)`, stock and time conventions |  |  |
| B08 generating revision and nonlinear row |  |  |
| B09 generating revision and criterion |  |  |
| R29 control-zonotope intent |  |  |
| ET version and `ell_enclose` |  |  |
| Document-level equations and Pascal units |  |  |

Additional decisions:

- [ ] Authorize a deeper archive extraction pass, or confirm that the current search boundary is final.
- [ ] Confirm whether derived facts (hashes, counts, printed anchors) may be published when the source cannot be.
- [ ] Confirm that an "unavailable" disposition is acceptable for a baseline that cannot be recovered.
- [ ] Identify a single reviewer/owner for future source handovers.

## 9. Closure criteria for this review

This dossier can close when every artifact in section 4 has one of these dispositions:

1. **Supplied** - a hash-identified file or owner-authenticated package is registered and linked to the relevant issue.
2. **Declared unavailable** - the owner states that no accessible copy exists; the baseline is recorded as unrecoverable and a corrected track may proceed separately.
3. **Deeper search authorized** - the reviewer names the additional scope and a target date; the item stays open with that scope.
4. **Not required** - the owner narrows the comparison goal and the historical artifact is unnecessary; the algorithmic comparison proceeds on shared synthetic fixtures without a reproduction claim.

Closing this review does not close #2, #4, #6, #10 or #8. Those issues retain their own scientific acceptance criteria. It only establishes which inputs exist and which do not.

## 10. Search boundaries and limits

- The source register covers the supplied corpus L01-L31 and the selected archive sources A01-A45 and W01-W14. Raw originals, full directory listings and personal source metadata remain local.
- The larger archive scans saw 8,982 files in the first targeted follow-up and 8,935 files in the later L04/L13 version trace. These are different bounded scans, not exhaustive enumerations.
- The later audit did not unpack every `.rar/.zip/.7z` container, inspect native MEX/binary code, load Simulink models, parse every MAT/MCOS object or read every image. Unregistered neighbours exist and are listed in the [legacy runnability audit](comparison-legacy-runnability.md).
- No historical MATLAB, Pascal or Python 2 program was executed. No benchmark or timing measurement was made for this dossier.
- The absence statements are scoped to the searches recorded in the linked audits. They are not proof that the owner's wider archive or another machine holds no copy.
- The publication values and raw rows remain immutable; any repair requires a separately identified corrected reference and an issue that explains the change.

## References

- [Published baselines](baselines.md)
- [Source map](source-map.md)
- [Archive follow-up](archive-followup.md)
- [Works follow-up](works-followup.md)
- [Publication-to-source version matrix](publication-source-matrix.md)
- [Legacy runnability and comparison fairness](comparison-legacy-runnability.md)
- [B04 restoration](b04-restoration.md), [T=16 source audit](b04-t16-source-audit.md), [saved witnesses](b04-saved-witnesses.md), [parameter cross-check](b04-parameter-crosswalk.md)
- [B06 source audit](b06-source-audit.md), [B07 source audit](b07-source-audit.md)
- [L05 Example 1 dossier](l05-example1-source-dossier.md), [candidate source check](issue4-volterra-source-check.md), [saved-figure audit](l05-saved-figure-audit.md), [candidate enclosure](issue4-volterra-enclosure.md), [primary-claim audit](l05-primary-claim-audit.md)
- [L05 Example 2 reconstruction](l05-example2-candidate-reconstruction.md), [retention audit](l05-example2-retention-audit.md), [reduction hypothesis](l05-example2-approximation-hypothesis.md)
- [L08 embedded equations](l08-embedded-equations.md), [A10 criterion trace](l13-a10-saved-criterion-trace.md)
- [R29 input audit](zonotope-paper-input-audit.md), [corrected scalar reference](r29-corrected-scalar-reference.md)
- [Approximation coverage](comparison-approximation-coverage.md), [ellipsoidal comparison](ellipsoidal-comparison.md), [hull/V-H coverage](comparison-hull-vhv-coverage.md)
