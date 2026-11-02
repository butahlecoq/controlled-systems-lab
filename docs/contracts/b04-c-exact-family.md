# B04-C exact optimal-family profile

The registered `strategy-a.b04-c-exact-dyadic-v1` profile accepts only the
corrected-track B04-C scenario from issue #531. It interprets finite binary64
initial-state, dynamics, and residual-objective values as their exact represented
dyadic rationals. The stage bounds, control bounds, transition structure, and
the three pre-registered acceptance bands are matched to the frozen profile.
`B04-historical` and `b04-reference-v1` are separate scenarios.

The profile returns the complete minimizing family in
`csl.joint-history.b04-c-exact-rational-v1`. Its 16-dimensional control
polytope contains all 32 control inequalities and all 68 phase inequalities;
four exact terminal equalities select the unique minimizing terminal state.
An exact affine lift maps each member to the canonical 84-coordinate history
`(x0, ..., x16, u0, ..., u15)`. The compiled verifier independently rebuilds
these objects from the prepared request and checks the strict-feasibility KKT
argument, objective enclosure, published-row rounding-box witness, and full
family payload before the registry publishes it.

`synthesis::b04_c::contains_exact_history` checks whether one full history is
in that family. Each coordinate is supplied as
`(numerator / denominator) * 2^binary_exponent`; numerator and denominator are
base-10 integers and the denominator must be nonzero. The query returns
`member`, `not_member`, `unsupported_relation`, `invalid_input`, or
`resource_limit`. It does not project the family or enumerate its members.
Malformed representations and shapes are refused. Parsing and membership use
bounded exact arithmetic (8192-bit integers and at most 2,000,000 arithmetic
operations); exhausting a cap returns `resource_limit`.

This profile is numerical assurance over exact arithmetic applied to the
represented dyadic model. It does not validate that those represented inputs
match any unavailable historical generator. It does not resolve the A40 unit
convention behind the fourfold coefficient scaling and makes no historical
reproduction claim. The profile has no adjustable family materialization limit;
unsupported variants are rejected during admission.

Build consumers link `CSL::strategy_a`. The public query is included in the
installed synthesis headers and is implemented by the compiled verifier
library, which is a transitive dependency of Strategy A. This is a source and
binary API addition; no external dependency or CMake package format changes.
No release is required for this repository change. Any future binary release
must include the updated library and headers together.
