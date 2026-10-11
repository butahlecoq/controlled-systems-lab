# Scenario files: authoring and selection design sketch

Date: 2026-10-11. Status: discussion draft. File-based input and supplied simple templates are owner decisions; syntax, field names, defaults and launcher details below are proposals, not an implemented parser/schema.

Requirements and acceptance tests are in the [consolidated specification](2026-10-11-controlled-systems-master-design.md), INP-01 through INP-05 and T-I01 through T-I03. Native input translation uses the [C++ contracts](2026-10-11-cpp-core-contracts-design.md).

## Intended experience

The user selects an existing scenario, or copies a template, edits mathematical data, validates the file and runs the comparison. Custom supported cases require no C++ changes. The project supplies templates and concise explanations; future users are responsible for their own model and problem data.

The first workflow returns final optimal-family results, selected controls and trajectories, objective/verification evidence and summary runtime/memory. Intermediate computation viewers are deferred.

## Proposed minimal form

The following YAML-shaped example illustrates desired readability. YAML is a candidate, not a selected dependency or accepted schema. The version and field names are illustrative. This is a discrete two-step integrator, not the archival B04 problem.

~~~yaml
version: 1
id: two-step-integrator
horizon: 2

model:
  type: linear_discrete_lti
  A: [[1]]
  B: [[1]]

initial_state: [0]

controls:
  type: box
  lower: [0]
  upper: [1]

objective:
  type: terminal_distance
  target: [1]
~~~

The proposed terminal_distance shorthand means Euclidean distance to the terminal state target: ||x_T-target||_2. It resolves to the existing residual-norm objective with L=I and r=target; advanced forms can specify weights or a rectangular residual map explicitly. Here the criterion is |x_2-1|. Its minimum is zero and the optimal controls satisfy u_0+u_1=1 inside [0,1]^2. Complete trajectories follow from the dynamics. This oracle can check the template loader and both strategies independently of historical restoration.

The proposed default nominal profile means no external inputs, known initial state, open-loop planning and no observation requirements. Omitted state restrictions mean universal admissibility under that documented profile. A linear model has zero offset; an affine form provides the offset explicitly. No control bounds or target are invented. These profile/default meanings must be recorded in the resolved run rather than inferred differently by each solver.

Dimensions can be inferred from matrix/vector shapes and then cross-checked. A square A, matching B rows, initial-state length, control-bound lengths and residual-map/target dimensions are still mandatory validation. Coefficients are constant here; the LTV template uses an explicit stage-indexed form. State restrictions distinguish T+1 state stages from T control stages.

## Progressive detail without changing the task

- Basic files contain the problem data and use a documented default comparison profile selecting the two agreed strategies.
- Optional run settings select strategies/backends, witness count/rule, numerical tolerances, seeds and resources. The problem identity remains independent of those choices.
- Small matrices appear inline. A later supported external-data form declares reference location, shape/layout and hashes; changing external content changes problem identity.
- Common boxes and simple terminal targets have concise forms. General polyhedral constraints and richer channels use explicit advanced forms.
- Optional features appear when needed; users do not fill empty disturbance, observation, temporal-constraint or hybrid sections for a nominal case.

One authored file may contain both problem and optional run settings. This conceptual separation does not require multiple files, inheritance chains or user-managed configuration merges. Automatic strategy substitution or mathematical relaxation requires a separate explicit policy; the parser does not silently change the requested problem.

## Templates, validation and compatibility

Supply a small documented catalog: a minimal LTI case, a state-constrained case, an LTV case and examples of each initial objective convention. Every executable template must have complete inputs and an independently checked expected behavior. Historical provenance, expected results and restoration metadata can live beside the user form; unresolved B04 stays explicitly non-executable.

Input validation should report a field path, the observed issue and the expected form. For example: model.B has two rows but model.A defines three state coordinates. Unknown fields must not be silently ignored; a misspelled constraint can otherwise change the mathematical problem. Unsupported model/domain/verification capabilities are distinguished from malformed input and from proven infeasibility.

Version the schema and document defaults. Save a resolved problem/run record so users and reviewers can understand omissions and reproduce an experiment. Do not equate the existing B04 archival JSON record with the eventual executable user schema. A scenario catalogue should distinguish ready-to-run cases from historical restoration records.

Concrete syntax, launch commands, matrix-data references and whether the first launcher is a CLI remain review topics. Adding continuous-time input with discretization would require an explicit time grid and integration/hold semantics; it must not be inferred from a discrete matrix entry.
