# Set representations and the Ellipsoidal Toolbox

Review date: 2026-10-11. Targeted extension of the [recent research review](../research/recent-research.md). Sources predating 2021-10-11 are foundational analogues; later revisions of earlier preprints are identified separately. Architecture consequences below are proposals, not measured speedups. No external library has been installed or benchmarked.

## Ellipsoidal methods found in the archive

L06/L07 cite Kurzhanski and Varaiya's 2002 work and Kurzhanskiy and Varaiya's 2011 reach-set/control-synthesis paper. L11/L12 also cite Ellipsoidal Calculus for Estimation and Control (1997). The supplied inventory does not contain a separate Ellipsoidal Toolbox source distribution. This establishes a bibliographic connection, not which historical toolbox/version the owner used.

The likely software counterpart is [Ellipsoidal Toolbox (ET)](https://github.com/SystemAnalysisDpt-CMC-MSU/ellipsoids), originating with Alex A. Kurzhanskiy and Pravin Varaiya's [2006 Berkeley report](https://ptolemy.berkeley.edu/projects/chess/pubs/93.html). Distinguish A. B. Kurzhanski's foundational work from A. A. Kurzhanskiy's software/papers when assigning authorship.

The project describes MATLAB routines for ellipsoid/hyperplane geometry and forward/backward reachability, including disturbance models. Its [website](https://systemanalysisdpt-cmc-msu.github.io/ellipsoids/) advertises ET 2.1 from October 2015, documents ET 2.0.1, and lists CVX, MPT3 and MATLAB dependencies. This page does not establish current MATLAB compatibility or recent maintenance. Check a pinned revision and environment before using it as an executable reference.

The [ellipsoidal-calculus manual](https://systemanalysisdpt-cmc-msu.github.io/ellipsoids/doc/chap_ellcalc.html) supports positive-semidefinite, including degenerate, shape matrices. In curated notation:

~~~math
\mathcal E(c,Q)=\{c+Q^{1/2}z:\|z\|_2\le1\},\quad Q\succeq0,
\qquad h_{\mathcal E}(l)=l^Tc+\sqrt{l^TQl}.
~~~

An affine image is an ellipsoid with center Ac+a and shape AQA^T. Minkowski sums, differences and intersections generally leave the single-ellipsoid class; the manual supplies inner/outer approximations. Preserve direction, assumptions and degeneracy in the operation contract. A shape matrix is not automatically a statistical covariance, and an ellipsoid is not automatically a probabilistic confidence region.

A finite intersection of valid outer ellipsoids remains an outer set; a finite union of valid inner ellipsoids remains an inner set. Neither need be a single ellipsoid. Implement these as composite/lazy representations with separate membership/support/projection capabilities. Exact parametrization by a theoretically complete family does not make a finite directional sample exact.

**Proposed role:** EllipsoidRepresentation, EllipsoidalApproximationStrategy and directional family construction are separate plugins. ET can be an external scientific comparison runner with versioned input/result files. Its MATLAB classes should not become the native C++ API. A future native implementation can reproduce selected formulas under independent inclusion checks.

A [Python port announced on PyPI](https://pypi.org/project/ellipsoidal-toolbox/) has release 1.0.0 dated 16 March 2026 and credits the original toolbox. This is a possible reference integration, not evidence of numerical equivalence, complete coverage, or author endorsement. It has not been tested here.

## A relevant recent ellipsoidal development

Liu, Manzie and Dower's [HJB approach](https://arxiv.org/abs/2401.06352) was submitted in January 2024 and revised in February 2025; the record links DOI 10.1109/TAC.2024.3512619. It derives inner unions and outer intersections of ellipsoidal sets for continuous-time LTV systems with ellipsoidal input and terminal/initial sets. The abstract connects their dynamics to HJB sub/supersolutions and boundary contact.

**Design inference:** support families and approximation-strategy replacement, rather than only one ellipsoid per stage. The published construction is not automatically a discrete-time, polytopic-control, finite-action or robust-game solver. Read the proofs and numerical-integration assumptions before importing a guarantee. Current reading depth: abstract and metadata.

## Representation catalog and extension priorities

| Representation | Potential use | Main boundary | Initial priority |
|---|---|---|---|
| V/H polyhedra | Reference geometry, state constraints, linear optimal faces | Bounded vertex form differs from unbounded polyhedron; conversion output can grow | First implementation slice |
| Zonotopes | Generator propagation for suitable affine dynamics/domains | Intersections and discrete unions need richer forms; reduction may lose exactness | Early |
| Constrained zonotopes (CZ) | Polytopes and dependency-preserving generator constraints | Projection/query costs and generator/constraint growth | Early |
| Boxes / parallelotopes | Cheap compatible bounds and reduction targets | Orientation and enclosure direction matter | Early auxiliary |
| Ellipsoids / directional families | Smooth bounds, ellipsoidal uncertainty, reachability comparison | Most set operations require approximations/composites | Early comparison |
| Lazy support/expression sets | Query-driven propagation without full materialization | Direction sampling and unsupported queries must be explicit | Early extension |
| Ellipsotopes | Combine generator and ellipsoidal geometry | Convex queries need appropriate optimization backend | Later candidate |
| Hybrid zonotopes / unions | Preserve nonconvex discrete alternatives | Binary feasibility and enumeration can remain difficult | Later candidate |
| Sparse polynomial zonotopes | Preserve nonlinear factor dependencies | General queries may be nonconvex; validated remainder needed | Later nonlinear work |
| Constrained polynomial zonotopes | Rich nonconvex algebra with constraints | Compact algebra does not guarantee cheap decision queries | Later nonlinear work |

[Ellipsotopes](https://arxiv.org/abs/2108.01750) combine ellipsoid/zonotope features, with closed-form affine, Minkowski and intersection operations and convex collision checking as described by the authors. First submission: 3 August 2021, before our strict window; revisions include 11 October 2021 and June 2022. Treat this as an adjacent development with later revisions, not a new first publication inside the window. Reading depth: abstract and revision history.

[Hybrid zonotopes](https://arxiv.org/abs/2106.14831) add binary factors to encode unions of constrained zonotopes compactly. First submission: June 2021, outside the window; revisions: May 2022 and April 2023. [Functional-decomposition reachability](https://arxiv.org/abs/2304.06827), April 2023, is a later extension. A compact representation of many alternatives does not eliminate the cost of recovering every alternative. Reading depth: abstracts and metadata.

[Constrained polynomial zonotopes](https://link.springer.com/article/10.1007/s00236-023-00437-5), Kochdumper and Althoff, Acta Informatica, published 5 May 2023, provide nonconvex set algebra including intersection, union and polynomial maps. The paper's polynomial representation-operation complexity is not a claim that every optimization, emptiness or membership query is polynomial. Reading depth: abstract, introduction and definition overview. [Sparse polynomial zonotopes](https://arxiv.org/abs/1901.01780) predate the strict window (2019 submission, 2020 revision); record provenance rather than counting the class as a 2021–2026 invention.

No universal best representation follows from this catalog. Select by operations, geometry, dependence, required guarantee and output scope. A conversion graph should offer equivalent routes separately from explicit inner/outer relaxations.

## Recovered owner-authored zonotope paper

External source R29: [Shorikov and Kalev, Reachable set computation for solving fuel consumption terminal control problem using zonotopes](https://ceur-ws.org/Vol-1825/p13.pdf), CEUR volume 1825, pages 103–110; conference 16 November 2016, proceedings published 2017. A local copy and editable TeX source were subsequently recovered as A21–A22 in the [larger archive](../research/archive-followup.md); they are separate from the original 31-item inventory.

It gives exact nominal generator propagation when initial/control sets are zonotopes; this does not extend unchanged to arbitrary state intersections. Its example has four states and sixteen steps, with both compared implementations reported below 0.5 seconds. Vertex conversion is identified as costly.

The typeset PDF and editable source both print `Ac2` in Algorithm 1's control-image center and a four-component control-set description beside a scalar input and a `4×1` input matrix. The [source-to-input audit](../research/zonotope-paper-input-audit.md) preserves those forms, derives the dimensionally consistent scalar-control reference interpretation, and identifies the unmatched historical run. This does not validate a corrected numerical baseline or the complete optimal family. Reading depth: visually checked PDF pp. 107–108 and corresponding TeX/model lines; full proof and executable correspondence remain open.

**Design inference:** generator propagation and vertex materialization should be separately selectable. Preserve temporal generator identities for solution recovery. Add this reachability case as a separate baseline after input reconciliation; it is not already a complete optimal-family reproduction.
