#include <csl/optimization/nominal_quadratic_history.hpp>

#include <iostream>
#include <variant>

int main() {
    using namespace csl;
    using namespace csl::optimization;
    const Matrix a{2, 2, {0, 0, 0, 0}}, b{2, 1, {1, 1}}, e{2, 0, {}};
    const Matrix zero_state{2, 2, {0, 0, 0, 0}}, zero_cross{2, 1, {0, 0}}, zero_control{1, 1, {0}};
    QuadraticHistoryStageCost empty{zero_state, zero_cross, zero_control, {0, 0}, {0}, 0};
    QuadraticHistoryStageCost interior{
        {2, 2, {2, 0, 0, 2}}, zero_cross, zero_control, {-2, 0}, {0}, 1};
    NominalQuadraticHistoryTask task{{{"installed-history-qp"}, {"two-transition"}},
                                     {{a, b, e, {0, 0}}, {a, b, e, {0, 0}}},
                                     KnownInitial{{0, 0}},
                                     {},
                                     {},
                                     std::nullopt,
                                     {empty, interior},
                                     {zero_state, {0, 0}, 0}};
    auto compiled = compile_nominal_quadratic_history(task);
    const auto *program = std::get_if<ConvexProgram>(&compiled);
    if (!program || program->quadratic_program().hessian().rows() != 8)
        return 1;
    if (program->quadratic_program().hessian()(2, 2) != 2.0 ||
        program->quadratic_program().hessian()(3, 3) != 2.0 ||
        program->quadratic_program().hessian()(4, 4) != 0.0)
        return 1;
    std::cout << "Installed nominal history QP: interior-state and terminal blocks passed\n";
}
