# R29 source-provenance follow-up — 2026-11-10

**Result: no canonical four-state run configuration or authorial control-center clarification recovered in this bounded pass.** This adds archive-member/provenance evidence to the earlier plain-text search; it does not repeat that search and call it exhaustive. The seventh acceptance bullet of [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8) remains open, feeding the historical-input work in [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2) and [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), both live-open at this checkpoint. The six architecture requirements have their separate reconciliation; no algorithm, benchmark or source-variant decision is added here.

The existing [printed-input audit](zonotope-paper-input-audit.md) and [editorial scalar reference](r29-corrected-scalar-reference.md) remain authoritative about what was recovered versus inferred. Existing claims were preserved; this investigation was coordinated in [the #8 follow-up claim](https://github.com/butahlecoq/controlled-systems-lab/issues/8#issuecomment-6755921088). Dirty main files were not edited. All source inspection was read-only, with payloads/conversions in private scratch; no author was contacted and no original source is redistributed.

## New archive-member evidence

The currently supplied `papers` tree contains **nine compressed containers**, previously outside the loose-file interpretation of the 511-file/66-MATLAB negative search. This pass listed all nine, then read their **102 regular member payloads** (108 listed entries including directories), representing **65 distinct SHA-256 payloads**. ZIP member bytes were read with Python's ZIP reader to avoid confusing CP437/escaped Cyrillic display names with actual member names; RAR members were read with `bsdtar -xOf`. No member code was executed. The containers are:

| Container relative to `papers/` | SHA-256 |
| --- | --- |
| `papers_for_professor/Статьи Шориков, Калёв.rar` | `9edf1275e45728428351560bc8d2d2e4cec80232857c2b38661fe287e083d12c` |
| `Minimax/Adaptive_Samara/Шориков_Калев_Вестник_СГАКУ_19.zip` | `c01f19ce98261627d811bb35fb06d431214c45771585af10ea5d100f06b17dc8` |
| `Minimax/Unconstrained/copyright_rus.zip` | `3c9c09434de8375665438a8343d90e529543c84c7717a49e49af20dae25eb677` |
| `Minimax/Unconstrained for AaRC/Paper.rar` | `287209914db24522cf3f758bea4622040c930daaecf227274dc3cc2ef534cd72` |
| `Minimax/Unconstrained for AaRC/ru-ait-tex-cp1251-2011.zip` | `05304b1e6ff461cb17a4d7a8f0751efd198eb816068a1649776de56127dcd5b4` |
| `Minimax/Unconstrained for AaRC/Shorikov_Kalev_AиT_New.rar` | `b0b4d394fed83241ace09815e7367fba549d833bafbd8960f881800a912e612f` |
| `Minimax/Unconstrained for AaRC/Shorikov_Kalev_АиТ_New (1).zip` | `40b9080956c0ea4b20e32edf222e2b152e3744b6a59f0461179856517f0c2bc0` |
| `Minimax/Unconstrained for AaRC/Shorikov_Kalev_АиТ_New.zip` | `e54fe00134ca10560658e960d5787552cfbf594d04f35849626ab7a4e474350b` |
| `Minimax/adaptive/constrained/LaTeX template for preparing an article for submission to the Journal of Samara State Technical University, Ser. Physical and Mathematical Sciences (R.zip` | `597a2c55286090dcc3f7ad7ee7f8a6f86ff3b31be1193a3876d003320fb5e204` |

The first RAR contains three scientific Word manuscripts and one temporary owner/lock member. The three manuscripts are **byte-identical** to already supplied loose copies:

| Member | SHA-256 | Consequence |
| --- | --- | --- |
| `Калёв В.И. Шориков А.Ф. МСНТ.doc` | `d2e949a7bff7287c9d31f854dba7a1a6f0facc2e065e2289b4d274c6643e8303` | Not a newly recovered revision. |
| `Калёв В.И. Шориков А.Ф. ИТИС16.doc` | `03eb71c5f22800750248a66f1f350182cdbc8a4b904cebf43eb1b6545db16b60` | Not a newly recovered revision. |
| `Калёв В.И. Шориков А.Ф. ИТИС17.doc` | `d179d9150a3d27b8c32a2705f4e79c3e8040f61d1278e98c041591c290c66fe8` | Exactly the two-state manuscript already inspected in [the preceding #8 source comment](https://github.com/butahlecoq/controlled-systems-lab/issues/8#issuecomment-6751910919); its center-formula support does not become four-state run recovery. |

The other containers contain minimax-paper material, journal templates, copyright forms and drafts/TeX build products. Their member inventories contain no MATLAB/Pascal driver, `Zonotope.m`, `Shorikov_Kalev_Paper.tex`, or R29 source bundle. TeX `.bak`/`.sav`, `.aux`, `.log` and SyncTeX provenance were inspected as source-history leads, rather than only searching displayed model numbers. The SyncTeX input lists point to the minimax manuscript/template tree, not a separate zonotope experiment. Three distinct SyncTeX payload identities were `b73e601a2ff167d6fcf75bcfb72e72a76bce9f5f60b829b3f4077384f237612c`, `8f0563cfc60171b09478fcdf52291bb8b9d5f85be663c009acebd0a010b4f064` and `d9450d8284a378eb549595bfb67eb2e21c5609116eea37c801bac6c60d064443`; one payload is duplicated between RAR/ZIP versions. Embedded host paths are private provenance, not instructions or public evidence of the absent R29 model. No historical four-state control specification was recovered from these leads.

The original larger `D:/work/PhD/PhD` archive from the [selected-source register](archive-selected-sources.json) was not mounted here. This pass therefore does **not** claim a new complete inspection of its 8,982 files or direct reinspection of A04/A22. The existing A04/A22 hashes and correspondence limits are retained from their prior audit.

## CEUR primary artifact and attachment check

A fresh download of the [publisher's volume page](https://ceur-ws.org/Vol-1825/) and [R29 PDF](https://ceur-ws.org/Vol-1825/p13.pdf) gives:

| Primary artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Volume index HTML | 17,389 | `7eee979345b5bdbe733389c58c0e8e8f2fb1311fb1d9097d7206950ae57a403a` |
| R29 `p13.pdf` | 391,183 | `8a70eddbd71571ea8443f92be1a799dc0ad6162fbfab902b88a931ab08981b4a` |

The PDF matches A21 exactly. `pdfdetach -list` reports **zero embedded files**; `pdfinfo` reports no metadata stream/custom metadata. Its self-reported TeX/pdfTeX creation time and HTTP Last-Modified are 2017-04-02; these are metadata observations, not a historical version guarantee. The volume page's actual links expose the paper PDFs/conference references but no source/code/archive link. No guessed URL or current absence is treated as proof that supplementary code never existed.

R29 explicitly identifies the four-state, sixteen-step scalar-input case and MATLAB R2014a implementation, but the supplied PDF still prints four-component control objects and the inconsistent center formula. Its references identify the two earlier 2016 model papers; neither a source configuration nor an erratum is attached to this publisher artifact. These facts preserve, rather than resolve, the distinction between printed data and editorial scalar interpretation. The [publisher-maintained author bibliography](https://www.mathnet.ru/eng/person126872) is a trace to those earlier papers and back to the same CEUR PDF, not an independent control-input correction.

## Targeted public owner/code-history check

R29's author identity/contact corroborates the known repository owner; no speculative username identity was substituted. The live GitHub REST endpoints [owner repositories](https://api.github.com/users/butahlecoq/repos?per_page=100&type=owner) and [public gists](https://api.github.com/users/butahlecoq/gists?per_page=100), read on 2026-11-10, returned:

- `anki`, created 2026-09-30;
- `Archy`, created 2026-10-28;
- `controlled-systems-lab`, created 2026-10-11;
- zero public gists.

The three public repository descriptions and creation chronology provide no separate historical MATLAB project lead. A local all-ref path-history query for `**/Zonotope.m` and `**/Shorikov_Kalev_Paper.tex` returned no tracked source-path history in the controlled-systems repository. This is a current-public-account/local-ref result: deleted repositories, private repositories, other accounts, unpushed branches, and the unmounted original dissertation archive are outside its scope. Public web searches by paper title/author/code terms led back to CEUR or bibliographic copies; unrelated modern zonotope packages supply no provenance for this historical example and were not adopted.

## Exact test of the already-mapped-input interpretation

A separate hypothesis is that the four-component control objects label the already mapped state-space input `B P`, rather than primitive control `P`. The earlier input audit already notes that the displayed generator is not `B`; the following exact certificate rules out **any** scalar generator yielding that column, rather than only the unit scalar choice.

For the printed `B=(4,0,2,0)^T`, `rank(B)=1`: its primitive control space is scalar, not two-dimensional. The displayed center `c=(0,0,0,0)^T` is in `image(B)` and uniquely pulls back to scalar center0. But the displayed single generator `g=(1,1,1,1)^T` is outside `image(B)`. The exact separating row `a=(0,1,0,0)` satisfies `a B=0` and `a g=1`; the fourth-coordinate row supplies another certificate. A left inverse `L=(1/4,0,0,0)` satisfies `L B=1`; it proposes generator `L g=1/4`, whose mapped residual is `g−B(Lg)=(0,1,1/2,1)^T`, not zero. All these identities were checked with Python `Fraction`.

Thus a full-column-rank inverse does recover the zero center but **cannot** recover a primitive control set consistent with the printed generator. Reading the displayed set as an independent state-space disturbance would change the printed plant/input relation, not resolve the label while preserving its inputs. Reading it as an erroneous scalar-label duplication remains an editorial hypothesis requiring the same explicit source-variant disposition. No numerical historical correspondence or authorial intention follows from this algebraic exclusion.

## Actionable disposition

1. **Canonical recovery remains absent.** A useful next artifact is the original MATLAB R2014a driver/configuration or archived project/export that identifies `c_P`, `G_P`, the implemented input matrix and the sixteen-stage run together. Another copy of the same PDF or byte-identical Word manuscript does not add that evidence.
2. **Editorial correction remains separate.** The scalar `P=[−1,1]` model and `B c_2` center formula are dimensionally coherent and already have their own reference ID/checks. This investigation adds no authorial confirmation, so it cannot relabel that model as recovered R29 input or claim its published timing/plots were reproduced.
3. **Owner/source-variant decision is still the precise unresolved item.** [The recorded input-recovery direction](https://github.com/butahlecoq/controlled-systems-lab/issues/521#issuecomment-6302807092) allows reconstruction from articles while reserving ambiguous intent for explicit disposition. The current work does not manufacture that disposition, ask the user to repeat it, or reopen a benchmark gate by inference. Keep #8 open; propagate the bounded negative scope to #2/#6 rather than treating it as proof of historical nonexistence.

No public API, dependency, installation, executable example or publication workflow changed. No release/package action or numerical rerun is needed for this research note. The private scratch inventories/hashes make the archive pass auditable without committing original sources, extracted text, administrative content or credentials.
