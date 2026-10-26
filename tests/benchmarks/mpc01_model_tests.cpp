#include "../../benchmarks/reporting/mpc01/model.hpp"

#include <cstdlib>
#include <iostream>

namespace {

csl::mpc01::MpcCase scalar_case() {
    using namespace csl::mpc01;
    MpcCase result;
    result.id = "ts01-exact";
    result.version = "1";
    result.source_kind = "analytic-contract";
    result.source_ref = "T-S01";
    result.canonical_input_sha256 = std::string(64, 'a');
    result.initial_state = {0.0};
    result.dynamics = {{{{1.0}}, {{1.0}}, {0.0}},
                       {{{1.0}}, {{1.0}}, {0.0}}};
    result.stages = {{{}, Box{{0.0}, {1.0}}},
                     {{}, Box{{0.0}, {1.0}}},
                     {{}, {}}};
    result.terminal_cost = QuadraticTerminalCost{{{2.0}}, {-2.0}, 1.0};
    return result;
}

int fail(const char* message) {
    std::cerr << message << '\n';
    return EXIT_FAILURE;
}

} // namespace

int main() {
    using namespace csl::mpc01;
    auto problem = scalar_case();
    if (validate(problem)) return fail("valid scalar fixture rejected");
    problem.dynamics[1].b[0].push_back(2.0);
    const auto ragged = validate(problem);
    if (!ragged || ragged->path != "dynamics[1].B") {
        return fail("stage-varying control dimension mismatch was not identified");
    }
    problem = scalar_case();
    problem.stages[0].control->lower[0] = 2.0;
    const auto reversed = validate(problem);
    if (!reversed || reversed->path != "stages[0].control") {
        return fail("reversed control interval was not identified");
    }
    problem = scalar_case();
    problem.terminal_cost = AffineResidualNormTerminalCost{{{1.0}, {2.0}}, {0.0, 1.0}};
    if (validate(problem)) return fail("valid affine residual norm fixture rejected");
    return EXIT_SUCCESS;
}
