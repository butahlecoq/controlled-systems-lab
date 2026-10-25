# Published numerical baselines

Owner direction, 2026-10-11: use the numerical experiments near the ends of supplied articles as the starting quality baselines. The owner selected C++ for the main implementation, with C++20 as the working standard. No throughput or real-time requirement has yet been selected.

All numbers below are **reported**, unless explicitly labelled computed in this assessment. Different article revisions remain separate scenarios. Historical runtimes are context, not modern acceptance thresholds.

## Baseline register

| ID | Source | Problem | Reported result | Readiness |
|---|---|---|---|---|
| B01 | L01/L02 | General terminal control; L02 includes production planning | Equations/example remain in extracted source | Transcribe full numerical data before inclusion in executable suite |
| B02 | L05, PDF pp. 9–10 | Two nonlinear reachability approximations, dimensions 2 and 4 | Vertex counts, volumes and runtimes below | Initial-state/coordinate and approximation semantics require clarification |
| B03 | L07, PDF pp. 52–55 | Reachability and convex-hull algorithm comparisons | Runtime/iteration data below | Compare C++ translations of the baseline and modified algorithms with each other and with the modern algorithms on shared fixtures; historical replay inputs are not required |
| B04 | L11, PDF pp. 12–14 | Nominal convex terminal control, n=4, T=16 | Objective 30.899, runtime 0.4 s | Article-derived `b04-reference-v1` is defined for algorithm work; the historical row has a proved displayed-model/result inconsistency and unresolved generating inputs |
| B05 | L08, numerical-example section and Table 2 | Optimal adaptive vs open-loop, T=16 | Nine tabulated outcomes; 0.4 s open-loop, 10 s adaptive | Table 2 policy labels cross-checked to the published PDF; canonical run inputs and provenance remain unresolved |
| B06 | L09, PDF pp. 10–12 | Unconstrained finite-action minimax, n=4, T=5 | Worst-case 10.11, nonlinear trajectory 9.049, runtime 300 s | See the [B06 source audit](b06-source-audit.md); an owner-confirmed finite reference is now computed, while historical disturbance bounds and reproduction remain unresolved |
| B07 | L10, PDF pp. 10–13 | State-constrained finite-action minimax, n=4, T=5 | 3125 candidates, 365 feasible; worst-case 9.77, runtime 66 s | See the [B07 source audit](b07-source-audit.md) and [historical manifest](../../benchmarks/scenarios/b07-historical.json); disturbance bounds, stock initialization, time discretization and linear terminal-row discrepancy remain unresolved |
| B08 | L04, PDF pp. 11–13 | Finite-action minimax, n=4, T=4 | 625 plans, worst-case 67.12, runtime 37 s | Independent discrete floating reference computed; nonlinear cost/table inconsistency |
| B09 | L13, PDF pp. 11–14 | Minimax adaptive fuel study, n=4, T=4, q=9 | Adaptive reported cost 22.657 on original model | Full control catalogue/error bounds/plant integration to transcribe; criterion/table inconsistency |

“Readiness” describes next work, not completed reproduction. No claim that all baseline input specifications are already executable.

## B02: nonlinear reachability approximation

Source: L05, Table 1, PDF p. 10 (printed p. 61).

| Example | Algorithm/model | Runtime, s | Vertices | Polytope volume |
|---|---|---:|---:|---:|
| 1, dimension 2, horizon 60 | General algorithm | 0.05 | 120 | 4.62 |
| 1 | Modified algorithm | 0.01 | 16 | 4.34 |
| 1 | Nonlinear system reference | — | 120 | 4.68 |
| 2, dimension 4, horizon 8 | General algorithm | 4.19 | 756 | 40808.17 |
| 2 | Modified algorithm | 0.76 | 153 | 34764.47 |
| 2 | Nonlinear system reference | — | 436 | 47795.76 |

The modified construction is smaller in reported volume. This is not proof of inner containment. Nor is the nonlinear reference a certified complete reachable set merely because its volume is tabulated.

Example 2's nonlinear initial coordinates are written all equal to one, while the extracted linear-system initial vector appears (1,-1,1,1). Check original typography and coordinate convention before coding. Preserve the reference trajectory and any affine/deviation transformation.

## B03: report algorithm benchmarks

L07, Table 3.1, PDF p. 53: at t=15, baseline runtime 5.466993 s and modified runtime 3.583817 s; simplex iterations 158399 and 116497 respectively. The report also compares hull construction for 5000 points from Normal, Uniform and Sphere sampling in dimensions 2–5 (PDF p. 54).

Hardware/report context: MATLAB R2014a, Intel Core i7 at 2.7 GHz (PDF p. 55). This differs from the 3.4 GHz computer quoted in several fuel articles. Identify whether runtime includes vertex generation, conversion, plotting, and repeated solves (historical-replay question only; the algorithm comparison uses the program timing contract in [comparison-program.md](../architecture/comparison-program.md):9,23). Seeds and full numerical arrays are absent.

Owner disposition, 2026-10-20: exact historical sets, execution in the original MATLAB/Python software, and the published runtime/iteration row are **not** goals. B03 is an algorithm comparison: translate the baseline and modified hull algorithms into C++, run them on bit-identical shared fixtures, and compare quality and performance with each other and with the modern algorithms. Historical values remain reported context; no B03 reproduction is claimed. The exact L07 artifact pair behind the baseline and modified rows is not yet named; selecting it is the first port step. See the [missing-inputs dossier](missing-inputs.md).

## B04: nominal terminal fuel control

L11, PDF pp. 12–14:

- Four states: oxidizer flow, oxidizer working-stock balance, fuel flow, fuel working-stock balance.
- T=16 over 100 s; displayed constant A has two blocks [[1,0],[-6.25,1]].
- Displayed B=(17,0,-12,0) transposed.
- Initial state (1216.904,119500,438.787,45300).
- Displayed flow constraints: x1 in [1176,1224], x3 in [432,468].

Criterion:

$$
\phi(x)=\sqrt{(1200-x_1)^2+x_2^2+
\frac{64}{9}(450-x_3)^2+\frac{64}{9}x_4^2+
(x_2-\frac83x_4)^2}.
$$

Reported terminal optimizer: (1200.7,-22.929,450.2,-7.709); reported cost 30.899. Reported solve time 0.4 s. The source discusses multiple realizing controls; do not require identical control histories when terminal objective and feasibility agree. The [recovered local tables](b04-tables.md) provide nonlinear parameters and outcomes for three witnesses; their nonlinear costs differ despite equal reported linear optimality.

The physical meaning of negative working-stock balances must be retained from the source convention and distinguished from total tank mass.

**Selected first, 2026-10-11.** The [restoration audit](b04-restoration.md) and [historical manifest](../../benchmarks/scenarios/b04-historical.json) distinguish supplied data, missing inputs and reported results. An independent exact-rational check shows that the reported terminal point violates a necessary invariant of the displayed model. The unrestricted terminal-plane objective minimum is approximately 160.880654, already above reported 30.899. Terminal-point rounding alone does not explain the gap. The later [saved-witness report](b04-saved-witnesses.md) and [evidence record](evidence/b04-saved-witnesses.json) establish three matching nominal/nonlinear pairs under different x0/B, with nominal norm approximately 30.899136. The frozen norm disagrees with print, replay ends at 99.99 seconds, and canonical T16 constraints/U/generator authority remain unresolved. The separate [b04-reference-v1 case](evidence/b04-reference-v1/canonical-case.json) uses the article's printed model and values with a declared owner-affirmed control interval; its [exact result](b04-reference-cross-check.md) supports algorithm work on that defined case. No full B04 reproduction is claimed or required for that work.

## B05: adaptive optimal control

L08's Table 2 contains the following extracted rows. The [bounded embedded-equation audit](l08-embedded-equations.md) maps the ten policy-label streams to the draft rows and cross-checks their grouping and terminal-coordinate/objective tuples against the [published Part II PDF](https://vestnik.susu.ru/ctcr/article/download/8019/7026). This resolves the table's row-to-policy assignment, not the canonical optimizer source, historical inputs, or run provenance.

| Extracted order | Model grouping | Terminal state | Reported criterion |
|---|---|---|---:|
| 1 | Reference | (1200,0,450,0) | 0 |
| 2 | Nonlinear | (1200.1,39.1,450,10.6) | 48.261 |
| 3 | Nonlinear | (1200.2,32.7,449.9,8.5) | 39.837 |
| 4 | Nonlinear | (1200.1,39.6,450,12.1) | 51.021 |
| 5 | Nonlinear | (1200.1,36.3,450,9.5) | 44.228 |
| 6 | Nonlinear | (1200,38.7,450,9.6) | 46.339 |
| 7 | Nonlinear | (1200.1,31.1,450,8.2) | 37.935 |
| 8 | Nonlinear | (1200.1,39.9,450,10.6) | 48.906 |
| 9 | Nonlinear | (1200,36.6,450,10.1) | 45.372 |
| 10 | Linear | (1200.1,39,450,10.5) | 47.988 |

The draft reports 0.4 s for one open-loop variant and 10 s for the adaptive simulation, on MATLAB R2014a, i7-3770 3.4 GHz, 8 GB RAM. Compare end-to-end replanning separately from one optimization solve.

## B06/B07: five-step minimax experiments

Shared displayed data: x0=(29.31,302,20.354,207), actions {1,0.3,0,-0.3,-1}, T=5. A has two blocks [[1,0],[-10/T,1]], B=(0.7,0,-1/3,0), disturbance matrix columns (0.05,0,0,0) and (0,0,-0.04,0).

B06/L09 includes a synchronization penalty:

$$
\phi_6(x)=\sqrt{(30-x_1)^2+x_2^2+2.25(20-x_3)^2+
2.25x_4^2+(x_2-1.5x_4)^2}.
$$

Reported: 3125 plans; worst-case 10.11; nonlinear state (30,6.0345,20,4.4731) and cost 9.049; runtime 300 s. L09 p. 11 visually prints the unique linear minimax sequence `(-0.3, 1, 0, 0, 0.3)` for control indices 0–4; p. 12 states that this found minimax control is applied to the original nonlinear system for the reported terminal result. The PDF does not print numeric disturbance bounds; the historical uncertainty catalogue and run remain unrecovered. See the [B06 source audit](b06-source-audit.md).

The separate [owner-confirmed disturbance reference](../../benchmarks/scenarios/b06-owner-confirmed-disturbance-v1.json) combines the displayed discrete model with the owner's later `[-1,1]^2` disturbance-set decision. The current finite-action minimax adapter exhaustively evaluates all 3,125 plans and 1,024 disturbance-corner histories per plan. Its independent integer-scaled exact oracle finds the unique minimizer `(-0.3,1,0,0,0.3)` and squared value `1100939049/9000000` (norm `11.060133859949435`). This is a result for the named reference case; the paper does not print the numerical uncertainty set, so it does not reproduce or explain the reported `10.11`. The [saved numerical report and 2D terminal projections](../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/index.html) include seven Release timings and raw inputs/results. A separate [2D example](../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/example-2d.html) and the saved-figure gallery entry show the flow projection and the stock-balance target gap.

B07/L10 uses

$$
\phi_7(x)=\sqrt{(30-x_1)^2+x_2^2+
2.25(20-x_3)^2+2.25x_4^2},
$$

and robust flow limits x1 in [29,31], x3 in [19.5,20.5] at steps 1–5. Reported: 3125 plans, 365 robustly feasible; optimal plan (1,0,0.3,-0.3,0); worst-case 9.77. Nonlinear state (30,5.81,20,4.39), reported cost 8.82; worst-case linear state (29.78,6.43,19.82,4.87), reported cost 9.77; runtime 66 s.

These values are transcribed, not reproduced. L10 does not give numeric vertices or bounds for the disturbance sets used in its robust calculations. Its printed stock-initialization equation and nonlinear parameter table imply stocks (305,205), while the numerical example prints initial stocks (302,207). The [source audit](b07-source-audit.md) records these gaps and the printed `-10/T` stock-flow entries without silently resolving them. The [historical manifest](../../benchmarks/scenarios/b07-historical.json) therefore remains non-executable.

These are different objectives and feasibility domains. Their runtimes are not a clean speedup comparison.

## B08: four-step minimax revision

L04, PDF p. 12: x0=(1182.074,119560,459.832,45260); A blocks [[1,0],[-25,1]], B=(20.073,0,-10.473,0), disturbance columns (1,0,0,0) and (0,0,-1,0). Actions {0.6,0.3,0,-0.3,-0.6}; t=0,1,2,3.

The disturbance box is |w1|<=0.1+0.1t and |w2|<=0.1+0.3t. The stated criterion is Euclidean distance to xd=(1200,0,450,0).

Reported optimal plan (0.6,0.6,-0.3,0), worst-case cost 67.12. Reported nonlinear state (1200.139,-2.294,450.406,-16.254), cost 14.048 (table rounded 14.05). Reported worst-case linear state (1201.14,-27.29,452.61,-61.25), cost 67.12. Historical runtime 37 s on MATLAB R2014a, i7-3770 3.4 GHz, 8 GB RAM; a GT 730 is listed, but GPU execution is not established by its presence.

**Open numerical inconsistency:** the stated Euclidean norm at the displayed nonlinear state is approximately 16.42, not 14.048. Resolve source coordinates, criterion implementation, or transcription; retain the reported value. The [exact displayed-data audit](b08-displayed-exact-audit.md) independently confirms the finite linear reference's three tied plans and its separate cost disagreement under the printed rational inputs.

The [printed terminal-row rounding audit](b08-reported-rounding-audit.md) checks both nonlinear row precisions with exact rational intervals and independently tests the linear Table 2 row against the printed plan's 256 disturbance corners. It keeps the historical values above unchanged.

## B09: minimax adaptive experiment

L13, Table 2, PDF p. 14, DOI 10.18287/2541-7533-2019-18-4-129-145:

| Model | Policy | Terminal state | Reported criterion | Reported exhaustion-time difference |
|---|---|---|---:|---:|
| Reference | Nominal | (60,0,24,0) | 0 | 0 |
| Simplified | Open loop | (60.08,47.7,24.09,-22.2) | 115.79 | 1.71 |
| Simplified | Adaptive | (59.82,20.3,23.91,4.5) | 22.658 | 0.15 |
| Original | Open loop | (60.26,22.6,23.86,5) | 25.295 | 0.17 |
| Original | Adaptive | (60,20.3,24,4.5) | 22.657 | 0.15 |

The initial solve uses nine actions over four steps (6561 plans), with subsequent shrinking horizons. Physical-model values include I=360 s, thrust 30.24 tf, nominal mixture ratio 2.5, nominal initial masses 18000 and 7200 kg, initial mass changes +100 and -50 kg, mixture change -0.075, and a 300 s physical interval.

**Open numerical inconsistency:** equation (16), PDF p. 6, identifies the criterion as Euclidean distance to the desired state. For desired state (60,0,24,0), the displayed original adaptive row has norm approximately 20.7928, not 22.657. The simplified open-loop row has norm approximately 52.613, not 115.79. Rounding does not explain these gaps. A different criterion may have been used in simulation; obtain source code before choosing acceptance thresholds.

## Future comparison protocol

For every executable scenario store the exact source ID/hash, time grid, all model matrices, coordinate convention, units, constraints, uncertainty set and dependence, policy class, objective expression, initial conditions, solver tolerances and reported numbers.

Keep three tracks:

1. Historical transcription: reproduce the published mathematical problem and record differences.
2. Corrected reference: repair demonstrable source/implementation inconsistencies, with a named issue and changed baseline.
3. Improved method: compare with the corrected reference under the same semantics and requested output.

Measure objective and worst-case bound, admissibility violations, model/simulation residuals, set inclusion/support error, solve status, runtime distribution, peak memory, solver iterations, representation size, and hardware/thread count. Record cold start and warm start separately.

Do not compare sampled trajectories with a complete worst-case certificate, approximate sets with exact output without approximation error, continuous controls with discrete actions, or one open-loop solve with an entire adaptive run.

Synthetic scaling extensions should vary dimension, horizon, action count, disturbance generators, constraint count and sparsity independently. They supplement the published cases and must not overwrite their identity.

## Independent partial check completed

[reference-b08.json](reference-b08.json) and [reference_b08.py](tools/reference_b08.py) record an exhaustive floating-point check of the displayed B08 discrete model: all 625 plans and 256 disturbance-box corner images per plan. Computed minimum: 67.150601101407, compared with reported 67.12. The published plan has the same computed objective within numerical tolerance; three plans tie at absolute tolerance 1e-8. This does not resolve uniqueness for any unreported constraints or original unrounded data.

The subsequent [exact rational audit](b08-displayed-exact-audit.md) proves that all three plans have identical squared worst-case value `112730080707/25000000` for the printed decimals, with no tie tolerance. This exact statement is confined to the displayed model; the source names one plan and does not establish uniqueness for an unrecovered generating revision.

The independently evaluated L04 nonlinear displayed-state norm is 16.42069149; the L13 original adaptive displayed-state norm is 20.79278721. These are arithmetic checks of printed coordinates, not nonlinear-plant reproductions. No timing speedup or validated numerical enclosure is claimed.
