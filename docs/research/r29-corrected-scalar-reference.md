# R29 corrected scalar-input reachability reference

Date: 2026-10-16. Status: **editorial mathematical reference**, not a
reproduction of the historical executable or its timings. This case is
separate from B04 and does not specify an objective or optimal control family.
The [source-to-input audit](zonotope-paper-input-audit.md) preserves the
printed ambiguities and their provenance.

## Input authority

| Input | Authority and interpretation |
| --- | --- |
| Four-state `A`, `B=(4,0,2,0)^T`, `c_X0=(1150,119600,430,44720)^T`, `G_X0=diag(20,500,10,300)`, 16 transitions, scalar `u(t)` and `|u(t)|<=1` | Printed in R29 p. 108; exact values and source SHA-256 are in the [versioned scenario](../../benchmarks/scenarios/r29-corrected-scalar-reference.json). |
| `P(t)=Z(0,[1])=[-1,1]`, independent scalar factor `u.t` at each step | **Inferred** from the printed scalar bound and `B` shape. R29 instead prints four-component control zonotope data and `Ac2` in an image labelled `B Z_P`; the paper's recurrence and dimensions motivate this correction. It is not recovered run input or a claim about author intent. |

The [saved exact record](evidence/r29-corrected-scalar-reference.json) binds
the scenario and checker UTF-8/LF-normalized byte hashes, R29 and A22 original
source hashes, all 20 terminal
factor IDs and generator columns, and 17 verified stage counts. The record is
computed with Python `Fraction`: printed decimal `-6.5` is interpreted as the
exact rational `-13/2`, with no binary64 step. The checker compares iterative
unreduced propagation against a separate closed-form calculation at every
stage; [literal regression tests](tools/test_r29_reference.py) anchor the
terminal result independently of either calculation.

## Derived result

Write `A=I+N`. For the printed `A`, `N²=0`, so `A^k=I+kN`. With the inferred
zero control center, the terminal center is

```text
A^16 c_X0 = (1150, 119600 - 16·6.5·1150,
             430, 44720 - 16·6.5·430)
          = (1150, 0, 430, 0).
```

The four initial factors become the columns
`(20,-2080,0,0)`, `(0,500,0,0)`, `(0,0,10,-1040)` and `(0,0,0,300)`.
For action stage `t`, the terminal column is
`A^(15-t)B=(4,-26(15-t),2,-13(15-t))`. Thus `u.0` contributes
`(4,-390,2,-195)` and `u.15` contributes `(4,0,2,0)`. The 16 separate
control factors and four initial factors give **20 unreduced columns**.

Independent per-coordinate projection extrema of this exact zonotope are
`[1066,1234]`, `[-5700,5700]`, `[388,472]` and `[-2900,2900]`. These are
coordinate intervals; their Cartesian product is not asserted to be the
reachable set. For example, the second-coordinate radius is
`2080 + 500 + 26·(0+...+15) = 5700`; the fourth is
`1040 + 300 + 13·(0+...+15) = 2900`.

The recurrence represents the reachable set of the **corrected reference
model** in real arithmetic. Every initial and stage factor remains identified,
so a coordinate box or a few endpoint witnesses cannot replace the joint
generator relation. No stage constraints or terminal criterion are specified
here. The checked result does not establish a historical implementation match,
global optimality, a complete optimal family, binary64 enclosure, or a
performance comparison.

## Native geometry-port replay

The [C++ contract test](../../tests/contract/geometry/r29_scalar_reference_tests.cpp)
replays this *inferred* case through the registered
`csl.geometry.generators.operations@1.1.0` port. At each of 16 transitions it
applies `A` to the current zonotope, applies `B` to a fresh scalar factor
`u.t`, then forms an independent Minkowski sum. It checks all 17 stage centers,
generator counts and ordered factor identities, plus every terminal generator
column and the four coordinate intervals against the separately saved
exact-rational reference. The regression uses the public operation/evidence
boundary, with numerical assurance and no reduction or vertex conversion.

The printed coefficients and all checked intermediate results in this
particular recurrence are exactly representable in binary64. Exact equality
in this test is a property of this fixture; the adapter's general binary64
operations have no validated rounding enclosure or global error bound. This
replay also supplies no objective, optimal-family coverage evidence, historical
run match, or timing comparison. Issue #8 remains open for those separate
questions and broader interchangeable geometry acceptance.

## Reproduce

From the repository root:

```powershell
python -B docs/research/tools/check_r29_reference.py --verify-record docs/research/evidence/r29-corrected-scalar-reference.json
python -B -m unittest docs/research/tools/test_r29_reference.py
# After configuring a native build as documented in the repository README:
python -m cmake --build build/dev --config Release --target r29_scalar_reference_tests
ctest --test-dir build/dev -C Release -R '^r29_scalar_reference_tests$' --output-on-failure
```

The scenario has its own ID. Do not substitute it for R29's printed
four-component control data, the archived A04 active three-state/five-step
script, or B04's unrelated fuel problem.
