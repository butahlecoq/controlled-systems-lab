# Owner interview and next research steps

Date: 2026-10-11. Questions are recorded for later discussion; unanswered preferences do not block the initial documentation.

## Confirmed directions

- Build a convenient general interface for controlled systems, with scientific and algorithmic extensibility, performance and parallel scalability.
- Architecture and replaceable mathematical algorithms are primary. Define contracts before benchmark implementation. The first output represents all optimal plans and consistent trajectories; feasible and near-optimal families are not initial public requests.
- Use the supplied application experiments and published numerical outcomes as initial baselines.
- First user workflow selected: optimal control planning. Given a model and constraints, obtain a control sequence, its corresponding trajectory, and an objective/quality evaluation. The first solve will be nominal, without process disturbances. The model contract must nevertheless account for external/adversarial inputs and partial/noisy observation. The first reproduction baseline remains undecided.
- Keep all newly authored research/software artifacts in English; converse with the owner in Russian.
- Prefer a compiled main implementation in C++ or Rust. Python is acceptable for initial verification and references. C++ is the assistant-proposed working target; the owner has not stated a preference between C++ and Rust.
- The professor's earliest implementation was Pascal; archived MATLAB/Python artifacts are historical evidence.
- Create a public GitHub repository for active tracking and scientific review. Approved name: controlled-systems-lab. Owner will add reviewers.

The owner's baseline answer did not choose between one large solve, many experiments, or a deadline-bound feedback controller. Treat that requirement as undecided.

## Next focused interview

| Priority | Question | Why it matters |
|---|---|---|
| 1 | Which optimal-family operations should be available first: witness selection, membership, projections or secondary optimization? | All optimal plans are confirmed; this prioritizes queries without weakening the result contract |
| 1 | Which supplied experiment should be our first complete reproduction: nominal B04, constrained minimax B07, four-step minimax B08, or adaptive B09? | Defines one concrete end-to-end result and missing inputs |
| 1 | Can original MATLAB/Pascal projects, full control histories, OpenLoopControl.py, and the distinct minimax adaptive source be recovered? | Resolves reproduction and duplicate-folder gaps |
| 1 | Which actual terminal criterion was used for L04/L13 numerical tables? | Printed Euclidean formulas and displayed state/cost rows disagree |
| 2 | Which other application domains should the interface serve first? | Validates generality beyond fuel-management assumptions |
| 2 | What typical/maximal dimensions, horizons, action counts and set complexities are expected? | Distinguishes numerical vs combinatorial bottlenecks |
| 2 | Is the priority scientific experiments, offline synthesis, or online control with a deadline? | Determines scheduling, deployment and timing contracts |
| 2 | Which guarantees are required: numerical feasibility, validated enclosure, global minimax, or probabilistic coverage? | Determines algorithms and evidence costs |
| 2 | Are controls continuous, finite, mixed, or selectable by application? | Prevents invalid convexification |
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

**Performance evaluation:** representative original cases followed by independently varied scale factors; profile kernels/conversions/search; then measure language stacks, CPU parallelism and optional GPU/distributed work.

**Interface implementation:** after agreeing the architecture, implement the selected nominal optimal-family workflow with replaceable algorithm ports. Numerical results validate it; interface design is not deferred until after benchmarking.

## Initial review topics

Track source/criterion inconsistencies, missing minimax adaptive implementation, worst-case oracle semantics, nonlinear residual validity, robust predecessor quantifiers, approximation inclusion, reproducibility, and language/performance requirements as separate issues. Reviewers should cite source IDs, exact formulas/pages, assumptions and minimal counterexamples.

The current study leaves these issues visible rather than silently selecting one draft or turning every reported numerical number into an acceptance test.
