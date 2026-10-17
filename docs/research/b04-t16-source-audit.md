# B04 T=16 source audit in the supplied research corpus

Date: 2026-10-18. Scope: focused, read-only follow-up for the live [issue #10 acceptance criteria](https://github.com/butahlecoq/controlled-systems-lab/issues/10), limited to the already supplied research corpus. Goal: locate the canonical T=16 control rows, first-action convention, stage bounds and generating revision. This is a bounded search, not proof that the owner's wider archive contains no such source.

## Finding

No new source in this corpus satisfies issue #10's restoration criteria or changes the B04 historical model. I did not find canonical T=16 `U` rows, a first-action declaration tied to the B04 run, full stagewise bounds, or a generating project revision. The repository's existing source audit remains authoritative for the recovered evidence: three saved witness histories, inferred effective actions, and a nonlinear replay kernel do not recover the optimizer's original `U` variables or their row mapping ([saved-witness report, source identities and limitations](b04-saved-witnesses.md#source-identities-and-anchors); [restoration report, completion gates](b04-restoration.md#completion-gates)).

The publisher's [article PDF](https://sciencejournals.ru/issues/teorsist/2019/vol_2019/iss_1/TeorSist1902009Kalev/TeorSist1902009Kalev.pdf) gives the numerical example's scalar control as `u(t) in R^1`, its flow limits as `1176 <= x1 <= 1224` and `432 <= x3 <= 468`, and its horizon as `T=16`. It does not give numerical `U` rows or numerical stock bounds. The article also indexes controls 0–15 while a later p. 13 expression begins at index 1; this does not resolve whether the first action is fixed. The manifest interprets the flow box as applying at stages 0–16, but that stage convention is not independently recovered from an executable T=16 project ([restoration report](b04-restoration.md#restored-problem); [saved-witness report, indexing note](b04-saved-witnesses.md#remaining-authority-and-bounded-recovery)).

## Focused inspection and source anchors

I searched source/configuration text under the permitted tree for the displayed B04 initial-state signature (`1216.904`, `119500`, `438.787`, `45300`), coefficients (`17`, `-12` in context), horizon/timing clues, and flow-box values. This produced no matching B04 project. The few relevant candidate sources below were read or parsed as inert data; no MATLAB, Simulink, MEX, archive payload, or other historical code was executed.

| Audit ID | Identity and observation | Relevance |
|---|---|---|
| R1 | 2,343 bytes; SHA-256 `184097076b608e74f107d19403fa69dad677edc97091140e29b7b4ea74ccd8d5`. The source has a 2-state example, `T=5`, `A=[1 0;-1 1]`, `B=[0.5 0]`, and `U=1`. | Not the 4-state, 16-transition B04 experiment; it provides no B04 rows or bounds. |
| R2 | 3,707 bytes; SHA-256 `36dae6f19d25083352d752a1967019275c1f0432a5eb0140e0ff3ffb0de1b667`. The source uses `T=10`, a different four-state matrix/input matrix, action polytope `P`, and initial point `(30.5,305,20-1/3,197)`. | A distinct reachability experiment, not canonical B04. |
| R3 | 894 bytes; SHA-256 `cf8e977b6b0bbd85db0b618d0fd472de02264b4378acb6112b8e35a85de18a4a`. The source has a 2-state, 5-step example with a different `A`, `B`, `Q`, `X0`, and target. | Unrelated low-dimensional demonstration. |
| R4 | 8,287 bytes; SHA-256 `09c5c21770b9b8429ab22ebbb126a291ac05c42d315ec62c61697dfb5f4eaa3f`. The image shows a generic `u(t)` staircase over 0–9, with values in `[-1,1]`. | Nine displayed intervals and no B04 state/model/provenance; does not establish B04's control bound or rows. |
| R5 | 5,032 bytes; SHA-256 `604be17367be0880704d74bd10d54be039b40972d890f6518919195a1e0e5153`. Inert MAT header inspection reports one variable `D`, shape 188-by-6, double; its values do not contain the B04 initial state or displayed flow bounds. | No B04 control histories or source metadata exposed. |
| R6 | 82,825 bytes; SHA-256 `0fd0168704c2ea862c716b03dc8e6d8a6a0f52124b296e53fa8df251883cb7e4`. Read as ZIP/XML only. Metadata says MATLAB R2014a and revision `1.330`, last modified 2015-02-04. Block parameters refer to engine quantities such as `Km_nom`, `Pp_nom`, `dT_kong`, `dT_kono`, disturbance terms and `Tm`; the model's time range is 100. It contains none of the B04 initial-state tuple or `B=(17,0,-12,0)`. | No evidence links this model to the B04 paper run. Its revision cannot be presented as B04's generating revision. |

A numeric match or shared author/subject vocabulary alone is not provenance. The only T=16 adaptive sources already in the repository's selected-source register are A02/A03, documented as having a different initial mixture, `B`, and objective; they remain distinct candidates rather than canonical B04 sources ([archive follow-up](archive-followup.md#b04-source-gaps-narrowed-canonical-project-still-unresolved); [source register](archive-selected-sources.json)).

## Search boundaries and exclusions

- The scan was restricted to the supplied research corpus. I did not rescan other archive packages, search the web for an unpublished project, or infer content from file names outside this corpus.
- The broader extension-based text search included `.m`, `.txt`, `.mdl`, and `.slx` files in the tree; vendor/library matches were not treated as project evidence. Opaque or non-text content was not converted into source text.
- I did not unpack bundled third-party archives; inspect native MEX/binary code; exhaustively parse all MAT/FIG/Office/Simulink binary internals; inspect every image; or recover data from external drives/cloud. The inspected SLX file was read as a ZIP/XML container only, not loaded in Simulink. The inspected MAT file was checked by its variable table and numeric content only.
- Prior bounded searches and exclusions remain as recorded in [archive-followup.md](archive-followup.md) and [b04-saved-witnesses.md#remaining-authority-and-bounded-recovery](b04-saved-witnesses.md#remaining-authority-and-bounded-recovery), including opaque MCOS/polyhedral MAT data and embedded Office equations.

## Effect on issue #10

This audit adds no admissible control history, stage-constraint source, first-action convention, or B04-generating revision. It does narrow the supplied corpus: the apparent T=10/T=5 reachability code, a generic nine-interval plot, an unrelated numeric MAT workspace, and the R2014a engine Simulink model cannot fill those gaps. The displayed-model terminal-invariant contradiction and the unresolved canonical restoration gate remain unchanged ([live issue #10](https://github.com/butahlecoq/controlled-systems-lab/issues/10); [exact consistency analysis](b04-restoration.md#exact-inconsistency-and-lower-bound)).

Do not close issue #10, change `b04-historical.json`, promote `[-1,1]` from hypothesis, or claim reproduction on the basis of this negative, bounded search. The next evidence that could satisfy the gate is the original T=16 MATLAB project/configuration or a complete owner-authenticated model/input package with the `U` row identity, sampling/index convention, every stage constraint, and revision provenance.
