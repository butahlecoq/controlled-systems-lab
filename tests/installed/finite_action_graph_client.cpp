#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/optimization/finite_action_graph.hpp>
#include <csl/optimization/phase_one.hpp>

#include <variant>
#include <limits>

using namespace csl;

namespace {
template<class Port>
registry::PreparedProvider<Port> select(registry::Registration<Port> registration,
        registry::Requirements requirements) {
    const registry::Method method{registration.identity.id, registration.identity.version};
    registry::Registry<Port> providers;
    if(providers.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    auto prepared=registry::prepare_provider(registry::select_provider(providers,method,requirements));
    if(!std::holds_alternative<registry::PreparedProvider<Port>>(prepared))
        throw std::runtime_error("provider preparation failed");
    return std::get<registry::PreparedProvider<Port>>(std::move(prepared));
}

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

registry::PreparedProvider<registry::GeometryPort> reachable_provider() {
    auto lp_result=optimization::phase_one::make_registration();
    if(!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result))
        throw std::runtime_error("Phase-I LP registration unavailable");
    registry::Requirements lp_requirements;
    lp_requirements.output.representation={"csl.program-result.v1"};
    auto lp=select(std::get<registry::Registration<registry::LPPort>>(std::move(lp_result)),lp_requirements);
    auto hull=select(geometry::make_lp_hull_reducer_registration(),{});
    geometry::AffineSumDependencies dependencies{std::move(hull),std::move(lp),std::nullopt};
    registry::Requirements geometry_requirements;
    geometry_requirements.output.representation={"csl.polyhedron.v"};
    geometry_requirements.output.relation=SetRelation::equivalent;
    geometry_requirements.output.assurance=Assurance::numerical;
    return select(geometry::make_affine_sum_registration(std::move(dependencies)),geometry_requirements);
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
        std::get<registry::PreparedProvider<registry::GeometryPort>>(provider), reachable_provider());
    if(!std::holds_alternative<optimization::FiniteActionGraphResult>(graph)) return 5;
    const auto& result = std::get<optimization::FiniteActionGraphResult>(graph);
    if(!result.has_viable_path || result.selected_nodes.size() != 3 || result.total_objective != 1.5) return 6;
    if(result.reachable_envelope_calls != 6 ||
       result.nodes[result.selected_nodes[1]].reachable_envelope_contains != true) return 8;
    if(result.nodes[result.selected_nodes[1]].action_index != 1) return 7;
    optimization::FiniteGraphActionCloudEnvelope cloud;
    cloud.outer_lower={-1,-1}; cloud.outer_upper={1,1};
    cloud.selected_outer_shape=optimization::FiniteGraphBoxShape{{-1,-1},{1,1}};
    const auto membership=optimization::finite_graph_action_cloud_membership(cloud,Vector{0.5,0.5});
    if(!membership.supported || !membership.contained || membership.method.empty()) return 9;
    const auto box_reject=optimization::finite_graph_action_cloud_membership(cloud,Vector{1.5,0.0});
    if(!box_reject.supported || box_reject.contained) return 10;
    cloud.selected_outer_shape=optimization::FiniteGraphParallelotopeShape{
        Matrix{2,2,{1,1,0,1}},{-0.1,-0.1},{0.1,0.1}};
    if(!optimization::finite_graph_action_cloud_membership(cloud,Vector{0,0.19}).supported ||
       optimization::finite_graph_action_cloud_membership(cloud,Vector{0,0.19}).contained) return 11;
    cloud.selected_outer_shape=optimization::FiniteGraphEllipsoidShape{{0,0},{0.2,0.1}};
    if(!optimization::finite_graph_action_cloud_membership(cloud,Vector{0.18,0.09}).supported ||
       optimization::finite_graph_action_cloud_membership(cloud,Vector{0.18,0.09}).contained) return 12;
    cloud.selected_outer_shape=optimization::FiniteGraphZonotopeShape{{0,0},Matrix{2,1,{1,1}}};
    if(!optimization::finite_graph_action_cloud_membership(cloud,Vector{1,-1}).supported ||
       optimization::finite_graph_action_cloud_membership(cloud,Vector{1,-1}).contained) return 13;
    cloud.selected_outer_shape=optimization::FiniteGraphZonotopeShape{{0,0},Matrix{2,4,{1,0,1,0,0,1,0,1}}};
    const auto repeated=optimization::finite_graph_action_cloud_membership(cloud,Vector{1.5,0});
    if(!repeated.supported || !repeated.contained || repeated.witness_coordinates.size()!=4) return 14;
    cloud.selected_outer_shape=optimization::FiniteGraphZonotopeShape{
        {std::numeric_limits<double>::quiet_NaN(),0},Matrix{2,0,{}}};
    const auto malformed=optimization::finite_graph_action_cloud_membership(cloud,Vector{0,0});
    if(malformed.supported || malformed.contained) return 15;
    return 0;
}
