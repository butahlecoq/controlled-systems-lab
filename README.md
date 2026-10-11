# Controlled Systems Lab

Public research repository: [butahlecoq/controlled-systems-lab](https://github.com/butahlecoq/controlled-systems-lab). Scientific review starts with [review issues](https://github.com/butahlecoq/controlled-systems-lab/issues) and [contribution conventions](CONTRIBUTING.md).

Initial research assessment, 11 October 2026. Documentation is in English; source artifacts retain their original language.

This archive supports a general library for constrained discrete-time control, reachable-set computation, terminal optimization, and minimax control. Aerospace fuel management is a domain adapter, not the definition of the mathematical core. The accompanying report also covers flight dynamics, slosh, elastic modes, and model discretization.

## Start here

| Document | Purpose |
|---|---|
| [Research index](docs/research/README.md) | Scope, evidence levels, and reading order |
| [Source map](docs/research/source-map.md) | All 31 original files, relationships, and extraction limitations |
| [Scientific foundations](docs/research/scientific-foundations.md) | Equations, assumptions, algorithm descriptions, and guarantee boundaries |
| [Published baselines](docs/research/baselines.md) | Numerical experiments to reproduce and compare |
| [Legacy implementation audit](docs/research/legacy-audit.md) | Source findings and isolated executable checks |
| [Research developments, 2021–2026](docs/research/recent-research.md) | Relevant recent methods and software analogues |
| [Modular algorithms and optimal families](docs/architecture/modular-algorithms-and-solution-sets.md) | Concrete C++20 ports, interchangeable solvers/geometry, complete solution relations |
| [Set representations and Ellipsoidal Toolbox](docs/architecture/set-representations-and-ellipsoidal-toolbox.md) | Ellipsoidal methods, newer representations, recovered owner-authored zonotope paper |
| [Initial architecture](docs/architecture/initial-architecture.md) | Broader modules, contracts, and workflows |
| [Performance and language](docs/architecture/performance-and-language.md) | Parallelism, complexity, and language evaluation |
| [Glossary](docs/research/glossary.md) | Shared mathematical and software vocabulary |
| [Open questions](docs/research/open-questions.md) | Interview agenda and next research steps |
| [Bibliography](docs/research/bibliography.md) | Primary sources and reading depth |

## Current conclusions

The first reusable core should represent affine discrete-time models, time-dependent constraints, uncertainty semantics, terminal objectives, and interchangeable set representations. Algorithms should advertise their supported assumptions and returned guarantees.

The archive's finite-action minimax solver enumerates control sequences; changing language alone will not remove exponential growth. Exact polytope operations, support-function methods, constrained zonotopes, and structured optimization deserve separate backends.

Published experiments are the starting baselines, as requested by the research owner. Their numbers are recorded as reported results, not new reproductions. Several source and implementation inconsistencies must be resolved before they become acceptance criteria.

Updated direction: use a compiled main implementation (C++ or Rust), with C++20 proposed as the working target and Python for initial verification/reference computations. Architecture contracts are defined before numerical benchmark implementation. The first user workflow returns an optimal solution family for nominal planning with continuous actions and without process disturbances; the model contract retains disturbance/adversarial and observation channels. See the [linear-system contract](docs/architecture/linear-system-contract.md). This is an initial architecture hypothesis and research package, not an approved implementation specification.

## Evidence and preservation

Original files were inventoried with SHA-256 hashes and left unchanged. Thirty content-bearing artifacts were extracted; one file is an Office lock file. Raw extraction lives in the local-only docs/research/extracted directory and may contain OCR errors, original Russian text, equation fragments, and personal information already present in the source files.

All 21 PDFs (226 pages in total; see the inventory for authoritative counts) were text-extracted. Selected mathematical and numerical pages were also visually inspected. Embedded Equation Editor objects in the two legacy Word files were not decoded. The full historical MATLAB/Pascal workflows have not been reproduced.

See [machine-readable inventory](docs/research/inventory.json), [characterization results](docs/research/legacy-characterization.json), and [verification record](docs/research/verification.md).
