# Issue #1 source and criterion version trace

The [2026-11-10 owner decision](owner-reference-decisions-2026-11-10.md) supersedes the historical-reproduction closure gate. L04 uses the Euclidean objective without a `14.048` target; L13 uses the squared synchronization objective without a `22.657` target. The source-to-run limitations documented below remain historical facts.

Initial audit date: 2026-10-18. Scope: bounded source/version follow-up for B08/L04 and B09/L13. This is not a reproduction of either publication run. No historical MATLAB source was executed, no continuous nonlinear plant was integrated, and no benchmark was run. The 2026-11-02 follow-up independently enumerates and replays one local discrete-model candidate; that transcription is separately scoped below.

## Result

The publication-level criterion statements are identifiable from the hash-identified articles, and nearby hash-identified MATLAB files expose materially different criterion expressions. The local archive now contains a source-correlated reconstruction candidate for the L13 original-adaptive row: a hash-identified A08 program's initial state and plotted trajectory match a saved MATLAB figure, whose unrounded terminal coordinates reproduce the published row under A08's synchronization-augmented reporting expression. This substantially narrows the L13 discrepancy, but no saved console output or explicit figure-to-Table-2 pointer proves that this exact run generated the table. The B08/L04 source-to-row gap remains open.

## B08 / L04

The selected-source register does not list L04 as an archive-selected algorithm source. The repository inventory identifies the supplied article as L04, 390,884 bytes, SHA-256 `6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f` (`docs/research/inventory.json`, `id=L04`). A full local archive PDF hash scan found the same bytes in two local article copies, one in the article folder and one in its TeX subfolder; it therefore verifies the identity of these article copies, not the generator of the numerical rows.

The archive also has an editable article manuscript at archive-relative path `Публикации/Минимакс/Unconstrained for AaRC/Paper/Shorikov_Kalev_AiT.tex` (37,412 bytes; SHA-256 `7dfcd12b5f946d459411ba7467d6a176d42ab33c20d56ce860fb8477c6ce956f`). Its lines 147 and 307 state the terminal criterion as the unweighted four-coordinate Euclidean norm to `(1200,0,450,0)`; its lines 320 and 335 reproduce the nonlinear terminal coordinates and reported `14.048`. This is primary article-manuscript evidence for the criterion and the printed row. It does not identify a MATLAB revision or saved run data. The already recorded displayed-row calculation gives approximately `16.42069149` for the printed nonlinear coordinates under that criterion; the original reported value remains unchanged (`docs/research/publication-source-matrix.md`, B08 row; `docs/research/baselines.md`, B08 section).

The [2026-11-10 draft uncertainty follow-up](issue1-draft-uncertainty-revision.md) now distinguishes this manuscript and its matching PDF/embedded figure from published L04: they report a different uncertainty matrix and linear cost `56.433`, rather than the later time-varying-bound result `67.12`. The shared nonlinear row and `14.048` discrepancy remain unresolved; the follow-up supplies exact row-offset checks without claiming a generating-run link.

The [fuller-dissertation archive follow-up](issue1-dissertation-archive-followup.md) records a distinct 38,966-byte AaRC manuscript variant that contains the published `67.12` linear row, plus nearby MATLAB candidates and a bounded saved-figure scan. It does not link the manuscript or candidates to the published nonlinear run; `14.048` remains unexplained.

The selected-source register contains W07, the separate notebook at SHA-256 `882ebb911cd495d5f724836653f8eeca93ef94d91282d5158d623441f8adbacd` (`docs/research/works-selected-sources.json`), whose data differ from L04. It is not a source-to-row match.

### Newly checked adaptive-project autosave candidate

The owner-supplied local archive contains an unregistered sibling autosave, `papers/Minimax/Adaptive_Samara/Minmaxclosedloop.asv` (4,017 bytes; SHA-256 `a1aa4ee264c93b283da7f9e17edd9dc3a08ab7cb54ba6e56b777e07567fd8d9b`). It is a private, ignored input and is not copied into this repository. Its bytes are not in the selected-source register; only the nearby `Minmaxclosedloop.m` A08 file is registered there. The autosave has an older fuel-model parameter block (`K=8/3`, `P=132000*4`, `I=320`, `T=4`) and its terminal reporting expression at lines 81 and 127 contains the unsquared term `(mg-450)`/`(mg1-450)`. A08's later L13 parameter block instead uses `K=2.5`, `P=30240`, `I=360`, and a different objective expression. The sibling path and parameter differences establish a nearby source variant, not version-control ancestry or a generating-run link.

The autosave's line-22 initialization evaluates to approximately `(1177.6301080697162,120330,462.4201995038153,44880)` under its literal parameter block. That differs from L04's published B08 discrete initial vector `(1182.074,119560,459.832,45260)` in the source matrix. It declares nine candidate control values, but its expansion loop uses only the first seven; even those differ from L04's five-action catalogue. The autosave therefore does not supply the missing source-to-row match or reproduce either disputed terminal row. It is a concrete, hash-identified lead for future owner/archive searches, and does not justify changing the published values. No execution was attempted; this static comparison does not reproduce the MATLAB run.

### Unconstrained MATLAB replay candidate

A second, stronger local candidate is the ignored pair `papers/Minimax/Unconstrained/Minmaxopenloop.m` (3,244 bytes; SHA-256 `bc45e3956992183ca10fef0b878116539c6888be2ccec4fe888d7e6d25bf26d6`) and `program.m` (1,388 bytes; SHA-256 `835d8908a8b1422aa783d15a3a66245a67c5b6f1ef3a6b7b810628155b820d8b`). `Minmaxopenloop.m` builds the finite four-stage plan catalog, computes a worst-case terminal score using the printed Euclidean criterion (line 48), selects a plan, then calls `program` (lines 68–78, 97–100). `program.m` applies the selected plan to the nonlinear fuel model and reports the same squared Euclidean criterion (line 43). This is a connected linear-minimax/nonlinear-replay workflow in the local archive and a concrete source lead for the L04 criterion.

It still does not establish that these bytes generated L04's rows. The candidate linear driver uses `X0=(1194,119520,453.19,45280)`, `B=(20.073,0,-10.473,0)`, fixed `W=[0.2,0;0,0;0,-0.07;0,0]` and actions `{1,0.8,0,-0.8,-1}` (lines 4–14); the published L04 B08 discrete fixture instead uses `X0=(1182.074,119560,459.832,45260)`, a five-action `{0.6,0.3,0,-0.3,-0.6}` catalog and stage-dependent disturbance bounds. Its nonlinear driver also uses initial stocks `(119520,45280)`; the available sources do not state how these are meant to map to the published linear state. No saved output, control-history-to-table mapping, or unrounded row data accompany this candidate pair. The source files are not copied into the repository, and no MATLAB/Octave execution was performed. Treat its matching criterion as a recovered candidate implementation, not proof it generated the reported `14.048` row.

An independent finite enumeration and nonlinear replay transcription is saved in [the issue #1 candidate record](evidence/issue1-unconstrained-candidate-replay.json), generated by [its checker](tools/check_issue1_unconstrained_candidate.py). It enumerates all 625 fixed plans and 256 disturbance histories per plan for the candidate affine model; two plans tie at `55.15290284582085`. It then replays all 625 control sequences through the candidate's 10,000-step nonlinear recurrence. **None** lands inside the published terminal state's three-decimal rounding box. The nearest replay is plan `(-0.8,0.8,1.0,-0.8)`, terminal state approximately `(1197.994607,13.411026,451.052187,-5.191885)`, with state-vector L2 error `19.339964` from the displayed row. The selected first minimax plan replays to `(1197.994607,13.411027,451.052187,-5.191885)` and candidate Euclidean cost `14.558159`; the displayed L04 state evaluates to `16.420691` under the article's printed criterion, not the reported `14.048`. This rules out the *current candidate pair and its stated five-action catalog* as an exact reproduction under the transcribed update order; it does not rule out another source revision or separate historical data.

Recompute the saved record and, where the private local files are available, check their hashes with:

```sh
python3 -B docs/research/tools/check_issue1_unconstrained_candidate.py \
  --source-dir "<local-papers>/Minimax/Unconstrained" \
  --verify-record docs/research/evidence/issue1-unconstrained-candidate-replay.json
```

The audited inventory and prior matrix continue to identify the L04 generating MATLAB project, original unrounded arrays, nonlinear integration, and criterion/coordinates behind the inconsistent row as unresolved (`docs/research/publication-source-matrix.md`, B08 row; `docs/research/b08-reported-rounding-audit.md`). Neither the autosave nor the candidate replay pair closes those links.

## B09 / L13

The supplied L13 article is 370,362 bytes, SHA-256 `4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e` (`docs/research/inventory.json`, `id=L13`). A full local archive PDF hash scan found the same bytes in the local archive. The [official journal record](https://journals.ssau.ru/vestnik/en/article/view/7621) lists the article and DOI `10.18287/2541-7533-2019-18-4-129-145`; its only listed supplementary file is JATS XML, not MATLAB source. L13 equation (16), physical PDF page 6, defines the displayed criterion as the unweighted four-state Euclidean norm to `(60,0,24,0)`; Table 2 on physical page 14 gives the reported rows. Evaluating that printed formula at the original adaptive rounded state `(60,20.3,24,4.5)` yields approximately `20.792787211`, not `22.657` (`docs/research/baselines.md`, B09 section; `docs/research/l13-displayed-criterion-audit.md`).

The selected archive register records A08 `Minmaxclosedloop.m` (SHA-256 `06c2f750a2c7deb01dbc457185378b440f8ba134216d7ab0762b8b28229ba2d9`), A09 `Minmaxopenloop.m` (`59daeacc7727cb7ff5e0090368d76e401fa4d0c874ef359a97d6acb722467aa6`), and A10 `results.mat` (`afb4c1b34aa4c6e9f6fdf3e31530e80e05962d9d5b83401fdb3665bd41adef4c`). Raw-byte hashes in the local archive match these registered identities. A09 line 32 uses the four squared Euclidean terms **plus** `(2.5*x4-x2)^2`; A08 lines 81 and 136 use reporting expressions with an **unsquared** `(x3-24)` term. These are source-level facts about A09 and A08, respectively. Neither file is linked to L13's Table 2 run, and their differences do not authorize replacing L13's published definition. A10 is a saved workspace; its saved adaptive controls and terminal stocks differ from the L13 original-adaptive row (`docs/research/l13-a10-saved-criterion-trace.md`; `docs/research/publication-source-matrix.md`, B09 row).

### Newly checked saved-figure trace for the L13 original-adaptive row

The owner-supplied ignored file `papers/Minimax/Adaptive_Samara/3.fig` is a MATLAB v5 figure (48,844 bytes; SHA-256 `65f15e5a3d46eb193ef7106b159159aee1fd3a9b8308a42120a32eddc9e7a719`; file timestamp 2019-11-06 14:40:54 +0300). MATLAB metadata records the figure's basename as `3.fig`. The neighboring A08 file has timestamp 2019-11-06 11:45:40 +0300, and the manuscript `Шориков_Калев_Вестник_06.11.19.doc` was created the same day and last saved 2019-11-07. These times are contextual provenance, not a saved-run identifier.

The figure stores four successive phase segments in each player plane. Its numeric data are available with `matdump -d papers/Minimax/Adaptive_Samara/3.fig hgS_070000`; a libmatio reader was used to retain full stored binary64 coordinates. The successive `(x1,x2)` states are `(59.133600709614917,18100)`, `(60.258434759826415,13664.979946782469)`, `(60.729201077027163,9145.5973398098558)`, `(60.941338661957637,4590.9072590285996)`, and `(60,20.30685938061275)`. The corresponding `(x3,x4)` states are `(24.384989983346358,7150)`, `(23.864726637555016,5321.1257512483826)`, `(23.584155758068803,3531.2712534273032)`, `(23.438976408445249,1762.4595715739815)`, and `(24,4.5363409402127273)`. The terminal state rounds to the L13 Table 2 original-adaptive row `(60,20.3,24,4.5)`. The initial pair agrees to binary64 precision with the state computed by A08 lines 6–22 from `K=2.5`, `dK=-0.075`, `P=30240`, `I=360`, and its other printed coefficients. The figure's two phase planes and staged line segments also match the plotting statements at A08 lines 65–70.

The intermediate flow pairs recover cumulative control values approximately `0, 1, 1.5, 1.75, 0.75` using A08's model relation `K_m = K + dK + c_1 u` and `K_m=x_1/x_3`; their increments are `(1, 0.5, 0.25, -1)`, all members of A08's nine-value action catalog at line 35. Re-evaluating the A08 nonlinear flow and stock recurrence at four 75-second stages with those increments reproduces the figure's stage states with maximum absolute component error `1.8e-8` (the maximum over all four components at each of the four post-control states; no normalization). This is an independent transcription of the printed source equations and recovered figure path, not execution of MATLAB or its optimizer. The following standard-library Python calculation specifies the recurrence and error metric from the recorded parameters and figure coordinates:

```python
K, P, I = 2.5, 30240.0, 360.0
c1, c2, c3, c4, c5 = 0.1, -6700.0, 900.0, -15.0, -12.0
dK = -0.03 * K
figure = [
    (60.258434759826415, 13664.979946782469, 23.864726637555016, 5321.1257512483826),
    (60.729201077027163, 9145.5973398098558, 23.584155758068803, 3531.2712534273032),
    (60.941338661957637, 4590.9072590285996, 23.438976408445249, 1762.4595715739815),
    (60.0, 20.30685938061275, 24.0, 4.5363409402127273),
]
def flow(u):
    km = K + dK + c1*u
    pp = P + c2*(km-K)**2 + c3*(km-K)
    iu = I + c4*(km-K)**2 + c5*(km-K)
    mg = pp / iu / (1+km)
    return mg*km, mg

mo, mg = flow(0.0)
Mo, Mg, u = 18100.0, 7150.0, 0.0
replayed = []
for increment in (1.0, 0.5, 0.25, -1.0):
    Mo, Mg = Mo-75*mo, Mg-75*mg
    u += increment
    mo, mg = flow(u)
    replayed.append((mo, Mo, mg, Mg))
max_error = max(abs(a-b) for state_a, state_b in zip(replayed, figure)
                for a, b in zip(state_a, state_b))
print(max_error)  # 1.7955244402401149e-08
```

At the stored figure endpoint, decimal arithmetic on the displayed full-precision binary64 coordinates gives `20.8073767455` for L13 Eq. 16 and `22.6569240872` for A09 line 32's synchronization-augmented criterion. The latter rounds to the reported `22.657`. A08 line 81 has an unsquared `(mg(end)-24)` term, but its endpoint has `mg=24` exactly; on this endpoint its reported value is also `22.6569240872`. Thus the figure, A08 model, inferred finite action history, and A08/A09 criterion variant provide a coherent, numerically reproduced candidate explanation for the L13 row. They do not prove that this precise source snapshot and figure generated the publication table: there is no saved run log, source-control revision identifier, or explicit link from `3.fig` to Table 2. Preserve the article's Eq. 16 and reported row as published, and label this match as candidate provenance pending that final link.

Thus the L13 original-adaptive endpoint coordinates, a compatible staged action history, and an augmented criterion that reproduces the reported value are now recovered from the saved figure and hash-matched source candidate. The exact publication-generating revision, error bounds, optimizer run, and explicit table-to-figure mapping remain unverified. The nearby source/figure pair materially narrows the provenance gap but does not authorize replacing the published criterion or values.

## Search bounds and evidence needed next

I read the selected archive register and the existing publication/version and criterion audits; enumerated the local PhD archive (8,935 files); searched the source-file inventory for MATLAB, MAT, and Live Script names associated with adaptive/minimax/open-loop work; and SHA-256 checked every PDF in the archive against the registered L04/L13 article identities. This recovered exact article copies and reconfirmed registered A08–A10. The register is explicitly a targeted selection, not a complete source audit, and filename-based discovery cannot rule out source embedded in unsearched containers or differently named files. I did not unpack archives, inspect every Office/Simulink container, or claim absence from the owner's full corpus.

The 2026-11-02 follow-up additionally hashed the local ignored A08 sibling autosave and enumerated ZIP members under `papers/`; none had `.m`, `.mat`, `.mlx`, `.pas`, `.slx`, `.mdl`, or `.csv` names. The nearby AiT ZIPs contain TeX/PDF article files, and the Adaptive Samara ZIP contains DOC/PDF article files. A `bsdtar -tf` listing of `papers/Minimax/Unconstrained for AaRC/Paper.rar` likewise showed article TeX/PDF and support assets, not a simulation source. These are member-list checks, not recursive Office/Simulink or arbitrary nested-container inspection. The 2026-11-04 follow-up inspected the local MATLAB figure data in `Adaptive_Samara/1.fig` through `4.fig` and `results.mat`; Figure 3 supplies the L13 row candidate detailed above, while the saved workspace remains a different run. The wider Office/Simulink/archive search remains incomplete, and this figure match does not rely on a claim that those containers contain no source material.

To resolve the remaining version gap, evidence must link one generator revision to the corresponding optimizer run and publication row, including any error bounds and original row output. For L04, the nearby TeX manuscript and candidate replay pair still do not establish the source version that generated the published nonlinear row. For L13, the A08 source/figure reconstruction is now a close candidate provenance chain, but its exact run and explicit Table 2 mapping are missing; A10 remains a distinct saved workspace. Until that last link is recovered, retain the historical rows and treat the displayed article criteria as the publication-level definitions, while documenting the candidate augmented-criterion explanation separately.
