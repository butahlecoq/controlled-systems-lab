#include <csl/synthesis/hybrid_path_program.hpp>

#include <iostream>
#include <stdexcept>
#include <variant>

int main() {
    using namespace csl;
    using namespace csl::model;
    using namespace csl::synthesis;

    auto inequalities = numeric::snapshot(Matrix{0, 4, {}});
    auto bounds = numeric::snapshot_vector(Vector{});
    auto equalities = numeric::snapshot(Matrix{2, 4, {-1, 0, 1, 0, 0, -1, 0, 1}});
    auto rhs = numeric::snapshot_vector(Vector{0, 0});
    if (!std::holds_alternative<numeric::MatrixView>(inequalities) ||
        !std::holds_alternative<numeric::VectorView>(bounds) ||
        !std::holds_alternative<numeric::MatrixView>(equalities) ||
        !std::holds_alternative<numeric::VectorView>(rhs))
        throw std::runtime_error("Could not store the exact 2D reset relation");
    auto reset = sets::make_h({{"installed-identity-reset"}, 4, {}},
        {std::get<numeric::MatrixView>(inequalities), std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities), std::get<numeric::VectorView>(rhs)});
    if (!std::holds_alternative<sets::SetData>(reset))
        throw std::runtime_error("Could not construct the exact 2D reset relation");

    HybridMode source{{"source"}, 2, 1, {"x", "y"}, {"u"}};
    source.flow = LinearStage{Matrix{2, 2, {1, 0, 0, 1}}, Matrix{2, 1, {1, 0}},
        Matrix{2, 0, {}}, Vector{0, 0}};
    source.control_sets = {Singleton{{1}}};
    source.invariants = {UniversalSet{2}, UniversalSet{2}};
    HybridMode target{{"target"}, 2, 0, {"x", "y"}, {}};
    target.flow = LinearStage{Matrix{2, 2, {1, 0, 0, 1}}, Matrix{2, 0, {}},
        Matrix{2, 0, {}}, Vector{0, 0}};
    target.control_sets = {UniversalSet{0}};
    target.invariants = {UniversalSet{2}, UniversalSet{2}};
    const HybridSystem system{1, {source, target},
        {{{"switch"}, {"source"}, {"target"}, {UniversalSet{2}},
          {std::get<sets::SetData>(reset).as_handle()}}}};
    const HybridRequest request{{{"source"}, {-1, 0}}, {{"target"}},
        {{{"target"}, LinearTerminal{{1, 0}, 0}, "x", "m"}}};
    const HybridPath path{{{"source"}, {"target"}}, {{"switch"}}};
    const auto result = build_hybrid_path_program(system, request, path,
        {"installed-hybrid-2d"}, {32, 128, 4096});
    const auto* program = std::get_if<HybridPathProgram>(&result);
    if (program == nullptr || program->path != path)
        throw std::runtime_error("Installed hybrid path program did not preserve the requested 2D branch");

    const auto relation = program->joint_relation.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&relation);
    const Vector literal_joint_state{-1, 0, 1, 0, 0, 0, 0};
    if (h == nullptr || h->inequalities.rows() != 0 || h->equalities.rows() != literal_joint_state.size())
        throw std::runtime_error("Installed hybrid path program returned a different exact 2D relation shape");
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double value = 0;
        for (std::size_t column = 0; column < h->equalities.cols(); ++column)
            value += h->equalities(row, column) * literal_joint_state[column];
        if (value != h->equality_values[row])
            throw std::runtime_error("Installed hybrid path program rejected the literal 2D trajectory");
    }

    std::cout << "Installed hybrid path program client: exact 2D branch program passed\n";
    return 0;
}
