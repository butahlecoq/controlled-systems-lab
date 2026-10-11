# B04 saved witnesses and historical nonlinear replay

Date: 2026-10-11. Evidence variant: `b04-saved-witness-replay-v1`. Scope: saved-witness/replay evidence. This report curates an independently audited archival discovery for [SCI-B04-CURATION #108](https://github.com/butahlecoq/controlled-systems-lab/issues/108).

Three saved nominal histories and their nonlinear replays reproduce the rounded optimal-witness rows of Table 2. They use different initial flows and input coefficients from the displayed B04 model. The frozen-regulator coordinates also match, but their objective is **368.609780868**, in conflict with printed **368.45**. Its generator remains unresolved.

The [machine-readable evidence](evidence/b04-saved-witnesses.json) contains curated facts and aggregate computations, separate from executable scenarios. The [historical manifest](../../benchmarks/scenarios/b04-historical.json) remains an unchanged, non-executable transcription. The [reference checker](tools/check_b04_saved_witnesses.py) reads explicit private sources and reproduces the numerical checks. Neither three witnesses nor floating agreement establishes a complete constrained optimal family.

## Source identities and anchors

The [selected-source register](archive-selected-sources.json) retains A01 and assigns A39–A42 to the newly curated sources. All five filenames below are relative to the archive subdirectory `Семинар ИММ/Статья`. Original files and raw histories remain private and unchanged. Scratch discovery labels F72/E042 are replaced by stable A39/A41 identities here.

| ID | Original filename | Bytes | SHA-256 |
|---|---|---:|---|
| A01 | `ReachableSets.m` | 8645 | `e7010e0a830595029b9876b1511558514cec8398d2ffa290313a566ba6997558` |
| A39 | `1st.fig` | 1131239 | `1120e70dbf3a300d1f8c9ee19d1082632c3adbb24f5ac445802954b164181f38` |
| A40 | `program.m` | 3819 | `581a91dbb1041973f9559a6cac07657279a5e3f40091f04606216be0f97bac46` |
| A41 | `Shorikov_Kalev_Article_v4.pdf` | 858237 | `db1f29e55e9e3558b4f9eb4bd52c86931f210233d746a986610dab08102b3891` |
| A42 | `1st.png` | 106169 | `ccbe6aac3e9d265999b135a780cbd4fff060d8db574bc747f27e8216c824692d` |

A41 physical PDF pages 11–14 supply the model, objective, Table 2 and figures. The prior independent visual audit checked pages 3, 4, 6 and 11–14, plus A42's first-witness phase plot. Those visual facts are retained as audited source readings; the numerical checker does not parse or reinterpret PDF equations. Its optional article/image inputs verify their identities only. A11/A12 independently supply the [previously transcribed tables](b04-tables.md).

A39 is read as inert MAT graphics data. Prefix each object anchor below with `hgS_070000.` and append `.properties`. Python child indices are zero-based. `XData` is flow and `YData` is working-stock balance; oxidizer and fuel pairs produce coordinates `(x1,x2,x3,x4)` in `(kg/s,kg,kg/s,kg)`.

| Witness | Nominal oxidizer / fuel | Nonlinear oxidizer / fuel |
|---|---|---|
| 1 | `children[0].children[3]` / `children[2].children[51]` | `children[0].children[4]` / `children[2].children[54]` |
| 2 | `children[0].children[55]` / `children[2].children[52]` | `children[0].children[57]` / `children[2].children[55]` |
| 3 | `children[0].children[56]` / `children[2].children[53]` | `children[0].children[58]` / `children[2].children[56]` |

Each nominal coordinate has 17 values; each nonlinear coordinate has 10000. Frozen coordinates use `children[0].children[5]` and `children[2].children[57]`, each with 17 values. Their 33-vertex stair-display children are generated geometry, not additional histories. The private audit verified all 20 graphics property paths; the focused public checker reads only the seven relevant four-coordinate histories. The FIG's 2017-10-20 MAT-header timestamp identifies saved-file metadata, not a revision history for neighboring scripts.

## Saved nominal dynamics and inferred actions

All three histories begin at

$$x_0=(1220.28265395983,119500,440.005764648976,45300)^\top.$$

A01 line 23 comments these initial decimals; its active line 24 uses rounded flows. Lines 31 and 34 independently supply

$$B=(2208/110,0,-1152/110,0)^\top.$$

The saved stocks imply `h=-diff(x2)/x1[:-1]` between 6.249999999999994 and 6.250000000000006. With 16 transitions, the inferred nominal duration is 100 seconds. Set `A=I+N`, with only `N[1,0]=N[3,2]=-6.25` in zero-based notation. A01 line 30 supplies this stock recurrence form, but line 28 currently sets **T=12**. The current driver is not established as the exact T16 generator, and no chronology of changes is proven.

Effective actions are inferred as `u[k]=(x1[k+1]-x1[k])/(2208/110)`, conditional on the sourced B. Fuel-channel inference differs by at most 6.828e-15. These are not recovered original optimizer U variables. First actions are approximately -0.683290486439, -0.999999991287 and -0.999999997214, so the three saved histories do not share a fixed first action.

The independent matrix evaluation `x[k+1]-(A*x[k]+B*u[k])` has maximum absolute residual 5.684e-14; the equivalent stock-difference form reaches 7.276e-12 through cancellation. All inferred actions lie in [-1,1] at saved precision. Flows agree with the displayed flow box up to floating error: witness 1 reaches 1175.9999999999943, about 5.7e-12 below its lower bound. Neither exact feasibility nor a rounding certificate follows from this observation. A01 lines 18, 26 and 38 specify a flow box and control interval in its T12 version; they do not recover every original T16 stage constraint.

The changed B gives `12*B1+23*B3=0`. The stock invariant is

$$12x_2(16)+23x_4(16)=12(x_2(0)-100x_1(0))+23(x_4(0)-100x_3(0)).$$

For witness 1 the initial expression is -452.4434444409562 and the terminal expression is -452.4434444412941. This is floating recurrence evidence, not admissibility or family completeness.

## Objectives and conditional terminal calculation

A41 p. 12, A01 lines 80/192 and A40 line 57 give the original norm

$$\Phi(x)=\sqrt{(1200-x_1)^2+x_2^2+\frac{64}{9}(450-x_3)^2+\frac{64}{9}x_4^2+(x_2-\frac83x_4)^2}.$$

A01 minimizes its square and reports its square root. Evaluate the norm before rounding coordinates. Table 2's coordinate and objective precisions differ.

| Witness | Saved nominal norm | Saved nonlinear norm | Printed nonlinear norm |
|---|---:|---:|---:|
| 1 | 30.899136030045337 | 41.855290738349495 | 41.855 |
| 2 | 30.899136030147798 | 65.8744016598146 | 65.874 |
| 3 | 30.899136030017026 | 7.921766774950679 | 7.922 |

All optimal-witness coordinates round to their A41 p. 13 Table 2 rows. Nominal endpoints agree at publication precision; they are not exactly equal. The evidence records individual endpoint values and residuals.

A separate conditional calculation fixes saved x0, sourced B and h=6.25. Every affine-model endpoint has the form `A^16*x0 + B*s + N*B*w`, where `s=sum(u[k])` and `w=sum((15-k)*u[k])`. For the weighted residual map W in the [restoration report](b04-restoration.md), set `M=[B,NB]`, `V=W*M` and `y=W*A^16*x0-r`. Solving the two normal equations `(V^T V)(s,w)^T=-V^T y` gives approximately

$$ (s,w)=(-0.973436294984494,-19.970076348240628),\quad \Phi=30.899136030021875.$$

Its terminal point is `(1200.7431326932322,-22.928545021908576,450.20029748372275,-7.708734964262931)`. The largest saved terminal-coordinate difference is about 3.218e-5 for witness 2. Floating evaluation puts witness 3's norm about 4.85e-12 below this computed relaxation. This calculation explains the observed 30.899, but does not validate a constrained optimizer, recover stage domains, or certify the complete optimal control family.

## Source nonlinear kernel and historical time convention

A40 lines 2–11 set `K=8/3`, `P=528000`, `I=320`, `c1=dK=8/75`, `c2=-6700`, `c3=9000`, `c4=-15`, `c5=-12`. For accumulated effective action a, lines 18–22 and 30–34 calculate

$$K_m=K+dK+c_1a,\quad \delta=K_m-K,$$
$$P_p=P+c_2\delta^2+c_3\delta,\quad I_u=I+c_4\delta^2+c_5\delta,$$
$$m_g=P_p/I_u/(1+K_m),\quad m_o=m_g K_m.$$

The checker preserves the audited subtraction order `delta=Km-K`. The unused c6 is not part of these active equations. Printed Table 1 instead gives c2=-1675 and c3=2250. The script explicitly multiplies those coefficients by four; its physical/unit explanation remains unresolved. No coefficients are fitted to endpoints.

A40's exact replay convention is:

1. MATLAB sample 1 stores initial flows/stocks at interpreted time 0 (lines 14–22).
2. Samples 2–10000 perform 9999 advances of 0.01 seconds. Each stock update uses the **previous sample's flow** (lines 23, 35–36).
3. Actions 1–15 are accumulated at samples 626, 1251, ..., 9376, interpreted as 6.25, 12.5, ..., 93.75 seconds (lines 24–25).
4. Action 16 is forced at sample 10000, interpreted as **99.99 seconds**, not 100 seconds (lines 27–28). It changes final flows but cannot change final stocks.

These times are inferred from the matching kernel; the FIG stores phase coordinates without a clock vector. Removing the last action from witness 1 changes its final flows by approximately `(19.91129648549213,-10.948454768662998)` while both terminal stocks stay unchanged. A physically aligned 100-second replay would be a separate variant; none is introduced here.

The checker compares all 120000 scalar samples, with maximum diagonal residual 9.095e-13. Comparing every nominal replay with every saved nonlinear history gives this maximum absolute discrepancy matrix:

| Nominal-derived replay | Saved nonlinear 1 | Saved nonlinear 2 | Saved nonlinear 3 |
|---|---:|---:|---:|
| 1 | 9.095e-13 | 503.173 | 1085.514 |
| 2 | 503.173 | 4.547e-13 | 806.275 |
| 3 | 1085.514 | 806.275 | 4.547e-13 |

This supports full-history pairings beyond terminal rounding. A40 **line 12** sets `z=1` and comments row numbers; line 16 averages rows i and 11 of an unavailable U. Replaying inferred actions establishes the kernel, not the historical row selection. The Table 2 ideal reference is also separate: a zero-increment replay from the perturbed initial state has norm about 7371.256616, not zero (A41 p. 4 reference equations and p. 13 table).

## Frozen discrepancy and printed-model contradiction

The saved frozen endpoint is `(1190.4414912370798,101.7033430973679,455.1220439139795,-72.81705922737456)`. Its norm is 368.6097808680356. The printed coordinates themselves give 368.6068413472544. Their nearest-rounding box has half-widths `(0.05,0.05,0.005,0.0005)` and computed norm range `[368.54934883615726,368.66434608974293]`, excluding even the rounding interval of printed 368.45.

The squared norm's four partial derivatives have fixed signs across this box; the checker verifies those affine derivative signs at all 16 corners before using corner extrema. This is an explanatory floating calculation, not an outward-rounded enclosure. The gap is not terminal-coordinate rounding. Initial plotted frozen stocks differ from initial nominal stocks by about 0.025 times their first flows, but neither that clue nor the 17 saved points establishes full frozen timing, downsampling or generator. No frozen controller is replayed.

The original printed B04 model retains `x0=(1216.904,119500,438.787,45300)` and `B=(17,0,-12,0)` (A41 p. 11; L11 pp. 12–13). Its [exact rational check](b04-consistency.json) gives required stock invariant -2122.7; the reported optimizer gives -406.201, a gap of 1716.499 versus at most 0.0145 from reported stock rounding. Its affine-terminal norm lower bound is about 160.880653946, not 30.899. Missing constraints cannot lower that bound. Saved-run evidence does not repair or replace this historical contradiction.

## Remaining authority and bounded recovery

The prior private configuration search covered 31 of 34 inventoried top-level packages (three third-party libraries excluded), 373 selected source files, five parsed nonlibrary MAT workspaces, and eleven adjacent model XML inventories. It did not recover the exact T16 driver/U rows. This is bounded negative evidence: opaque MCOS/polyhedral MAT data, embedded equations, two mislabeled RTF documents, several binary/generated/model variants and sources outside the archive were not semantically exhausted. No new archive-wide search was performed for this curation.

Adjacent T16 adaptive drivers are distinct variants; they cannot supply canonical missing stage sets. A01's present row selections also differ from A40's U averaging. A41 p. 6 uses conflicting control index ranges (1..T-1 versus 0..T-1), p. 12 reports 100 controls, and p. 14 claims intersection-vertex coverage. Three saved histories do not establish those claims or resolve the indexing intent.

Before original issues [#1](https://github.com/butahlecoq/controlled-systems-lab/issues/1), [#2](https://github.com/butahlecoq/controlled-systems-lab/issues/2), [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6) or [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10) can meet their respective restoration obligations, remaining work includes canonical numerical stage domains and any stock restrictions; first-action convention; original T16 generating revision and U row mapping; coefficient/unit authority; frozen generator and objective conflict; and constrained optimum/family completeness checks. An explicitly authorized reference variant is another route, with its assumptions recorded separately. Delivery of #108 closes only this curation scope. Historical timing reports remain contextual; no speed claim is made.

## Reproducing the focused check

See [research utility commands](tools/README.md#b04-saved-witness-reference-check). The three required inputs are A39 FIG, A40 kernel and A01 driver; each must match its registered SHA-256 and byte count. Optional A41/A42 inputs add hash checks. NumPy and SciPy read numeric data only; original MATLAB, Simulink and native code are not executed. The published evidence includes the environment and aggregate output from a five-source run. Operational regression thresholds are declared there; they are not numerical certificates. Source/table visual interpretation remains the prior audit's provenance obligation.
