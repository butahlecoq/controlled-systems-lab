# Phase-I mathematical lineage and saved variants

OPT-04 is an independently written C++20 equality/nonnegative feasibility kernel.
The evidence connects its problem formulation to L01/L03/L07 and A06. It does
not identify any saved file as a verified original author release. Local original
bytes were hash-checked during the reviewed design; raw copyrighted documents,
scans and source listings are not redistributed here. Source IDs are those of the
[algorithm inventory](algorithm-module-inventory.md).

| Source | SHA256 | Relevant evidence |
|---|---|---|
| L01, 1993 terminal-control article | `b468f67e7464256a3212552f72588c223e295f70f40867894afb841387449872` | Physical p5 problem2/(6), p8 algorithm1 step9: convex-combination feasibility, modified simplex, nonnegative RHS normalization and restoration of original signs. |
| L03, `pardalos.docx` | `4350cf20a2e458a9bd3cdb95e3ea8e306549b4b65d80fc5e3c5b89712d20dafb` | Sections3.3–3.4 distinguish per-point feasibility, additional classification from a completed basis, and ordering/grouping. The filename alone establishes no authorship. |
| L07, explanatory report PDF | `6bc149e7e1c63d1cff262ffd861898d528a3eee2b1c0b591aebde91c607f89fc` | Physical pp47–51, sections3.3–3.4, equations3.7/3.8. Displayed formulas on pp47/49 were visually checked: convex weights, sum-one constraint, artificial basis and augmented sum-plus-one row. Additional classifications on p50 are a separate layer. |
| A06, `btulshor.pas` | `06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442` | `KPABEP` lines73–126 adds affine/objective rows and normalizes signs; `MODIF` lines128–213 uses identity initialization, reduced costs/ratios, multiple objective phases and status codes. Fixed arrays and unavailable companion units were not adopted. |
| A25, `Simplex_Hull_Shor.m` | `cf401b763af706a582e411d4e3f17cd1bb7398bf1bd44fa6fa3e65637ee31034` | Lines1–32: fresh artificial basis, signs at5, ones and sum-plus-one at6, largest reduced-cost entering rule22–24, ratio25–27 and basis solves28–29. No finite execution cap or floating anti-cycling proof is supplied. |
| W06, `Works/Main_Shor.py` | `8192d85d70615700ecb4da4e85381d4280cc15ffc27db4770092ec5067e2bc2e` | Lines4–29: normalization8–9, but appended sum omits A25's plus-one; ratio24–26 retains zero directions and28 explicitly inverts B. A distinct unvalidated algebra/tolerance variant. |
| W05, `Works/Main_mod.py` | `988ca23a5298ad56e13eff6a8e22c6e02f9d116058d63e5d8cd41af339c3dddf` | Lines4–42: same sum difference;17–25 additionally classify/delete/reorder columns. This is more than a pivot-kernel variation. |

L03 paragraph extraction loses some equations, so the visually checked L07
formulas supplied that evidence. A16 `Simplex_Hull_mod.m` lines13–25 also separates
completed-basis deletion/reordering. `QLPHULL.m` grouping at44–64 is commented;
its final reduction at65–76 does not prove an archived recursive simplex method.
No legacy program was executed to infer correctness.

The product's independent derivation makes the auxiliary objective explicit:
`D=diag(sign-normalization)`, `N=D*A`, `q=abs(b)`, then minimize `sum(a)` subject
to `N*x+a=q`, `x,a>=0`. The initial artificial basis is I and the original-row
artificial columns are `D*e_i`. Original residuals and candidate evidence are
checked separately. This replaces neither a hull predicate nor the additional
classification/grouped algorithms in those sources. It also avoids choosing one
saved augmented-tableau variant by filename or presumed provenance.

The entering and leaving rules deliberately differ from A25's largest-reduced-
cost selection. Bland's primary paper, [New Finite Pivoting Rules for the Simplex
Method](https://doi.org/10.1287/moor.2.2.103), Mathematics of Operations Research
2(2),103–107 (1977), p104 rules1.2a/b and Theorem1.1, supplies least eligible
entering index and least basic-variable index among minimum-ratio ties. The
[primary article scan](https://people.ohio.edu/melkonia/math4620/bland.pdf) was
inspected during design. Its theorem concerns exact mathematical arithmetic.
The product's binary64 thresholds, rank/condition checks and finite cap are a
separate guarded numerical policy, documented in the [phase-I contract](../contracts/phase-one.md).

Literal triangle, signed degenerate, duplicate/tie, collinear, zero/contradictory
and original-space basis cases are derived independently, then compared with the
actual registered reference LP only for moderate well-separated fixtures.
Agreement with another numerical solver is not a proof of exact feasibility,
infeasibility, hull extremality, complete families or archival-code correctness.
