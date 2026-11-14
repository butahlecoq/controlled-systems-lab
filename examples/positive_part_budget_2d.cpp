#include <csl/adapters/convex/highs.hpp>
#include <csl/optimization/nominal_quadratic_history.hpp>
#include <csl/registry/registry.hpp>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <variant>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;

template <class T, class... E> T take(std::variant<T, E...> value) {
    if (auto *result = std::get_if<T>(&value))
        return std::move(*result);
    throw std::runtime_error("Positive-part 2D example operation failed");
}

CompiledNominalQuadraticHistory make_program() {
    const Matrix a{1, 1, {1.0}}, b{1, 2, {0.0, 0.0}}, e{1, 0, {}};
    const Matrix zero_state{1, 1, {0.0}}, zero_cross{1, 2, {0.0, 0.0}};
    const Matrix control_hessian{2, 2, {1.0, 0.0, 0.0, 1.0}};
    const QuadraticHistoryStageCost cost{zero_state, zero_cross,  control_hessian,
                                         {0.0},      {-0.2, 0.2}, 0.04};
    QuadraticTerminal terminal_cost{zero_state, Vector{0.0}, 0.0};
    NominalQuadraticHistoryTask task{
        {{"example.positive-part-budget-2d"}, {"exact-positive-part-epigraph-v1"}},
        {{a, b, e, {0.0}}},
        KnownInitial{{0.0}},
        {},
        {{{-0.2, 0.2}, {-0.2, 0.2}}},
        std::nullopt,
        {cost},
        std::move(terminal_cost),
        {{{{0, 1}, 0.1}}}};
    auto compiled = compile_nominal_quadratic_history(task);
    if (!std::holds_alternative<CompiledNominalQuadraticHistory>(compiled))
        throw std::runtime_error("Positive-part 2D QP did not compile");
    return std::get<CompiledNominalQuadraticHistory>(std::move(compiled));
}
} // namespace

int main(int argc, char **argv) try {
    using namespace csl;
    if (argc != 2)
        throw std::runtime_error("Usage: positive_part_budget_2d NEW_OUTPUT_DIRECTORY");
    const std::filesystem::path output(argv[1]);
    if (!std::filesystem::create_directory(output))
        throw std::runtime_error("Output directory must be new");

    const auto history = make_program();
    const auto &program = history.program;
    auto registration = take<registry::Registration<registry::ConvexPort>>(
        adapters::convex::make_highs_registration());
    auto workspace = registration.factory(program);
    if (!workspace)
        throw std::runtime_error("HiGHS did not create a convex workspace");
    const ExecutionContext context{
        std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {},
        {},
        {1e-9, 1e-9},
        "positive-part-budget-2d"};
    auto outcome = workspace->solve(program, context);
    const auto *result = std::get_if<ProgramResult>(&outcome);
    if (!result || !result->primal || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal ||
        !history.layout.accepts_primal_size(result->primal->size()) ||
        !check_program_result(*result, program, Assurance::numerical).empty())
        throw std::runtime_error("HiGHS did not return a checked positive-part optimum");

    const auto u0 = (*result->primal)[*history.layout.control_index(0, 0)];
    const auto u1 = (*result->primal)[*history.layout.control_index(0, 1)];
    const auto positive_total = std::max(u0, 0.0) + std::max(u1, 0.0);
    const auto literal_objective = 0.5 * ((u0 - 0.2) * (u0 - 0.2) + (u1 + 0.2) * (u1 + 0.2));
    auto checked = evaluate_primal(program, *result->primal, {1e-9, 1e-9},
                                   {{"positive-part-budget-2d-literal-check"}, "1"});
    if (std::abs(u0 - 0.1) > 1e-7 || std::abs(u1 + 0.2) > 1e-7 ||
        std::abs(positive_total - 0.1) > 1e-7 || std::abs(literal_objective - 0.005) > 1e-7 ||
        !std::holds_alternative<ConvexPrimalEvaluation>(checked) ||
        std::abs(std::get<ConvexPrimalEvaluation>(checked).original_objective - literal_objective) >
            1e-9 ||
        std::get<ConvexPrimalEvaluation>(checked).residuals.rows.violation > 1e-9)
        throw std::runtime_error("Native solution disagrees with the literal pentagon optimum");

    std::ofstream coordinates(output / "vertices.csv");
    coordinates << "u0,u1\n-0.2,-0.2\n0.1,-0.2\n0.1,0\n0,0.1\n-0.2,0.1\n";
    std::ofstream solution(output / "native-solution.csv");
    solution << std::setprecision(std::numeric_limits<double>::max_digits10)
             << "coordinate,target,solution,lower,upper\n"
             << "u0,0.2," << u0 << ",-0.2,0.2\n"
             << "u1,-0.2," << u1 << ",-0.2,0.2\n"
             << "positive_part_budget,0.1," << positive_total << ",0,0.1\n";
    std::ofstream summary(output / "run.txt");
    summary << std::setprecision(std::numeric_limits<double>::max_digits10)
            << "solver=csl.convex.highs\n"
            << "objective_convention=0.5*z_transpose_H_z+q_transpose_z+c\n"
            << "control_target=(0.2,-0.2)\nsource_constraint=sum(max(u_i,0))<=0.1\n"
            << "literal_source_objective=0.5*((u0-0.2)^2+(u1+0.2)^2)\n"
            << "native_control=(" << u0 << ',' << u1 << ")\n"
            << "native_positive_part_sum=" << positive_total << "\n"
            << "literal_recomputed_objective=" << literal_objective << "\n"
            << "net_sum_surrogate_admits_target=true\n"
            << "feasible_polygon_vertices=analytically_derived_from_box_and_source_budget\n"
            << "assurance=numerical; no robustness or policy claim\n";
    std::ostringstream captured_output;
    captured_output << std::setprecision(8) << "Positive-part budget QP: u=(" << u0 << ',' << u1
                    << "); sum(max(u,0))=" << positive_total
                    << "; literal objective=" << literal_objective << '\n';
    std::ofstream stdout_record(output / "native-example.stdout");
    stdout_record << captured_output.str();
    coordinates.close();
    solution.close();
    summary.close();
    stdout_record.close();
    if (!coordinates || !solution || !summary || !stdout_record)
        throw std::runtime_error("Could not write positive-part example outputs");
    std::cout << captured_output.str();
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
