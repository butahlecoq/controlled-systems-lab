# Independent objective evaluation and reformulation oracles

These [TEST-04](../superpowers/plans/tickets/TEST-04.md) fixtures exercise the
existing [terminal objective contract](terminal-objectives.md) through
`snapshot`, `evaluate`, `square_residual_norm`, and retained public accessors.
The [evaluator tests](../../tests/unit/objectives/evaluator_test.cpp) cover
original costs and rejected inputs. The
[reformulation tests](../../tests/unit/objectives/reformulation_test.cpp) cover
literal coefficients, costs, transformation provenance and analytic examples.
The original [implementation tests](../../tests/unit/objectives/objectives_tests.cpp)
remain unchanged, including lifetime, zero-dimensional and arithmetic-failure
regressions.

The bounded sets below are mathematical fixtures. The objective API accepts no
box constraints, solves no optimization problem and enumerates no minimizers.
The algebra establishes complete minimizer sets for these particular examples;
the executable tests check selected points against independently supplied
literals. Their finite witness lists are not evidence of general family
completeness. No solver, native backend or timing threshold is involved.

## Original conventions and required rectangular fixture

At `x=[1,2]`, `c=[2,-1], d=3` gives `c^T x+d=3`. Under the convention
`0.5 x^T Q x+q^T x+c`, `Q=diag(2,0), q=[0,1], c=3` gives **6**.
At the origin both costs are **3**; at `[2,-1]` they are **8** and **6**.
These checks distinguish the offset, coefficient order and one-half factor.

For `L=[[1,0,0],[0,1,1]], r=[1,4]`, the point `[1,1,3]` has zero
residual. At `[4,1,7]` the residual is `[3,4]`, so the original norm is **5**
and its square is **25**. The literal quadratic data are:

```
Q = [[2,0,0], [0,2,2], [0,2,2]]
q = [-2,-8,-8]
c = 17
```

The tests check both costs independently against literals. They never derive
the expected original norm from the computed squared value.

## Bounded minimizer sets

Write `x=[x0,x1,x2]`. For nonnegative real costs, the square function is strictly
increasing; hence a pure norm and its square have the same argmin on a common
domain. The equality conditions below identify those sets explicitly.

| Fixture | Bounded domain | Complete minimizer set | Original / squared minimum |
|---|---|---|---|
| A: wide map, zero minimum | `[0,2] x [0,4] x [0,4]` | `{[1,t,4-t]: 0<=t<=4}` | 0 / 0 |
| B: wide map, nonzero minimum | `[0,1] x [0,4] x [0,4]` | `{[1,t,4-t]: 0<=t<=4}` | 2 / 4 |
| C: rank-one map | `[0,1]^3` | `{[t,1-t,s]: 0<=t,s<=1}` | 0 / 0 |
| D: constant residual | `[-1,1]^2` | Entire box | 5 / 25 |

**A.** Use the required wide map and `r=[1,4]`. The squared residual is
`(x0-1)^2+(x1+x2-4)^2`. Its lower bound zero is attained exactly when
`x0=1` and `x1+x2=4`; intersecting these equalities with the box gives the
displayed segment. Tests check both endpoints and its midpoint at **0/0**.
Off-family points `[0,0,4]` and `[1,1,2]` each give **1/1**.

**B.** Keep the wide map, change `r` to `[3,4]`, and use the smaller box.
Now `(x0-3)^2>=4`, with equality exactly at `x0=1`. The remaining square
vanishes exactly when `x1+x2=4`. Thus the same segment minimizes both criteria,
but the optimal values are **2** and **4**. Tests check `[1,0,4]`, `[1,2,2]`,
`[1,4,0]` and the nonminimizer `[0,0,4]`, whose costs are **3/9**.

**C.** Take `L=[[1,1,0],[2,2,0]], r=[1,2]`. The second row is twice the
first and the first is nonzero, so the rank is one. The squared residual is
`5(x0+x1-1)^2`. Equality at zero imposes `x0+x1=1` and leaves `x2` free in
the box, giving the two-parameter family. Tests include `[0,1,0]`, `[1,0,1]`
and `[0.5,0.5,0.25]` at **0/0**. At `[0,0,0]`, the costs are **sqrt(5)/5**.

**D.** Take the 2-by-2 zero map and `r=[3,4]`. Every point has residual
`[-3,-4]`, original cost **5** and squared cost **25**. Every point of the
box is therefore a minimizer; tests check opposite corners and the origin.

These arguments require neither differentiating the norm at zero nor assuming
positive definiteness or uniqueness. They are real-arithmetic derivations.
Floating expansion still has the conditioning, cancellation and arithmetic
limits described in the objective contract.

## Weights, offsets and transformation provenance

Use the tall map `L=[[2,0],[0,3],[0,0]], r=[2,6,4]`. Weights **2** and **3**
are encoded directly in L; r retains the target and constant-residual terms.
The squared cost is
`4(x0-1)^2+9(x1-2)^2+16`. Under the one-half convention this yields:

```
Q = [[8,0], [0,18]]
q = [-8,-36]
c = 56
```

At `[1,2]` the original cost is **4**, squared cost **16**. At `[0,0]` they
are **sqrt(56)** and **56**. Tests inspect every retained L/r and generated Q/q
entry, c, the `residual_norm_squared` transformation kind, and the explicitly
supplied numerical policy on both retained objectives. This records the
implemented provenance without inventing separate weight, unit or sum metadata.
The original cost is evaluated from `record.original()`.

## Why a mixed objective does not inherit the equivalence

On `[0,2]`, consider `f(x)=|x-1|+x/2`. For `x<=1`, it equals `1-x/2` and
decreases; for `x>=1`, it equals `3x/2-1` and increases. Its unique minimizer
is **1**, with value **0.5**.

Squaring only the residual gives `g(x)=(x-1)^2+x/2`, which equals
`(x-0.75)^2+0.4375`. Its unique minimizer is **0.75**, with value **0.4375**.
The literal test values make the ordering reversal explicit:

| x | Original sum f | Partially transformed sum g |
|---|---|---|
| 1 | 0.5 | 0.5 |
| 0.75 | 0.625 | 0.4375 |

The test adds values from separately published norm and linear objectives in
its own expressions. It does not implement a sum-objective API. Only the pure
norm is passed to `square_residual_norm`; separate admission tests check that
linear and quadratic inputs return `unsupported` at `objective.reformulation`.

## Invalid inputs and numerical assurance

Publication tests cover wrong residual target/storage shapes, rectangular Q,
Q/linear size mismatch, and positive infinity, negative infinity and NaN in
every coefficient role and offset. Evaluation tests cover wrong point lengths
and nonfinite coordinates for all three forms. They assert the documented
diagnostic code and field rather than merely requiring failure.

With absolute tolerance **0.0625** and relative tolerance **0**,
`Q=[[2,0.25],[0,2]]` fails symmetry, while `Q=[[1,2],[2,1]]` fails the PSD
policy with minimum eigenvalue -1. One-dimensional Q of **-0.03125** is
unresolved (`unsupported`); **-0.125** is invalid. `diag(2,0)` is accepted
semidefinite numerical data. A validated assurance request remains explicitly
unsupported. These are numerical-policy checks, not validated convexity proofs.

## Original test-first evidence and expansion history

TEST-04 expands an existing implementation; new passing tests do not establish
a new RED/GREEN implementation cycle. The retained OPT-01 implementation report
records original BASE `5f1eaa491a2d7526c3b95c4f7c150b6eeecd99e5` and HEAD
`bd3082875f403d4aa94677b5aa5ca254edb9b436`. It reports public executable tests
against compiled unsupported stubs before first implementing linear evaluation,
rectangular norm evaluation, quadratic policy, recorded squaring, assurance
validation and extreme-scale PSD protection. The first four cycles progressed
from failing cases to respectively 3, 8, 39 and 67 passing assertions. The report
explicitly distinguishes additional tests of already implemented behavior that
were not individually RED. Its original final suite had 13 cases and 265
assertions. These are retained historical observations, not runs repeated here.

The public [OPT-01 fix report](https://github.com/butahlecoq/controlled-systems-lab/pull/113#issuecomment-6112938942)
records a later genuine regression cycle: three new Q/q/c underflow tests failed
before the fix, then all 17 cases and 297 assertions passed. The
[controller reproduction recheck](https://github.com/butahlecoq/controlled-systems-lab/pull/113#issuecomment-6112939143)
independently confirmed that the originally flattened norm expansion was now
declined. The [specification review](https://github.com/butahlecoq/controlled-systems-lab/pull/113#issuecomment-6112979398)
distinguishes its executed checks from historical test-first evidence.

The TEST-04 evaluator and reformulation expansions both passed on their first
run against unchanged production code. No new production defect was found.
The original minimum suite and its underflow regressions remain intact.

## Acceptance trace and running the tests

| TEST-04 criterion | Evidence |
|---|---|
| 1: linear and half-quadratic costs | Evaluator literals 3 and 6, plus offsets |
| 2: rectangular zero and 5/25 | Evaluator and reformulation wide-map cases |
| 3: bounded minimizers, zero and rank deficiency | Analytic sets A-D and public evaluation witnesses |
| 4: invalid dimensions, finite data, Q properties | Evaluator diagnostics and numerical-policy cases |
| 5: pure transformation provenance and sums | Tall weighted fixture and mixed-objective counterexample |
| 6: minimum test-first implementation, independent expansion | Retained original suite and provenance above |

Build the `objective_evaluator_tests` and `objective_reformulation_tests` targets
with testing enabled, then run them through CTest. Full CTest also retains the
original `objectives_tests` and installed-package consumer checks. No expected
coefficient or cost is computed by a production helper inside these tests.
