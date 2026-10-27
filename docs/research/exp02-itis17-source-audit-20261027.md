# ITIS'17 LP hull methods: source and Pascal audit

This note records the method identity and source availability for the optional LP hull comparators requested for EXP-02. It is a source audit; no code or benchmark was run.

## Primary paper sources

The two PDFs were present in the main checkout under `papers/papers_for_professor/` during this audit. Their SHA-256 values are included because the papers directory is not present in this isolated worktree and the source PDFs are not tracked here.

| Comparator ID | Paper | Source identity | Method relevant to a finite point cloud |
|---|---|---|---|
| A43 | V. V. Bulaev and A. F. Shorikov, “Модификация общего рекуррентного алгебраического метода построения областей достижимости линейных дискретных управляемых систем” (2017) | `Булаев В.В. Шориков А.Ф. ИТИС17.pdf`; SHA-256 `a90a3e404807238886122dfdfc91a5f18697949137a8d9744af7180508de848a`; relevant PDF pp. 3–7 | Tests each candidate by a convex-combination feasibility LP using an artificial basis. After a feasible basis is found, it also tests nonbasic point columns for nonnegative normalized coordinates over that basis, allowing batch deletion of certified redundant points. It proposes a largest-norm pivot/tie choice to obtain a basis of hull vertices, but does not establish a general degeneracy/pivot proof for that stronger claim. |
| A44 | A. Yu. Goranov and A. F. Shorikov, “Модифицированный рекуррентный метод построения области достижимости линейной дискретной динамической системы” (2017) | `Горанов А.Ю. Шориков А.Ф. ИТИС17.pdf`; SHA-256 `493917da7d8ac669a470a978780a2ca269ce9da1b594365f49c6ebd572388fd7`; relevant PDF pp. 4–7 | Orders points using normalized distance from a bounding-box center, seeds a candidate set, tests each remaining point by LP membership against the current hull, and finally rechecks candidates. The description says both “increasing distance” and that the first `k+1` points are the most distant, so the ordering direction is ambiguous in the paper text. |

Both methods are finite-point convex-hull reducers based on LP/simplex feasibility. They are not geometric QuickHull implementations. A comparison can feed them the same 2D point clouds as QuickHull and independently check hull equality, but should identify the LP and geometric method families separately and apply the LP certificate/tolerance checks.

## Existing implementation correspondence

The repository's OPT-06 basis-reuse reducer is related to A43's batch deletion; OPT-07 ordered reduction is related to A44's incremental filtering. Neither should be relabeled as a paper reproduction without step-level correspondence and separate method identities. A safe A43 variant can delete only points with explicit nonnegative normalized certificates and then perform a complete final redundancy or independent hull-equality check. Treat basis extremality under the paper's largest-norm rule as a separate, unproven claim. For A44, record the selected ordering interpretation and retain the final LP recheck.

The source-specific proof discussion is in [the reachability proof audit](reachability-proof-audit.md#3-equality-for-certified-deletion-and-a44). It also cautions that these papers cannot be attributed as the exact references behind other papers without matching bibliographic evidence.

## Pascal source search

No `.pas`, `.pp`, or `.p` implementation path was found in the repository's Git history or the searched project/home files. The local selected-source register records `Статьи/А.Ф. Шориков/btulshor.pas`, but that is a different legacy method and is not evidence for either A43 or A44. The available RAR archive `papers/papers_for_professor/Статьи Шориков, Калёв.rar` contains three DOC files (a MСНТ paper, publication metadata, and a 2016 ITIS paper); its member list contains no Pascal source and no ITIS'17 code. Accordingly, no historical Pascal correspondence or results can be claimed. Reopen this search if the original source files or an archive containing them become available.

## Benchmark identity guidance

Keep separate rows for QuickHull, generic LP baseline, OPT-06, OPT-07, and any new faithful/adapted A43 or A44 implementation. Compare hull geometry and point identities on identical canonicalized finite clouds; report LP feasibility/certificate outcomes separately from exact geometric orientation results. Do not import timing claims from the papers' reachability experiments as QuickHull measurements.
