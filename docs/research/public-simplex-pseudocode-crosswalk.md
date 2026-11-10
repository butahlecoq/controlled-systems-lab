# Public simplex-hull pseudocode: source and method crosswalk

2026-11-10. This bounded [issue #2](https://github.com/butahlecoq/controlled-systems-lab/issues/2) follow-up identifies a public operational specification. It recovers neither an original Pascal/Delphi project nor the historical L05 modified driver. Keep #2 open.

## Newly inspected publisher source

Bulaev V. V. and Osipov I. O., *The Modified Algorithm for the Linear Discrete-Time Dynamic Systems Reachable Sets Computation*, Bulletin of the South Ural State University, Computer Technologies, Automatic Control, Radio Electronics, 2018, volume 18, number 1, pages 56–62, DOI [10.14529/ctcr180106](https://doi.org/10.14529/ctcr180106). Canonical [publisher PDF](https://vestnik.susu.ru/ctcr/article/download/7186/5994).

Access qualification: the publisher PDF's complete seven-page indexed text was read on 2026-11-10 through web retrieval. Direct HTTPS download timed out after 40 seconds; HTTP connection also timed out. No local PDF bytes were obtained, no SHA-256 is asserted, and typeset page images were not available for visual formula verification. This reading identifies the publication, not an immutable downloaded file or a supplementary code release.

Source summary: section 2, printed pages 57–60, supplies pseudocode for `ReachSets`, `ConvSM` and `SimplexHull`. It constructs affine state/control corner sums, traverses candidate columns, and uses an augmented simplex tableau to classify/delete points and promote basis columns. The tableau includes a row of ones; the subsequent row is a column sum. The deletion test sums absolute transformed coordinates after removing the last row, with threshold `1+epsilon`; `epsilon=1e-9` is an example. The paper presents exact linear reachable sets, with a MATLAB 8.4 R2014b numerical example. Reference [3] identifies Bulaev/Shorikov's ITIS 2017 paper, pages 47–52. No source-download or program-registration identifier was found in the inspected text. These are paper descriptions, not verified correctness or performance claims.

## What the affine augmentation means

The following is an independent algebraic interpretation under explicit basis premises, not a claim that every printed pivot reaches such a basis.

Let original points be `p_j` in `R^n`, and let `D` be the diagonal row-sign transformation applied for the tested point. Append a homogeneous coordinate to each point: `h_j=(D p_j,1)`. Suppose the retained basis consists of `n+1` affinely independent **original point columns**, so `H=[h_b1,...,h_b(n+1)]` is invertible. For any original point `q`, define `lambda=H^(-1)(D q,1)`. Its last homogeneous equation gives `sum(lambda)=1`; the other equations give `q=sum_i lambda_i p_bi`. Thus `lambda>=0` certifies membership in the retained basis simplex.

This is affine/barycentric geometry. It is not the ordinary linear-coordinate criterion for the centrally symmetric hull of paired `+/-` basis vectors. If artificial basis columns remain, or the point basis is singular/lower-dimensional, the preceding argument does not apply automatically; the actual basis and residual conditions need checking.

For exactly normalized affine weights,

`sum_i |lambda_i| = 1 + 2 sum_{lambda_i<0} |lambda_i|`.

Therefore an exact nonnegative normalized representation is a sound deletion certificate, independently of whether the basis points are extreme in the full input hull. Conversely, the floating test `sum |lambda_i| < 1+epsilon` permits small negative weight mass. For the segment with endpoints `0,1`, weights `(-epsilon/4,1+epsilon/4)` sum to one and pass that strict threshold for positive epsilon, yet represent the exterior point `1+epsilon/4`. This elementary counterexample qualifies the tolerant criterion, not the whole published implementation: no actual paper run or pivot trajectory was reconstructed. Setting epsilon to zero in the strict inequality would also not be equivalent to the exact nonnegative test. Validated inclusion requires actual coefficient/residual checks or a proved error enclosure.

## Correspondence and limits

| Existing source or record | Relation to the newly read paper | What remains unestablished |
|---|---|---|
| A43, Bulaev/Shorikov ITIS17, SHA-256 `a90a3e404807238886122dfdfc91a5f18697949137a8d9744af7180508de848a` | The supplied local PDF matches the [registered A43 hash](archive-selected-sources.json). Its pages 5–7 explicitly use homogeneous normalization and nonnegative retained-basis coefficients for batch deletion, and distinguish feasible basis points from true extreme points. Its authors/title match the new paper's reference [3]. | Citation correspondence is not byte identity with the published proceedings version. A43's pivot/tie discussion does not automatically prove all branches of the later pseudocode. |
| A44, Goranov/Shorikov ITIS17, SHA-256 `493917da7d8ac669a470a978780a2ca269ce9da1b594365f49c6ebd572388fd7` | The supplied local PDF matches the registered A44 hash. Its pages 6–7 use incremental enlarged-hull vertexhood plus a final recheck, as recorded in the [proof audit](reachability-proof-audit.md#source-authority-and-review-disposition). | This is a separate operational rule, not interchangeable with batch basis deletion or L05's underspecified support-hyperplane wording. |
| Archived `ConvSM_mod` / `Simplex_Hull_mod` and their [floating replay](tools/check_l05_dim4_retention.py) | The replay also augments with ones and a column-sum row, retains basis columns, and uses an absolute-coordinate deletion threshold. The [predicate crosswalk](l05-retention-predicate-crosswalk.md) pins the original source hashes and its `1e-6` tolerance. | Similar structure and names do not establish line-for-line equivalence. This pass did not rerun the private MATLAB source or requalify any old capture as faithful to the new paper. Pivot ties, index movement, artificial bases, tolerances and degeneracy need a separate literal crosswalk. |
| L05, supplied/publisher 1063 article | The [L05 clarification in PR #928](https://github.com/butahlecoq/controlled-systems-lab/pull/928) distinguishes auxiliary approximation from its full-vertex promise. | This new public simplex specification does not resolve L05's farthest-first support predicate or identify the 153-vertex Table 1 driver. |

The advance is public access to named procedures and an operational tableau specification corresponding to an already known research lineage. It is not discovery of the underlying affine-deletion proof, which the existing audit already treats conditionally.

## Separate leads and bounded search limits

The distinct 2017 Bulaev/Osipov item, *On a modified recurrent algebraic method for constructing reachable sets of linear discrete dynamic systems*, Rocket and Space Technology, volume 1, number 2(10), pages 4–15, remains **citation-only** here. It appears in [GUAP's 2024 proceedings](https://guap.ru/content/aai/sbornik2024.pdf) and the bibliography of an [institutionally hosted 2022 dissertation](https://www.spiiras.nw.ru/dissovet/wp-content/uploads/2022/11/ushakovva-kand.-dis._itog-v3.pdf). The [NPO Automatics conference page](https://www.npoa.ru/about/socialnaya-politika/smus/meropriyatiya-sms/) identifies its collection-publication activity, but that does not recover this particular full text.

Exact procedure-name/author searches produced no positive original code supplement in this pass. The URFU repository was blocked by the web tool's robots policy; its holdings were not exhaustively searched. The already recorded PROGNOZ-2022 institutional registration is a separate later lead, not recovered initial source. No author contact, code execution, benchmark, installation, license inference or original/private redistribution occurred.

Next useful work is typeset verification and byte identification of the 2018 PDF, recovery of the distinct 2017 item, and a literal versioned correspondence audit before adopting any procedure. This note changes no public API, dependency, installation or publication workflow; no release/package update is needed.
