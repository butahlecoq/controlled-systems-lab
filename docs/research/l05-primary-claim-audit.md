# L05 primary paper: reachability and approximation claims

Date: 2026-10-19. This source audit reads the hash-identified L05 paper, [inventory record L05](inventory.json), SHA-256 `dfc76d4d33dad578567f851ae8169a44af290d2e17ea826cec46271dde2d311d`. The publisher's [article record](https://vestnikmi.bsu.ru/?article=1063&issue=34&rus=) links the same paper. The local PDF was checked visually on PDF pages 3-12 (printed pages 54-63); it remains private and is not copied into this repository.

## Exact reference set in the paper

On PDF pp. 3-4 (printed pp. 54-55), L05 starts with a continuously differentiable nonlinear recurrence and says that the linearization procedure is outside the paper's scope: a corresponding linear model is assumed to have already been formed. It then assumes a nonsingular state matrix and convex, closed, bounded polytopes for the initial state, stage states, and controls.

Definition 1, equation (6), defines the reachable set using complete histories of that **linear model**, with the stated state and control constraints. Equation (7) gives its one-step recurrence. The general algorithm on PDF pp. 5-6 forms pairwise affine images, takes their convex hull, converts to halfspaces, clips by the stage constraint, and converts back. The conclusion on PDF p. 11 calls this general method exact for the constrained linear system and cites prior works [2-4]; L05 does not reproduce those proofs.

The printed pseudocode initializes its reachable set with the single point `{x0}`. It therefore directly covers a fixed initial state. Although the surrounding assumptions allow an initial-state polytope, applying the recurrence to a general initial polytope requires initializing from all of its vertices (or an equivalent exact representation); the printed initialization does not show that extension. See the [reachability proof audit](reachability-proof-audit.md) for this distinction.

Thus the paper's exact mathematical reference is the history-defined affine set `R_t^lin`. Under exact set operations, independent convex controls, affine dynamics, and exact stage clipping, the stated recurrence computes `R_t^lin`. The [reachability proof audit](reachability-proof-audit.md) supplies the detailed induction and distinguishes it from the floating implementation.

## Modified vertex selection

The modified procedure on PDF pp. 7-8 sorts an input point set by distance from the center of its minimum bounding parallelepiped, seeds a hull with `n+1` points, and uses linear programs to decide whether later points lie on an extreme supporting hyperplane of the current candidate hull. It then hulls the retained candidates. L05 calls this a modification/approximation, attributes the auxiliary-set reduction to reference [6], and describes the final result as the vertices of the reachable set.

L05 gives pseudocode but no theorem or proof that its point-discard rule preserves the complete hull. Its equality claim therefore needs the cited reduction proof and an identified implementation before it can be accepted as established; the status of the cited source [6] is summarized in the [L05 source dossier](l05-example1-source-dossier.md#cited-source-and-generator-search). Separately, the proof audit shows the weaker conditional guarantee: if the retained points are feasible points of the affine reachable set, their exact convex hull is an **inner** affine reachable set; equality requires a valid completeness argument for discarded points. Floating LP and hull calculations do not provide validated inclusion by themselves.

The current archived four-state source experiment reinforces this distinction: the active general path numerically reproduces the complete 756-vertex linear hull in a floating translation, while the translated commented reduction yields 148 vertices and does not reproduce the printed modified row of 153 vertices. Its NumPy rank-order sensitivity and limitations are recorded in the [stagewise reduction report](l05-example2-approximation-hypothesis.md). Neither implementation result identifies the code that generated Table 1.

## Nonlinear comparison

The paper's numerical section (PDF pp. 8-11, printed pp. 59-62) presents the nonlinear recurrences separately from the linear models. For Example 1, the printed nonlinear initial state is `(410,300)` and the linear initial state is `(1,2)`. For Example 2, they are `(1,1,1,1)` and `(1,-1,1,1)`. The inspected pages do not specify a common-coordinate transformation that would make their volumes directly comparable.

Table 1 reports separate linear general, linear modified, and nonlinear vertex/volume rows. Figure 2 shows projections of linear and nonlinear reachable regions. L05 reports no evaluated Taylor remainder set, justified common validity domain, propagated model-error tube, discretization or rounding enclosure, or all-history inclusion certificate for these comparisons. They are numerical comparisons as reported in the article, not proof that the linear set is an inner or outer enclosure of the nonlinear set. The smoothness assumption alone supplies none of those bounds.

For future comparisons, use the same named reference set and coordinates, and report both directed distances or a justified support-function bound, as defined in the [source-to-experiment comparison](reachability-source-correspondence.md#contracts-and-measurable-references) and [proof audit](reachability-proof-audit.md#metrics-and-the-table-1-discrepancy). Vertex counts, volumes, and plotted projections remain descriptive unless accompanied by a containment or coverage proof.

## Effect on issue #4

This audit sharpens the article-level contract: exact reachability is defined for the linear surrogate; the modified construction is an unproved reduction in this paper with a conditional inner-set interpretation; the reported nonlinear comparison has no validated relation to the physical reachable set. It does not establish the cited reduction's proof, recover the Table 1 driver or coordinate map, or supply evaluated nonlinear error bounds. Issue #4 remains open for those historical and physical-model gates.
