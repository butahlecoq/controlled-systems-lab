# Owner interview and next research steps

Date: 2026-10-11. Questions are recorded for later discussion; unanswered preferences do not block the initial documentation.

## Confirmed directions

- Build a convenient general interface for controlled systems, with scientific and algorithmic extensibility, performance and parallel scalability.
- First solver control domain: continuous actions. Preserve explicit finite and mixed control domains for future algorithms; hybrid dynamics are a separate future model capability. Continuous-domain convexity is an algorithm assumption, not implied by the word continuous.
- Architecture and replaceable mathematical algorithms are primary. Define contracts before benchmark implementation. The first output represents all optimal plans and consistent trajectories; feasible and near-optimal families are not initial public requests.
- Reserve linear cross-step constraints in the problem contract, but omit new temporal couplings from the first archival experiments. Future variants require a compatible strategy and separate scenario identity. A specific exact slew-constraint lift and its limits are documented in temporal-coupling.md.
- Verification architecture includes numerical and validated/certificate-based levels. Implement numerical verification first, with explicit tolerances, independent trajectory checks and supported optimality evidence; algorithm assumptions are documented from the start.
- First optimal-family operation: obtain different consistent complete control sequences and their trajectories, for visual, numerical and runtime comparison of methods. Membership/projections and user-facing secondary optimization remain later query priorities.
- First method comparison: historical reachability/backward recovery versus direct joint-trajectory optimization, both returning supported optimal families. Reachable-set approximation comparison is deferred.
- First objective modules: explicit linear, convex quadratic and weighted Euclidean terminal forms. General user functions remain a future extension. Preserve each archival objective/weight convention and evaluate original objective values after any solver reformulation.
- Use the supplied application experiments and published numerical outcomes as initial baselines.
- First user workflow selected: optimal control planning. Given a model and constraints, obtain a control sequence, its corresponding trajectory, and an objective/quality evaluation. The first solve will be nominal, without process disturbances. The model contract must nevertheless account for external/adversarial inputs and partial/noisy observation. B04 is selected as the first end-to-end reproduction baseline; its canonical inputs need restoration and its displayed model/result inconsistency must be resolved.
- Keep all newly authored research/software artifacts in English; converse with the owner in Russian.
- The owner selected C++ as the main implementation language, with C++20 as the working standard. Python is acceptable for independent verification and references. See the [language decision](../architecture/decisions/0001-cpp20-core.md).
- Module unit tests are required, with adapter contract, mathematical and integration tests. Consolidate conversation decisions into a specification, then derive tickets and implement dependency-ready work with subagents. See the [consolidated specification](../superpowers/specs/2026-10-11-controlled-systems-master-design.md).
- The professor's earliest implementation was Pascal; archived MATLAB/Python artifacts are historical evidence.
- Create a public GitHub repository for active tracking and scientific review. Approved name: controlled-systems-lab. Owner will add reviewers.

The immediate workflow compares alternative algorithms through complete witness trajectories, numerical quality and computation time. Target workload scale and any deadline-bound online controller remain undecided.

## Next focused interview

| Priority | Question | Why it matters |
|---|---|---|
| 1 | Can the original B04 MATLAB project or full numerical inputs be recovered? | B04 is selected; printed matrices violate the reported terminal-point invariant and numerical control bounds are missing |
| 2 | Which later experiments should follow nominal B04: minimax B07/B08 or adaptive B09? | The selected initial solve is nominal; later workflows have different uncertainty/information assumptions |
| 1 | Can a B04-matching project/run, full historical control histories and OpenLoopControl.py be recovered? | The larger archive recovered MATLAB/Pascal variants and a distinct minimax adaptive MATLAB source; canonical publication/run matching remains open |
| 1 | Which actual terminal criterion was used for L04/L13 numerical tables? | Printed Euclidean formulas and displayed state/cost rows disagree |
| 2 | Which other application domains should the interface serve first? | Validates generality beyond fuel-management assumptions |
| 2 | What typical/maximal dimensions, horizons, action counts and set complexities are expected? | Distinguishes numerical vs combinatorial bottlenecks |
| 2 | Is the priority scientific experiments, offline synthesis, or online control with a deadline? | Determines scheduling, deployment and timing contracts |
| 2 | Which future claims require validated certificates: set inclusion, global minimax, family completeness, or statistical coverage? | Both verification levels are in the architecture; concrete certificate support remains claim-specific |
| 2 | Which future temporal constraints should be supported beyond the proved one-step slew lift? | General joint linear constraints preserve convexity under stated assumptions but may require different algorithms or growing memory |
| 2 | Are disturbances bounded independently each step, correlated, fixed unknown parameters, or statistical? | Determines reachable-set and minimax semantics |
| 2 | Is full state observed? Are observation/model uncertainties estimated online? | Defines information pattern and estimator responsibilities |
| 3 | What CPUs/GPUs, operating systems and deployment targets should be supported? | Guides backend/packaging choices |
| 3 | Should the first convenient interface be a library, CLI/notebook, desktop tool, or web UI? | Separates computational core from presentation |
| 3 | Which archival materials may be redistributed publicly, and under what license? | Defines public source release independently of new documentation |

Ask one focused group at a time; update the glossary and architecture when answers change the domain model.

## Proposed staged investigation

**Architecture first:** discuss the [modular C++20 contracts](../architecture/modular-algorithms-and-solution-sets.md), dependency-preserving optimal families, interchangeable solvers/operators and approximation evidence. Language and ownership are part of this design now.

**Source restoration:** complete baseline manifests, recover missing equations/control labels, visually resolve ambiguous signs, and identify canonical versions. Keep original reported and recomputed values side by side.

**Independent references:** verify the mass recurrence, exact small disturbance extrema, robust feasibility, nominal terminal optimum and consistent recovered trajectories. Characterization already found listing defects; full reproductions remain future work.

**Method comparison:** exact low-dimensional polytope reference, lazy support/CZ alternatives, direct sparse optimization and a supported feedback method. Read the relevant proofs before importing guarantee claims.

**Performance evaluation:** representative original cases followed by independently varied scale factors; profile kernels/conversions/search; then measure native backends, CPU parallelism and optional GPU/distributed work.

**Interface implementation:** after agreeing the architecture, implement the selected nominal optimal-family workflow with replaceable algorithm ports. Numerical results validate it; interface design is not deferred until after benchmarking.

## Initial review topics

Track source/criterion inconsistencies, missing minimax adaptive implementation, worst-case oracle semantics, nonlinear residual validity, robust predecessor quantifiers, approximation inclusion, reproducibility, and language/performance requirements as separate issues. Reviewers should cite source IDs, exact formulas/pages, assumptions and minimal counterexamples.

The current study leaves these issues visible rather than silently selecting one draft or turning every reported numerical number into an acceptance test.
