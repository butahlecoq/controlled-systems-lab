#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/optimization/finite_action_graph.hpp>

#include <variant>

using namespace csl;

namespace {
sets::SetData make_box(const Vector& lower, const Vector& upper, const char* id) {
    const auto dimension = lower.size();
    Matrix a{2 * dimension, dimension, Vector(2 * dimension * dimension, 0.0)};
    Vector b;
    for(std::size_t i = 0; i < dimension; ++i) {
        a.values[2 * i * dimension + i] = 1.0; b.push_back(upper[i]);
        a.values[(2 * i + 1) * dimension + i] = -1.0; b.push_back(-lower[i]);
    }
    const auto av = numeric::snapshot(a); const auto bv = numeric::snapshot_vector(b);
    const auto ev = numeric::snapshot(Matrix{0,dimension,{}}); const auto fv = numeric::snapshot_vector(Vector{});
    if(!std::holds_alternative<numeric::MatrixView>(av) || !std::holds_alternative<numeric::VectorView>(bv) ||
       !std::holds_alternative<numeric::MatrixView>(ev) || !std::holds_alternative<numeric::VectorView>(fv))
        throw std::runtime_error("H box snapshot failed");
    const auto set = sets::make_h({{id}, dimension, {"x","y"}},
        {std::get<numeric::MatrixView>(av), std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(ev), std::get<numeric::VectorView>(fv)});
    if(!std::holds_alternative<sets::SetData>(set)) throw std::runtime_error("H box construction failed");
    return std::get<sets::SetData>(set);
}
}

int main() {
    const SystemModel authored{{{2,1,0}, TimeDomain::discrete,
        std::vector<LinearStage>{
            {{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}},
            {{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}}, {}};
    const auto system = model::snapshot(authored, Vector{0,1,2});
    if(!std::holds_alternative<model::LinearSystem>(system)) return 1;
    const auto objective = optimization::snapshot(QuadraticTerminal{
        Matrix{2,2,{2,0,0,2}}, {0,0}, 0});
    if(!std::holds_alternative<optimization::Objective>(objective)) return 2;
    optimization::FiniteActionNominalRequest request{{"installed-graph"}, {"installed-graph-query"},
        std::get<model::LinearSystem>(system), {0,0}, {1,{{0},{1}}}, {{},{}},
        {make_box({0,0},{0,0},"root"), make_box({1,0},{1,0},"middle"), make_box({0,0},{2,0},"terminal")},
        std::get<optimization::Objective>(objective),
        {"installed-running/1",2,{{0,{{optimization::QuadraticControlPenalty{{0},{1},{1},1,2}}}},
                                  {1,{{optimization::QuadraticControlPenalty{{0},{1},{1},1,2}}}}}}, 0};
    auto registration = geometry::polyhedral::make_projection_registration();
    registry::Registry<registry::GeometryPort> registry;
    if(registry.add(registration)) return 3;
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    auto provider = registry::prepare_provider(registry::select_provider(registry,
        {registration.identity.id, registration.identity.version}, requirements));
    if(!std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(provider)) return 4;
    const auto graph = optimization::finite_action_stage_layered_graph(request, {4,32},
        std::get<registry::PreparedProvider<registry::GeometryPort>>(provider));
    if(!std::holds_alternative<optimization::FiniteActionGraphResult>(graph)) return 5;
    const auto& result = std::get<optimization::FiniteActionGraphResult>(graph);
    if(!result.has_viable_path || result.selected_nodes.size() != 3 || result.total_objective != 1.5) return 6;
    return result.nodes[result.selected_nodes[1]].action_index == 1 ? 0 : 7;
}
