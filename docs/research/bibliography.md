# Primary-source bibliography

Checked 2026-10-11. Reading depth distinguishes metadata/abstract review from proof review. No entry below implies independent reproduction. Live software documentation describes the observed interface, not a pinned dependency version.

## Research papers

| ID | Primary source | Date / status | Reading depth |
|---|---|---|---|
| R01 | Vinod, Weiss, Di Cairano. [Projection-free computation of robust controllable sets with constrained zonotopes](https://www.merl.com/publications/TR2025-023). [Author PDF](https://merl.com/publications/docs/TR2025-023.pdf). DOI 10.1016/j.automatica.2025.112211 | Automatica 175, 112211, 2025; preprint 2024 | Abstract and paper formulation/algorithm portions; no full proof audit |
| R02 | Chen, Preciado, Morari, Matni. [Robust Model Predictive Control with Polytopic Model Uncertainty through System Level Synthesis](https://arxiv.org/abs/2203.11375v3) | 2022, revised 2023; accessed preprint | Abstract/formulation overview |
| R03 | Sieber, Bennani, Zeilinger. [A System Level Approach to Tube-Based Model Predictive Control](https://www.research-collection.ethz.ch/entities/publication/a3609de6-a49a-4e5c-b1f5-07f84896b347). DOI 10.1109/LCSYS.2021.3086190 | IEEE Control Systems Letters 6, 776–781, 2022; early online 2021 | Institutional record/abstract |
| R04 | Alanwar, Koch, Allgöwer, Johansson. [Data-Driven Reachability Analysis from Noisy Data](https://arxiv.org/abs/2105.07229v3). DOI 10.1109/TAC.2023.3257167 | IEEE TAC 2023; first preprint May 2021 | Abstract and scope |
| R05 | Berberich, Allgöwer. [An overview of systems-theoretic guarantees in data-driven model predictive control](https://arxiv.org/abs/2406.04130v2). DOI 10.1146/annurev-control-030323-024328 | Annual Review of Control, Robotics, and Autonomous Systems 8(1), 77–100, 2025; first preprint 2024 | Abstract and bibliographic status |
| R06 | Martin, Schön, Allgöwer. [Guarantees for data-driven control of nonlinear systems using semidefinite programming: A survey](https://arxiv.org/abs/2306.16042v2) | 2023 author preprint; journal DOI 10.1016/j.arcontrol.2023.100911 | Abstract and method categories |
| R07 | Zhang, Lin, Grammatico. [Parallel Branch Model Predictive Control on GPUs](https://arxiv.org/abs/2506.13624v2) | First submitted 2025; v2 August 2026; preprint | Abstract and parallel structure; no proof audit |
| R08 | Chen, Tse, Nobel, Goulart, Boyd. [CuClarabel: GPU Acceleration for a Conic Optimization Solver](https://arxiv.org/abs/2412.19027v3). [Author PDF](https://stanford.edu/~boyd/papers/pdf/cuclarabel.pdf) | First submitted December 2024; v3 November 2025; preprint status used here | Abstract and computational approach |
| R09 | Naderi, Hegazy, Alanwar. [Online Data-Driven Reachability Analysis using Zonotopic Recursive Least Squares](https://arxiv.org/abs/2509.17058v2) | September 2025; v2 August 2026; preprint | Abstract only |
| R10 | Xie, Zhang, Findeisen, Alanwar. [Bridging Data-Driven Reachability Analysis and Statistical Estimation via Constrained Matrix Convex Generators](https://arxiv.org/abs/2604.04822v1) | April 2026; preprint | Abstract only |
| R11 | Naderi, Hafez, Fawzy, Alanwar. [Data-Driven Reachability of Nonlinear Lipschitz Systems via Koopman Operator Embeddings](https://arxiv.org/abs/2604.00150v2) | March 2026; v2 August 2026; preprint | Abstract only |
| R12 | Althoff, Forets, Perschl, Schilling. [ARCH-COMP25 category report: continuous and hybrid systems with linear dynamics](https://portal.fis.tum.de/en/publications/arch-comp25-category-report-continuous-and-hybrid-systems-with-li/). DOI 10.29007/z3g7 | EPiC Series in Computing 108, 15–38, 2025 | Institutional report record/abstract |
| R24 | Frey, Gao, Messerer, Lahr, Zeilinger, Diehl. [Efficient Zero-Order Robust Optimization for Real-Time Model Predictive Control with acados](https://publications.syscop.de/Frey2024.pdf) | ECC 2024 | Paper formulation, algorithm and convergence qualifications |
| R25 | [Advanced-Step Real-Time Iterations With Four Levels – New Error Bounds and Fast Implementation in acados](https://publications.syscop.de/Frey2024a.pdf) | 2024 | Identified from official acados reference; paper accessed, detailed assessment pending |
| R26 | [Differentiable Nonlinear Model Predictive Control](https://arxiv.org/pdf/2505.01353) | 2025 preprint identifier | Identified from official acados reference; detailed assessment pending |

R04's first preprint lies outside the strict rolling window, but the journal result and revisions are inside. R03 has a similar distinction between early dissemination and journal year. These are not presented as entirely new ideas first invented after October 2021.

## Software and documentation

| ID | Primary source | Role |
|---|---|---|
| R13 | [MERL pycvxset](https://www.merl.com/research/downloads/pycvxset); [official repository](https://github.com/merlresearch/pycvxset). Vinod, ACC 2025, 2515–2521, DOI 10.23919/ACC63710.2025.11107986 | Convex set operations, constrained zonotopes, CVXPY and pycddlib integration; institutional page/repository inspected |
| R14 | [LazySets documentation](https://juliareach.github.io/LazySets.jl/stable/); [ReachabilityAnalysis repository](https://github.com/JuliaReach/ReachabilityAnalysis.jl) | Julia set/reachability ecosystem; docs/repository overview |
| R15 | [CORA project](https://tumcps.github.io/CORA/); [2024 manual](https://tumcps.github.io/CORA/data/archive/manual/Cora2024Manual.pdf) | MATLAB verification and set computation; overview/manual portions |
| R16 | [do-mpc documentation](https://www.do-mpc.com/en/latest/); [robust MPC theory](https://www.do-mpc.com/en/develop/theory_mpc.html) | MPC/MHE/simulation and multistage uncertainty tree; docs inspected |
| R17 | [acados features](https://docs.acados.org/features/); [installation and parallel configuration](https://docs.acados.org/installation/index.html) | Structured OCP solvers, code generation, RTI, MHE, batching and OpenMP; docs inspected |
| R18 | [CVXPY 1.7 changes](https://www.cvxpy.org/version/1.7/updates/index.html) | New GPU solver interfaces; release notes |
| R19 | [HiGHS](https://highs.dev/) | Native LP/QP/MIP backend candidate; official overview |
| R20 | [OSQP](https://osqp.org/) | Sparse convex QP backend candidate; official overview |
| R21 | [cddlib manual](https://www.cs.mcgill.ca/~fukuda/soft/cddlibman/cddlibman.html) | H/V conversion and polyhedral computation; manual overview |
| R22 | [Julia performance guidance](https://docs.julialang.org/en/v1/manual/performance-tips/) | Type stability, allocation and compilation considerations; documentation |

CORA, JuliaReach, do-mpc, acados, HiGHS, OSQP and cddlib have histories predating the window. Their current capabilities inform architecture, but package existence is not evidence of a 2021–2026 scientific advance.

## Original-work counterparts and follow-up leads

R23: [Published adaptive optimal fuel-control Part II](https://vestnik.susu.ru/ctcr/article/download/8019/7026), DOI 10.14529/ctcr190203, 2019. Companion [Part I record](https://vestnik.susu.ru/ctcr/article/view/8018). These help restore L08's embedded equations.

The [author's institutional research profile](https://sciact.uiec.ru/public/profile/77) lists subsequent registered programs, including PROGNOZ-2022 (RU2022667943), and provides a lead for continued research. [A 2026 institutional record](https://sciact.uiec.ru/public/article/5501) lists “Optimization of Adaptive Control of Forecasting of the Phase Vector State of a Quasilinear Discrete-Time Controlled Dynamical System,” DOI 10.1007/s10598-026-09686-8. Treat this as a metadata lead, not an assessed algorithm or demonstrated improvement.

A related 2016 reachable-set/fuel-control work using zonotopes appears in bibliographic search leads but was not supplied. Request its original before concluding that zonotope methods are new to this research lineage.

## Next reading depth

Before implementing R01/R02/R24, audit each relevant theorem, supported set/policy assumptions, numerical method and benchmark inputs. Before adopting R09–R11, read the full latest versions and verify model-containment, noise, excitation, drift and residual assumptions. Archive implementation commit identifiers and licenses when an adapter is selected.

## Additional interface and language references

R27: [MATLAB state-space models](https://www.mathworks.com/help/control/ug/state-space-models.html) and [ControlSystems.jl system construction](https://juliacontrol.github.io/ControlSystems.jl/stable/man/creating_systems/), checked 2026-10-11. Official notation and input/output construction reference; no new scientific advance claimed.

R28: [Clarabel official documentation](https://clarabel.org/stable/), checked 2026-10-11. Native Rust/Julia implementations and language-interface information; backend candidate, not an adopted dependency.

## Set representations and ellipsoidal follow-up

Follow-up assessed 2026-10-11. See [architecture implications and reading limits](../architecture/set-representations-and-ellipsoidal-toolbox.md). These sources are separate from the unchanged local inventory L01–L31.

| ID | Primary source | Date / reading depth |
|---|---|---|
| R29 | [Shorikov and Kalev, reachable-set computation using zonotopes](https://ceur-ws.org/Vol-1825/p13.pdf); [publisher record](https://ceur-ws.org/Vol-1825/) | Conference 2016; proceedings 10 April 2017, pp. 103–110; extracted paper/model/algorithm read, proof audit pending |
| R30 | [Ellipsoidal Toolbox repository](https://github.com/SystemAnalysisDpt-CMC-MSU/ellipsoids); [calculus manual](https://systemanalysisdpt-cmc-msu.github.io/ellipsoids/doc/chap_ellcalc.html); [reachability manual](https://systemanalysisdpt-cmc-msu.github.io/ellipsoids/doc/chap_reach.html) | Foundational software; documentation inspected, no executable verification |
| R31 | [Liu, Manzie and Dower, HJB ellipsoidal approximations](https://arxiv.org/abs/2401.06352) | Submitted 2024, revised 2025; abstract/metadata, linked journal DOI 10.1109/TAC.2024.3512619 |
| R32 | [Kousik, Dai and Gao, ellipsotopes](https://arxiv.org/abs/2108.01750) | First submitted August 2021 outside strict window; revisions October 2021/2022; abstract/history |
| R33 | [Bird et al., hybrid zonotopes](https://arxiv.org/abs/2106.14831) | First submitted June 2021 outside strict window; revisions 2022/2023; abstract/history |
| R34 | [Siefert et al., hybrid-zonotope functional decomposition](https://arxiv.org/abs/2304.06827) | Submitted April 2023; abstract/metadata |
| R35 | [Kochdumper and Althoff, constrained polynomial zonotopes](https://link.springer.com/article/10.1007/s00236-023-00437-5) | Published May 2023; abstract, introduction and definition overview; full proof audit pending |
| R36 | [Kochdumper and Althoff, sparse polynomial zonotopes](https://arxiv.org/abs/1901.01780) | Submitted 2019/revised 2020, before window; abstract/metadata |
| R37 | [Ellipsoidal Toolbox Python port, publisher release record](https://pypi.org/project/ellipsoidal-toolbox/) | Release 1.0.0, March 2026; project description/release metadata only; untested |

## Temporal-constraint foundations

| ID | Primary source | Reading depth / role |
|---|---|---|
| R38 | [Boyd and Vandenberghe, Convex Optimization](https://web.stanford.edu/~boyd/cvxbook/) | Foundational text, 2004; convexity/polyhedral formulation background. Applied derivations are recorded independently in [temporal coupling](temporal-coupling.md) |
| R39 | [do-mpc LQR increment-state reformulation and source](https://www.do-mpc.com/en/latest/_modules/do_mpc/controller/_lqr.html) | Documented augmentation and source inspected; input-rate penalty example, not a certificate for hard constraints or complete-family recovery |

## B04 publication recovery

R40: [Kalev and Shorikov, optimal open-loop terminal fuel control](https://sciencejournals.ru/view-article/?a=TeorSist1902009Kalev&j=teorsist&n=1&v=0&y=2019), 2019, pp. 166–176, DOI 10.1134/S0002338819020094. Published counterpart to L11; numerical section and tables inspected 2026-10-11.
