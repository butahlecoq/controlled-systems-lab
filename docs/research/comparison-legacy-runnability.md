# Legacy runnability and comparison fairness audit

Audit date: 2026-10-17. Scope: wayfinder map #390, ticket #398 "Audit legacy runnability and comparison fairness". This is a documentation-only fact audit: no product code, test or build change, and no legacy program was executed by this audit beyond syntax compilation and read-only inspection. Facts below are cited to repository paths with line numbers, to issue numbers, or are marked **[measured 2026-10-17]** with the method stated. Porting-effort labels are estimates with the stated basis; they are not decisions about what to port first (that is the old-side porting-plan ticket, #400).

Evidence roots: supplied archive (`Свидетельства/`, `papers/`, inventory L01–L31, `docs/research/inventory.json`); larger local archive `D:/work/PhD/PhD` (selected register A01–A45, `docs/research/archive-selected-sources.json`); Works folder `D:/work/PhD/Works` (register W01–W14, `docs/research/works-selected-sources.json`); prior audits `docs/research/legacy-audit.md`, `algorithm-module-inventory.md`, `archive-followup.md`, `works-followup.md`, `baselines.md`, `publication-source-matrix.md`. The larger archive was read only; it was not modified. Raw originals are not redistributed and are not copied into this repository.

Identity check **[measured 2026-10-17]**: SHA-256 of L16, L19, L26, L28, A06 (`btulshor.pas`), A08, A09, A10, A40, W04, W07, W09, W12 matched the registers (`inventory.json`, `archive-selected-sources.json`, `works-selected-sources.json`) byte-for-byte on this date; the publication-source-matrix reported the same matches on 2026-10-16 (`publication-source-matrix.md:5`).

## Host toolchain availability

**Measured 2026-10-17** with `Get-Command octave,matlab,fpc,lrs,python2,python,python3,py`:

| Tool | Present | Detail |
|---|---|---|
| MATLAB | No | not on PATH |
| GNU Octave | No | not on PATH |
| Free Pascal (`fpc`) | No | not on PATH |
| `lrs`/lrslib | No | not on PATH |
| Python 2 (`python2`) | No | not on PATH |
| Python 3 | Yes | 3.13.5 (`C:\Users\f5spb\AppData\Local\Programs\Python\Python313`), `py` launcher 3.13 |
| NumPy / SciPy | Yes | numpy 2.3.2, scipy 1.16.3 (same versions as `legacy-audit.md:7`) |
| matplotlib | No | `ModuleNotFoundError` **[measured 2026-10-17]** |
| pandas / scikit-learn | No | `ModuleNotFoundError` **[measured 2026-10-17]** |

Consequence: **no MATLAB-family artifact and no Pascal artifact can be executed natively on this host as configured**; Python 2 artifacts cannot run on the only installed interpreter without a port. This is a host fact, not an artifact property; nothing was installed during this audit.

Python 3.13 syntax status of every supplied and Works Python file, compiled with the built-in `compile()` (no execution, no bytecode written) **[measured 2026-10-17]**:

| File | Result |
|---|---|
| `Свидетельства/…№4…/ClosedLoopControl.py` (L16) | parses |
| `Свидетельства/…№6…/ClosedLoopControl.py` (L22) | parses (byte-identical to L16) |
| `Свидетельства/…№5…/MinimaxOpenLoopControl.py` (L19) | parses |
| `Свидетельства/…№1 (ОД)/ReachableSet.py` (L26) | `SyntaxError` line 17 (matches `legacy-audit.md:14`) |
| `Свидетельства/…№2 (Модель)/LinearSystem.py` (L28) | parses |
| `Works/ClosedLoopControl.py` (W01) | `SyntaxError` line 157 |
| `Works/Forecast.py` (W02) | parses |
| `Works/LinClosedLoopControl.py` (W03) | `SyntaxError` line 189 |
| `Works/LinearSystem.py` (W04) | parses |
| `Works/Main_mod.py` (W05) | parses |
| `Works/Main_Shor.py` (W06) | parses |
| `Works/MinimaxOpenLoopControl.py` (W08) | parses |
| `Works/OpenLoopControl.py` (W09) | `SyntaxError` line 132 |
| `Works/ReachableSet.py` (W12) | `SyntaxError` line 16 (L26 minus one blank line, `works-followup.md:12`) |
| `Works/VFEnumeration.py` (W14) | `SyntaxError` line 12 |

The failures at lines 17 (L26), 157 (W01), 189 (W03), 132 (W09), 12 (W14) are Python 2 `print` statements; W12's is the same statement as L26 line 17 shifted by one line. Parsing is syntax only: it does not imply Python 3 semantics for the surviving files.

## 1. Supplied-archive Python listings (L16–L28)

Sizes **[measured 2026-10-17]** (`Get-Content` line counts; bytes from `inventory.json`): L16 = 2,245 B / 77 lines (SHA-256 `543db67b…`), L19 = 9,601 B / 253 lines (`6385317d…`), L22 = byte-identical to L16, L26 = 6,183 B / 164 lines (`98aa51db…`), L28 = 4,594 B / 64 lines (`f567c88d…`). L14, L17/L23, L20, L25, L29 are PDF listings of the same programs (`source-map.md:24–38`); L14 has no standalone `.py` (`source-map.md:51`).

### 1.1 L26/W12 `ReachableSet.py` — reachable-set construction

- **Language/size**: Python 2-era, NumPy only; 164 lines (W12: 163 lines, one blank line removed).
- **Runnability today**: does not parse under Python 3.13 (line 17); no Python 2 interpreter on host. The module has no `__main__` guard: the top-level demo (lines 146–162) is part of import. Not executed in this audit; the repo's executed check was parse-only (`legacy-characterization.json:63–69`).
- **Defects forcing corrected-track treatment**: backward branch inverts `A` and mutates the caller's `B` in place (`ReachableSet.py:12–13`, `legacy-audit.md:24`); `U` is read as a hidden module-level global despite the `U1` argument (`ReachableSet.py:22`; `legacy-audit.md:24`); custom simplex/double-description with fixed tolerances and randomized basis selection (`ReachableSet.py:62,79,102`; `legacy-audit.md:25`); the demo itself is a B04-neighbour configuration — `T=16`, `B=(2208/110,0,−1152/110,0)`, `U=[−1,1]`, `X0=(1192.5,119500,454,45300)` (lines 154–158), matching the B04 saved-witness family rather than the printed B04 model (`publication-source-matrix.md:28`).
- **Port effort (estimate)**: small for the file (one 164-line NumPy module, no external solver), but the backward-branch semantics and global dependencies require a correctness pass before comparison.
- **Baseline gate**: reachable-set construction seams (B02/B03 evidence class; `baselines.md:23–44`) and B04-neighbour backward construction; no canonical baseline input is recovered by this file.

### 1.2 L28/W04 `LinearSystem.py` — fuel-plant model builder

- **Language/size**: Python 2-era, NumPy only; 64 lines (W04: 72 lines, different uniform-grid branch).
- **Runnability today**: parses under 3.13; the module body is a self-contained demo (lines 52–64) with no missing names, but it was not executed in this audit and the demo is not a baseline. The repo's characterization executed only the `LinearSystem` function through AST loading (`legacy-characterization.json:7–53`).
- **Defects forcing corrected-track treatment**: uniform-grid branch loses mass memory — the stock diagonal is zero, so the zero-control next state is `(1192.5,−10840.9091,454,−4127.2727)` instead of the article recurrence's expected masses (`legacy-audit.md:11`; `legacy-characterization.json:35–42`); the explicit-time and uniform branches do not implement the same mass update (`legacy-audit.md:12`); scalar and vector control-coefficient branches write to different state indices (`LinearSystem.py:35–36` vs `39–41`; `legacy-audit.md:30`); the explicit branch forces the first control row to zero while the uniform branch does not (`LinearSystem.py:25` vs `29`; `works-followup.md:21`). W04 flips the uniform stock self-coefficient to 1 and retains the coordinate discrepancy (`works-followup.md:13,21`).
- **Port effort (estimate)**: small; the open work is semantic resolution with source/unit authority, not code volume.
- **Baseline gate**: the plant/discretization seam used by the B04–B09 fuel family; canonical authority is blocked on #2 and the B04 generator (#10).

### 1.3 L16/L22 `ClosedLoopControl.py` — optimal adaptive loop (minimax-adaptive folder duplicated)

- **Language/size**: Python 2-era, NumPy + matplotlib + SciPy; 77 lines; L22 is byte-identical, so the "minimax adaptive" folder duplicates the optimal-adaptive listing (`source-map.md:32`, `legacy-audit.md:33`).
- **Runnability today**: parses under 3.13; on this host `import` fails first at line 2 (matplotlib absent **[measured 2026-10-17]**). With matplotlib present, the module body still reaches `LinearSystem(...)` at line 68 with no such name defined (only imports are numpy/matplotlib/SciPy, lines 1–3), and `ClosedLoopControl` depends on global `T` and undefined `OpenLoopControl` (lines 7–8; `legacy-audit.md:15,31`). The isolated-definition check in `legacy-characterization.json:71–74` records the `NameError` for `T`.
- **Defects forcing corrected-track treatment**: hidden globals (`T`, `mo/mg/Mo/Mg`, `X`) and a missing standalone `OpenLoopControl` (`legacy-audit.md:31`; `source-map.md:51`); the cost at line 70 reproduces the B04-shaped weighted norm, but the demo is not the printed B04 model.
- **Port effort (estimate)**: small file, medium context: it only becomes executable with the W09/W01/W03 helper family (`works-followup.md:25`), which itself has Python 2 statements.
- **Baseline gate**: B05 optimal-adaptive evidence class (`baselines.md:70–87`); the byte-identical minimax-adaptive folder gated the missing B09 implementation until MATLAB A08 was recovered (`archive-followup.md:34`).

### 1.4 L19/W08 `MinimaxOpenLoopControl.py` — finite-action minimax

- **Language/size**: Python 2-era, NumPy + SciPy (`from scipy.optimize import minimize`, line 2); 253 lines.
- **Runnability today**: parses and is importable under 3.13 (module body is imports and definitions only; W08 reorders the same definitions, `works-followup.md:11`). No demo is present, so importability is not a run.
- **Defects forcing corrected-track treatment**: `optimize_on_rs` minimizes the supplied convex cost locally with SLSQP over the H-representation and returns its negation, which is not the worst-case maximum — the positive convex check `(x−1)^2` on `[0,2]` returns `-0.0` against a true vertex maximum of 1 (`MinimaxOpenLoopControl.py:246–253`; `legacy-audit.md:13,18`; `legacy-characterization.json:55–61`); the internal simplex casts to `float32` (`:228`; `legacy-audit.md:25`); NaN scoring/`nanargmin` has no explicit infeasible contract (`:14–15`; `legacy-audit.md:29`); `feasible_actions` materializes the full Cartesian product (`:18–33`) — 2^16 = 65,536 and 9^16 = 1,853,020,188,851,841 for the audited counts (`legacy-audit.md:16,26`); the disturbance set is supplied as a single `V1` vertex set, not an explicit time-dependent uncertainty (`:39`; `legacy-audit.md:27`). The corrected replacement is an exhaustive terminal-vertex oracle (`algorithm-module-inventory.md:119`).
- **Port effort (estimate)**: small for the language port; medium for a corrected comparator (replace the local solver by a justified vertex oracle and keep the enumeration contract).
- **Baseline gate**: B06/B07/B08 minimax evidence class (`baselines.md:89–123`); with the B08 displayed-data references (section 4) a corrected minimax comparator can be validated without archive recovery.

### 1.5 L14 PDF listing (no standalone source)

- **Language/size**: Python 2-era listing, PDF only, 3 pages / 259,188 B (`inventory.json`, L14 row); defines `OpenLoopControl`, `ConvexProgram`, `Snatch`, `LPControl` (`source-map.md:24`).
- **Runnability today**: not executable from PDF; extraction is formatting-sensitive and the audit records a possible unbound time symbol in `Snatch` (`legacy-audit.md:32`). First-hand check of the local extraction: the `Snatch` caller uses `A[t:,:,:]`/`B[t:,:,:]` at `docs/research/extracted/L14.txt:79` with no visible binding of `t` in that block, but the extraction flattens indentation.
- **Port effort (estimate)**: not applicable as-is; the standalone W09 now supplies the same helper family (`works-followup.md:25`).

## 2. Larger local archive MATLAB sources (A01–A45)

None of these was executed here, matching the prior audit ("Original code was not executed", `archive-followup.md:5`; "no historical program executed", `algorithm-module-inventory.md:3`). All registered files exist at their registered paths with the registered byte counts **[measured 2026-10-17]**. Line counts below are **[measured 2026-10-17]** (`Get-Content`); byte counts from `archive-selected-sources.json`. Runnability today is uniformly "not native on this host" (no MATLAB/Octave, section "Host toolchain"); the remaining columns record the corrected-track evidence and gates.

| ID | Path (archive-relative) | Type / bytes / lines | Runnability notes | Defect / evidence anchors | Baseline gate |
|---|---|---|---|---|---|
| A01 | `Семинар ИММ/Статья/ReachableSets.m` | MATLAB, 8,645 B, 292 | needs MATLAB/Octave; neighbouring variant, not canonical | T=12, X0≈(1220.3,119500,440,45300), B=(2208/110,0,−1152/110,0); comments saved decimals; active flows rounded (`archive-followup.md:26`; `publication-source-matrix.md:28`) | B04 neighbour (non-canonical) |
| A02 | `Конференция/ICIE 2018/Adaptive_Correction.m` | MATLAB, 3,590 B, 123 | needs MATLAB/Octave | T=16 with different nonlinear initial state/B and accumulated control increments (`archive-followup.md:28`) | B04/B05 neighbour |
| A03 | `Конференция/ICIE 2018/OpenLoopControl.m` | MATLAB, 4,276 B, 129 | needs MATLAB/Octave | forward/backward optimization and witness recovery; objective omits synchronization term (`archive-followup.md:28`; `algorithm-module-inventory.md:117`; `publication-source-matrix.md:29`) | B04 neighbour; witness-recovery seam |
| A04 | `Scientific Research/Zonotope.m` | MATLAB, 2,003 B, 66 | needs MATLAB/Octave | reduction branch is 2D while active example is 3D (`archive-followup.md:46`) | B02 approximation class |
| A05 | `Scientific Research/ELL_OD.m` | MATLAB, 1,313 B, 45 | needs MATLAB/Octave + missing dependency | references external `ell_enclose`; enclosing, not exact set (`archive-followup.md:18,46`) | B02 approximation class |
| A06 | `Статьи/А.Ф. Шориков/btulshor.pas` | Object Pascal, 43,261 B, 1,075 | **no FPC on host; four units missing** (see 2.1) | ZODENTEK step-bound concern `:839–843` (`algorithm-module-inventory.md:104`) | Pascal projection family (no B02–B09 baseline) |
| A07 | `Scientific Research/BTULSHOR/BTULSHOR.m` | MATLAB, 592 B, 44 | needs MATLAB/Octave | MATLAB translation of the old reachability algorithms (`archive-followup.md:19`) | Pascal-comparison complement |
| A08 | `Публикации/Минимакс/Adaptive_Samara/Minmaxclosedloop.m` | MATLAB, 4,525 B, 147 | needs MATLAB/Octave; saved workspace A10 | T=4, nine actions; line 81 unsquared fuel-flow deviation (`publication-source-matrix.md:30`; `archive-followup.md:36`) | B09 (unmatched to printed row) |
| A09 | `Публикации/Минимакс/Adaptive_Samara/Minmaxopenloop.m` | MATLAB, 1,578 B, 55 | needs MATLAB/Octave | line 32 adds `(2.5*x4−x2)^2`; vertex safeguard with eps; local nonlinear solve (`archive-followup.md:38`; `publication-source-matrix.md:30`) | B09 candidate criterion |
| A10 | `Публикации/Минимакс/Adaptive_Samara/results.mat` | MAT workspace, 1,111,167 B | needs MATLAB/Octave or SciPy `loadmat` | saved run terminal stocks ≠ published row (`archive-followup.md:40`) | B09 saved-run evidence |
| A11–A14 | Izvestiya article folder: tables `.doc` (164,864 B), two revision PDFs, byte-identical L11 copy | DOC/PDF | not executable | tables corroborate transcription; discrepancy remains (`archive-followup.md:23–24`) | B04 source evidence |
| A15 | `Scientific Research/Main_Hull_mod.m` | MATLAB, 591 B, 27 | needs MATLAB/Octave | bulk-deletion driver (`algorithm-module-inventory.md:47`) | B03 hull class |
| A16 | `Scientific Research/Simplex_Hull_mod.m` | MATLAB, 1,131 B, 42 | needs MATLAB/Octave | bulk classification from one basis; fresh `B=eye` per invocation (`algorithm-module-inventory.md:47,51`) | B03 hull class |
| A17 | `Scientific Research/GeoCalcLib-master/vertexEnumeration.m` | MATLAB, 236 B, 8 | needs MATLAB/Octave + external `libgeocalc` mex | external dependency not recovered (`algorithm-module-inventory.md:130`) | V↔H backend candidate |
| A18 | `Конференция/ICIE 2018/VertexEnumeration.m` | MATLAB, 2,072 B, 86 | needs MATLAB/Octave | double-description with randomized initial basis (`algorithm-module-inventory.md:130`) | V↔H conversion |
| A19 | `Публикации/ЮУрГУ/CntrlTrMtrx.m` | MATLAB, 4,750 B, 94 | needs MATLAB/Octave | LTV discretization/transition module (`archive-followup.md:20`) | B03/B04 model seam |
| A20 | `Публикации/ЮУрГУ/TestSouthUral.m` | MATLAB, 2,883 B, 96 | needs MATLAB/Octave | six-state orbital example, second application (`archive-followup.md:20`) | non-fuel application lead |
| A21/A22 | `Конференция/УрГУПС 2016/p13.pdf`, `…/Shorikov_Kalev_Paper.tex` | PDF/TeX, 391,183 B / 27,104 B, 433 lines | not executable | local zonotope paper + editable source (`archive-followup.md:17`) | B02/approximation context |
| A23 | ellipsoidal-toolbox study notes `.docx` (407,188 B) | DOCX | not executable | study notes, not the library (`archive-followup.md:18`) | approximation context |
| A24 | `Scientific Research/Main_Hull_Shor.m` | MATLAB, 556 B, 25 | needs MATLAB/Octave | baseline per-point phase-I driver (`algorithm-module-inventory.md:26`) | B03 hull baseline |
| A25 | `Scientific Research/Simplex_Hull_Shor.m` | MATLAB, 829 B, 32 | needs MATLAB/Octave | fresh artificial basis per tested point (`algorithm-module-inventory.md:26`) | B03 hull baseline |
| A26 | `Scientific Research/Main_Hull.m` | MATLAB, 1,470 B, 57 | needs MATLAB/Octave | invokes `Simplex_Hull.m` at line 49 (`algorithm-module-inventory.md:48`) | B03 hull variant |
| A27 | `Scientific Research/Simplex_Hull.m` | MATLAB, 975 B, 37 | needs MATLAB/Octave | deletes columns from basis coordinates; no front-moving/skip (`algorithm-module-inventory.md:48`) | B03 hull variant |
| A28 | `Scientific Research/LPHULL.m` | MATLAB, 496 B, 22 | needs MATLAB/Octave | LP hull routine (`algorithm-module-inventory.md:14`) | B03 hull class |
| A29 | `Scientific Research/QLPHULL.m` | MATLAB, 1,619 B, 80 | needs MATLAB/Octave | decreasing sort metric `abs(max((p−d)./r))`; grouping block commented out (`:44–64`); independent final LP (`algorithm-module-inventory.md:65`) | B03 hull class; OPT-07 adapter source |
| A30 | `Scientific Research/Modified_SM.m` | MATLAB, 1,150 B, 51 | needs MATLAB/Octave | alternate inverse-basis membership predicate (`algorithm-module-inventory.md:49`) | B03 hull class |
| A31 | `Scientific Research/SMLP.m` | MATLAB, 1,770 B, 73 | needs MATLAB/Octave | tableau-updating auxiliary LP experiment (`algorithm-module-inventory.md:49`) | B03 hull class |
| A32 | `Scientific Research/quickhull.m` | MATLAB, 2,316 B, 67 | needs MATLAB/Octave | 2D geometric Quickhull with plotting mixed in and slope divisions; no simplex (`algorithm-module-inventory.md:84`) | hull strategy class |
| A33 | `Публикации/Минимакс/Constrained/QLPHULL.m` | MATLAB, 1,778 B, 91 | needs MATLAB/Octave | active grouping with fixed `Ck`; `itrt` counters discarded (`algorithm-module-inventory.md:66`) | constrained minimax hull |
| A34 | `Конференция/ИТиС 2019/2/Main_Hull_mods.m` | MATLAB, 1,005 B, 50 | needs MATLAB/Octave | streaming candidate strategy, not recursive (`algorithm-module-inventory.md:67`) | B03 hull variant |
| A35 | `Конференция/ICIE 2018/Snatch.m` | MATLAB, 564 B, 22 | needs MATLAB/Octave | predecessor/successor witness recovery (`algorithm-module-inventory.md:117`) | B04 witness seam |
| A36 | `Конференция/ICIE 2018/Simplex_ctrl.m` | MATLAB, 881 B, 32 | needs MATLAB/Octave | feasibility LP for two convex combinations (`algorithm-module-inventory.md:117`) | B04 witness seam |
| A37 | `Конференция/ICIE 2018/Simplex_lazy_ctrl.m` | MATLAB, 1,576 B, 65 | needs MATLAB/Octave | direct stacked terminal equality; hard-coded rows; no visible state path constraints (`algorithm-module-inventory.md:118`) | recovery baseline |
| A38 | `Конференция/ICIE 2018/SimplexIntersect.m` | MATLAB, 1,018 B, 36 | needs MATLAB/Octave | intersection adapter (`algorithm-module-inventory.md:168`) | set intersection seam |
| A39 | `Семинар ИММ/Статья/1st.fig` | MAT graphics, 1,131,239 B | inert parse only | saved B04 nominal/nonlinear witnesses; not the generator (`publication-source-matrix.md:28`) | B04 saved-witness evidence |
| A40 | `Семинар ИММ/Статья/program.m` | MATLAB, 3,819 B, 102 | needs MATLAB/Octave; replay kernel reimplemented publicly | `c2=−6700, c3=9000`, stocks advance to 99.99 s (`publication-source-matrix.md:28`; `b04-saved-witnesses.md`) | B04 replay evidence |
| A41–A42 | `…/Shorikov_Kalev_Article_v4.pdf` (858,237 B), `1st.png` (106,169 B) | PDF/PNG | not executable | B04 table/figure anchors (`archive-selected-sources.json`) | B04 source |
| A43–A45 | `Публикации/statyi dlya shiryaeva/` three PDFs | PDF, 1,347,343 / 555,552 / 679,336 B | not executable | retained-basis, incremental-hull and discretization references RP01–RP03 (`source-map.md:69`) | hull/discretization proof context |

Unregistered neighbours also exist in the same folders and are not in any register; examples **[measured 2026-10-17]**: `Публикации/Минимакс/Constrained/Minmaxopenloop.m` (3,643 B) vs registered A09 (1,578 B); `Constrained/ReachableSets.m` (4,592 B) vs A01 (8,645 B); `Constrained/program.m` (1,422 B) vs A40 (3,819 B); `Adaptive_Samara/Minmaxclosedloop.asv` (4,017 B); `Конференция/ИТиС 2019/2/CDD.m` (1,168 B); `Scientific Research/REACH_SET.m` (2,617 B), `SMO.m` (2,433 B), `Spirel_Solver.m` (1,791 B), `ReachableSets.m` (2,343 B, a different file from A01); Simulink models `fmcs.slx` (82,825 B / 104,684 B), `ident.slx` (27,363 B), `dis_jam.slx` (21,303 B); `Scientific Research/mpt3_1_2.7z` (10,148,247 B); `Конференция/ICIE 2018/vertex_enumeration.zip` (2,012 B). Treating any of them as canonical requires its own identity check and is not done here.

### 2.1 A06 Pascal `btulshor.pas`

- **Language/size**: Object Pascal (Turbo-Pascal-era), 43,261 B; **1,075** lines **[measured 2026-10-17]** (`Get-Content` and CRLF count both 1,075; file ends with a newline). Note: `archive-followup.md:19` and the ticket text say 1,076 lines; the measured count differs by one under the stated method.
- **Runnability today**: no `fpc` on the host **[measured 2026-10-17]**. Dependencies are explicit and absent: `USES BIBTUSH,DIALOGS;` (line 5) and `uses term,funfnx;` (line 26). A recursive name search of `D:/work/PhD/PhD` found no `BIBTUSH`, `DIALOGS`, `term.*` or `funfnx.*` files and exactly one `.pas` file (this one) **[measured 2026-10-17]**; `btulshor.rar` in the same folder contains only the same `btulshor.pas` (43,261 B, dated 2010-02-20) **[measured 2026-10-17]**. `archive-followup.md:19` already records that missing Pascal dependencies are not assumed recovered.
- **Procedure anchors [measured 2026-10-17]**: `REACH` line 41, `KPABEP` 73, `MODIF` 128, `OBREACH` 215, `OBRMTR` 246, `ALOWER` 617, `ZODENTEK` 766, `VERLIM` 888, `CHEBR` 913, `HSG` 993, `GIPBER` 353, `CRAPOV` 464. These confirm the anchors cited in `algorithm-module-inventory.md:27,98–101`.
- **Defects forcing corrected-track treatment**: ZODENTEK's step-bound loop jumps out on the first inactive row with nonpositive directional derivative and can ignore a later finite upper bound (`btulshor.pas:839–843`; `algorithm-module-inventory.md:104`); `CHEBR` is an enclosing-ball routine, not a Chebyshev center, and needs independent derivation (`algorithm-module-inventory.md:121`); hard-coded mixed tolerances `1E-10`/`1E-05` (`algorithm-module-inventory.md:104`).
- **Port effort (estimate)**: large — 1,075 lines with custom units and type families `t1`–`t13`, a private projection/feasible-direction family and no runnable native environment; the suggested scoping is one contract at a time (`algorithm-module-inventory.md:110`).
- **Baseline gate**: no B02–B09 baseline; it is the archival evidence for the projection/Zoutendijk family (`algorithm-module-inventory.md:88–110`).
- **Recovery lead (unverified)**: `Статьи/А.Ф. Шориков/Свидетельство_16.rar` (60,633 B, dated 2016-02-28) contains seven Word documents including a `Listing.doc` (118,784 B) and an abstract; the folder name decodes as a registration package number 16 **[measured 2026-10-17]**, but its contents were not inspected beyond the archive listing and its relation to `btulshor.pas` is not established.

## 3. Works folder W01–W14

Root `D:/work/PhD/Works` (the register does not name a root; this is the folder found on this host, and its byte counts match `works-selected-sources.json` **[measured 2026-10-17]**). Line counts are **[measured 2026-10-17]**.

| ID | File | Language / bytes / lines | Runnability today | Corrected-track evidence | Relationship / gate |
|---|---|---|---|---|---|
| W01 | `ClosedLoopControl.py` | Python 2-era, 13,453 B, 354 | Py3 `SyntaxError` at 157 | embeds `OpenLoopControl`/`ConvexProgram`/`Snatch`/`LPControl`/`ReachableSet`/`LinearSystem`; no complete optimizer family | L16 relative (`works-followup.md:14`) |
| W02 | `Forecast.py` | Python, 1,909 B, 55 | parses; pandas/sklearn absent on host | consumes W10/W11 spreadsheets (13 features, 1 target) | no control baseline (`works-followup.md:54`) |
| W03 | `LinClosedLoopControl.py` | Python 2-era, 13,260 B, 354 | Py3 `SyntaxError` at 189 | parameter/recovery variants; top-level call before its `LinearSystem` definition | L16 relative (`works-followup.md:25`) |
| W04 | `LinearSystem.py` | Python 2-era, 5,029 B, 72 | parses | uniform-grid stock self-coefficient changed to 1; coordinate discrepancy remains; demo ×0=(1192.5,119500,454,45300), T=5 | L28 variant, same plant seam (`works-followup.md:13,21–23`) |
| W05 | `Main_mod.py` | Python, 1,670 B, 71 | parses | ratio filter `<0` vs MATLAB `<eps`; different basis exclusion/deletion/reorder | A15/A16 relative (`works-followup.md:35`) |
| W06 | `Main_Shor.py` | Python, 1,289 B, 58 | parses | same family differences | A24/A25 relative (`works-followup.md:35`) |
| W07 | `MinimaxOpenLoopControl.ipynb` | JSON notebook, 13,847 B, 357 JSON lines | no saved outputs; all nine cells output-free | T=4, five actions incl. 0.01, x0=(1182.074,119610,459.832,45220), B=(2208/110,…), fixed [−1,1]² corners; cell source hash recorded | B08 separate variant, not the L04 run (`works-followup.md:29–31`) |
| W08 | `MinimaxOpenLoopControl.py` | Python 2-era, 9,601 B, 253 | parses | same named definitions as L19, reordered (`feasible_actions:4`, `Polytope:44`, `reachable_set:218`, `optimize_on_rs:232`, `minimax_openloop_control:241`) | L19 relative; no repaired oracle (`works-followup.md:11`) |
| W09 | `OpenLoopControl.py` | Python 2-era, 11,086 B, 282 | Py3 `SyntaxError` at 132 | supplies reachable-set, terminal minimization and witness helpers missing from L16 (`:7–46,55–102`); Py2 prints at 132/155/201 | L14/L16 missing-module gap (`works-followup.md:25`) |
| W10/W11 | `pred_data.xlsx`, `pred_test.xlsx` | XLSX, 210,243 B / 8,756 B | inert XML: 1000×14 numeric cells; no formulas found | forecast data | not fuel trajectories (`works-followup.md:54`) |
| W12 | `ReachableSet.py` | Python 2-era, 6,181 B, 163 | Py3 `SyntaxError` at 16 | L26 minus one blank line; global-U and backward-mutation findings persist | not independent evidence (`works-followup.md:12`) |
| W13 | `Rendezvous-RL.ipynb` | JSON notebook, 10,264 B, 339 JSON lines | saved outputs only; no fixed seed | four saved objects (mean reward 0.149124882…, session 0.128820578…) | separate nonlinear RL model (`works-followup.md:41–50`) |
| W14 | `VFEnumeration.py` | Python 2-era, 3,837 B, 103 | Py3 `SyntaxError` at 12 | empty equality matrix width `d` (homogeneous) vs W12's `d−1`; fuel vertices are test inputs | V↔H representation discrepancy (`works-followup.md:37`) |

Port effort (estimate): W01/W03/W09 are medium (350/354/282-line multi-module copies with embedded solver code); W04–W06/W14 are small; W07/W13 are configuration notebooks whose port is bounded but unverifiable without new runs; W02/W10/W11 are out of the control-comparison scope until provenance is established.

## 4. What the repository already provides for oracle-based validation

- The comparison protocol requires exact source identity, the full model/input record, three tracks (historical transcription, corrected reference, improved method), listed measurements and explicit non-comparisons (`baselines.md:141–155`).
- **B08 is the only finite-action minimax baseline with two independent, runnable references today**: a floating enumeration of 625 plans × 256 disturbance corners with minimum 67.150601101407 and three plans tied at 1e-8 (`reference-b08.json`; `baselines.md:159`), and an exact standard-library rational enumeration proving squared norm `112730080707/25000000`, whose square root (the norm) is approximately 67.15060110140489 with the same three exact minimizers (`b08-displayed-exact-audit.md:25–33`). Both use only the printed decimals in `baselines.md:115–117`; neither executes archived code (`tools/README.md:19,21`).
- Isolated characterization of archived definitions through AST loading is established practice (`tools/characterize_legacy.py:4–5`; `legacy-audit.md:7`; `tools/README.md:19`), with results in `legacy-characterization.json`.
- Arithmetic-only audits of printed rows exist for B08 rounding (`b08-reported-rounding-audit.md`), L13/B09 criteria and rounding boxes (`l13-displayed-criterion-audit.md`, `l13-rounding-box-audit.md`, `check_l13_displayed_criteria.py`, `check_l13_rounding_boxes.py`) and the A10 saved workspace (`l13-a10-saved-criterion-trace.md`).
- The B04 saved-witness replay is a scoped reference, not a canonical run: the historical scenario remains non-executable, the frozen row prints 368.45 while the saved objective is 368.609780868, and the replay ends at 99.99 s (`b04-saved-witnesses.md`; `README.md:59`; issue #10 comments).
- B08's and B09's printed nonlinear rows already disagree with their own displayed data: L04 nonlinear norm 16.42069149 vs reported 14.048; L13 original-adaptive norm 20.792787211 vs reported 22.657 (`baselines.md:121,139,163`). These are ready-made deviation records for corrected-track comparisons.

## 5. Blocked-versus-ready split

### Comparisons that can start now, without any further source recovery

1. **Corrected finite-action minimax oracle/comparator** validated against the two existing B08 references (`reference-b08.json`, `b08-displayed-exact-audit.md`), on the printed displayed model only. This is the readiest end-to-end comparison target (`baselines.md:159`; `algorithm-module-inventory.md:119`).
2. **B06/B07 displayed-data references** built the same way as the B08 audit: the shared model, actions, disturbance columns and both criteria are fully transcribed (`baselines.md:91–109`). Caveats bound the claims: the B06 extracted control sequence has ambiguous sign placement and B07 still lacks full physical parameters, so this track can fix a displayed-data reference but not a canonical reproduction (`baselines.md:16–17,100`).
3. **Isolated characterization of the supplied listings** under the host Python 3.13 + NumPy 2.3.2/SciPy 1.16.3 environment: L16, L19, L28 parse, L26/W12 need the documented `print` fix to parse; the AST-loading method already runs definitions in isolation (`legacy-audit.md:7`; `legacy-characterization.json`). Hooks that fail on this host today: L16/W01/W03/W09 import matplotlib (absent), W02 imports pandas/sklearn (absent).
4. **Source-variant differential checks** among files already in hand: W08 vs L19, W12 vs L26, W04 vs L28, W01/W03/W09 vs L16, W05/W06 vs A15/A16/A24/A25 (`works-followup.md:11–15,25`).
5. **Hull- and V↔H-strategy comparisons on synthetic fixtures** against the documented contracts, which need no baseline input (`algorithm-module-inventory.md:29,53,69,86,130–136`); B03's historical runtime/iteration reproduction itself is blocked (below).
6. **Static transcription of A06** projection/ZODENTEK semantics can begin from the file in hand (`algorithm-module-inventory.md:110`), while native execution stays blocked.
7. **B09 criterion-candidate arithmetic** already exists (L13 audits); a corrected-criterion comparison can use it, while the published B09 run stays blocked.

### Blocked on recovery or missing authority

| Item | Blocker |
|---|---|
| B04 canonical inputs (T16 `U` rows, stage constraints, generating revision, first-action convention) | issues #10 and #2; `publication-source-matrix.md:28,36`; historical scenario remains non-executable (`README.md:59`) |
| B09 canonical row (criterion/table mismatch; A08–A10 not matched to printed run) | issue #2; `publication-source-matrix.md:30` |
| B05 adaptive-optimal rows (L08 Table 2 policy labels mapped; historical run inputs/provenance unresolved) | `baselines.md:15,72`; `source-map.md:18`; `l08-embedded-equations.md` |
| B02 nonlinear-approximation semantics (initial-state/coordinate convention) | `baselines.md:12,38` |
| B03 complete model/input generation and seeds | `baselines.md:13,44` |
| B06/B07 canonical reproduction (control sign; disturbance set and full physical parameters) | `baselines.md:16–17` |
| Native MATLAB-family execution | no MATLAB/Octave on host **[measured 2026-10-17]**; toolbox/Simulink/MEX dependencies (A17 external `libgeocalc`, `algorithm-module-inventory.md:130`) |
| Native Pascal execution | no `fpc` on host; `BIBTUSH`, `DIALOGS`, `term`, `funfnx` absent from the archive (`btulshor.pas:5,26`; `archive-followup.md:19`) **[measured 2026-10-17]** |
| Native Python 2 execution | no Python 2 interpreter on host **[measured 2026-10-17]** |

## 6. Deviation-log requirements for corrected-track ports

The repository has no existing deviation-log artifact or schema **[searched `docs/` for "deviation log" variants: no matches]**. The requirements below assemble the documented protocol and the audited pitfalls; a port's deviation log should state at least:

1. **Identity**: source ID, archive-relative path, byte count and SHA-256 of the original, and the port's own version/hash (`baselines.md:143`; `publication-source-matrix.md:5`).
2. **Complete scenario record**: time grid, every `A/B/D` array, coordinate convention and order, units, constraints, uncertainty set and its time dependence, policy class, objective expression, initial conditions, solver tolerances, and reported originals (`baselines.md:143`).
3. **Recovered vs inferred inputs**: mark each field recovered from a hash-identified source or inferred/rounded — e.g., A39's effective 16-action histories were recovered algebraically with different first actions, and the frozen controller is unmatched (issue #10 comments; `publication-source-matrix.md:28`); W07's notebook configuration has no saved outputs and is not a B08 run (`works-followup.md:29–31`).
4. **Float precision and representation**: legacy `float32` simplex (`MinimaxOpenLoopControl.py:228`; `legacy-audit.md:25`), fixed tolerances (`ReachableSet.py:62,79`), the characterization's NumPy/SciPy versions (`legacy-audit.md:7`), and the exact-rational route used where decimals are the authority (`b08-displayed-exact-audit.md:25`).
5. **Randomness and seeds**: state whether the legacy path used randomized basis selection (`ReachableSet.py:102`; `MinimaxOpenLoopControl.py:161–168`), and that B03 seeds and full arrays are absent (`baselines.md:44`), W05/W06 demonstrations are unseeded (`works-followup.md:35`) and W13 has no fixed seed (`works-followup.md:50`), plus the port's own seeds/seed policy (`works-followup.md:56`).
6. **Changed behavior**: for every correction, the source equation or statement, the changed behavior, the resulting baseline difference and the verification evidence (`legacy-audit.md:45`).
7. **Track labeling and immutability**: historical numbers stay immutable; corrected/assumed variants get distinct IDs; runtime is context, not an acceptance threshold (`baselines.md:5,145–149`; `publication-source-matrix.md:36`; issue #10 acceptance list).
8. **Comparison semantics guards**: do not compare sampled trajectories against complete worst-case certificates, approximate sets against exact output without error, continuous controls against discrete actions, or one open-loop solve against an adaptive run (`baselines.md:153`).
9. **Environment**: host toolchain and package versions actually used for the executed comparison (the table in the Host section is the kind of record required; `tools/README.md:5`).

## 7. Candidate new backlog items (titles only)

1. Build the corrected finite-action minimax reference validated against both B08 references.
2. Produce exact and floating displayed-data references for B06 and B07.
3. Port the supplied Python listings to Python 3 with per-file deviation logs.
4. Transcribe A06 ZODENTEK/VERLIM projection semantics with regression fixtures.
5. Recover or stub the four missing Pascal units (`BIBTUSH`, `DIALOGS`, `term`, `funfnx`).
6. Hash-classify unregistered archive neighbours (`Constrained/Unconstrained` Minmax/ReachableSets variants, `CDD.m`, `SMO.m`, `Spirel_Solver.m`, `.asv`, Simulink models).
7. Inspect the unregistered `Свидетельство_16.rar` listing document as a Pascal-era recovery lead.
8. Resolve the L28/W04 uniform-versus-explicit stock-memory divergence against source authority.

## Limits

The larger archive was not fully enumerated for this audit (`archive-selected-sources.json:5` records 8,982 files seen and 175 non-library candidates in the earlier heuristic scan). Unregistered neighbours, archives inside `.rar`/`.zip`/`.7z` containers and Simulink models were not opened beyond the cases stated. No legacy program was executed except via the built-in Python `compile()` syntax check and the previously recorded isolated characterizations; MATLAB, Octave, Free Pascal and Python 2 were absent and nothing was installed. Port-effort labels are estimates. No decision on porting order or scope is made here (that belongs to the old-side porting-plan ticket #400).
