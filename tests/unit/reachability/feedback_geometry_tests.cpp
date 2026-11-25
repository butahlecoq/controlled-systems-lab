#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_tube.hpp>
#include <csl/reachability/feedback_geometry.hpp>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace {
template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("Installed nominal-tube consumer setup was rejected.");
    return std::get<T>(std::move(value));
}

template<class Port> csl::registry::PreparedProvider<Port> selected(
        csl::registry::Registration<Port> registration, std::string representation) {
    csl::registry::Registry<Port> providers;
    const csl::registry::Method method{registration.identity.id, registration.identity.version};
    if (providers.add(std::move(registration))) throw std::runtime_error("Provider registration rejected.");
    csl::registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, csl::registry::GeometryPort> ||
                  std::is_same_v<Port, csl::registry::ConversionPort>)
        requirements.output.relation = csl::SetRelation::equivalent;
    return take(csl::registry::prepare_provider(
        csl::registry::select_provider(providers, method, requirements)));
}

csl::SetHandle box(std::string id, csl::Vector lower, csl::Vector upper) {
    using namespace csl;
    const auto dimension = lower.size();
    if (dimension != upper.size()) throw std::runtime_error("Invalid box dimensions.");
    Matrix rows{2 * dimension, dimension, Vector(2 * dimension * dimension, 0.0)};
    Vector rhs(2 * dimension, 0.0);
    for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        rows.values[(2 * coordinate) * dimension + coordinate] = 1.0;
        rhs[2 * coordinate] = upper[coordinate];
        rows.values[(2 * coordinate + 1) * dimension + coordinate] = -1.0;
        rhs[2 * coordinate + 1] = -lower[coordinate];
    }
    std::vector<std::string> labels;
    if(dimension==2) labels={"x","y"};
    else for(std::size_t i=0;i<dimension;++i) labels.push_back("x"+std::to_string(i));
    return take(sets::make_h({{std::move(id)}, dimension, labels},
        {take(numeric::snapshot(rows)), take(numeric::snapshot_vector(rhs)),
         take(numeric::snapshot(Matrix{0, dimension, {}})),
         take(numeric::snapshot_vector({}))})).as_handle();
}

bool contains(const csl::sets::HRepresentation& h, const csl::Vector& point) {
    if (point.size() != h.inequalities.cols()) return false;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < point.size(); ++column)
            value += h.inequalities(row, column) * point[column];
        if (value > h.upper_bounds[row] + 1e-10) return false;
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < point.size(); ++column)
            value += h.equalities(row, column) * point[column];
        if (std::abs(value - h.equality_values[row]) > 1e-10) return false;
    }
    return true;
}

bool axis_membership_contains(const csl::reachability::FeedbackMembership& member, const csl::Vector& point) {
    using namespace csl;
    if(const auto* h=std::get_if<reachability::FeedbackHMembership>(&member)) {
        auto data=take(sets::from_handle(h->set)); auto repr=data.representation();
        const auto* rows=std::get_if<sets::HRepresentation>(&repr);
        return rows && contains(*rows,point);
    }
    Vector center; Matrix factor; bool ball=false;
    if(const auto* z=std::get_if<reachability::FeedbackZonotopeMembership>(&member)) { center=z->center; factor=z->generators; }
    else { const auto& e=std::get<reachability::FeedbackEllipsoidMembership>(member); center=e.center; factor=e.factor; ball=true; }
    if(center.size()!=point.size() || factor.rows!=point.size() || factor.cols!=point.size()) return false;
    double norm=0;
    for(std::size_t j=0;j<point.size();++j) {
        const auto d=factor.values[j*factor.cols+j];
        if(d==0) { if(std::abs(center[j]-point[j])>1e-10) return false; }
        else { const auto x=(point[j]-center[j])/d; norm+=x*x; if(!ball && std::abs(x)>1+1e-10) return false; }
    }
    return !ball || norm<=1+1e-10;
}
}

int main() {
    using namespace csl;
    try {
        auto lp = take(adapters::lp::make_highs_registration());
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
        auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"),
            selected(converter, "csl.polyhedron.v")}, {{}, {}});
        reachability::ForwardDependencies forward{
            selected(geometry::polyhedral::make_projection_registration(), "csl.polyhedron.h"),
            selected(std::move(affine), "csl.polyhedron.v"),
            selected(converter, "csl.polyhedron.h")};
        auto intersection = selected(geometry::polyhedral::make_intersection_registration(),
            "csl.polyhedron.h");

        const auto model = std::make_shared<const SystemModel>(SystemModel{{{2, 2, 0},
            TimeDomain::discrete,
            std::vector<LinearStage>{{{2, 2, {1, 0, 0, 1}}, {2, 2, {1, 0, 0, 1}},
                {2, 0, {}}, {0, 0}}}}, {}});
        const std::vector<std::string> state_labels{"x", "y"};
        Problem source{{"installed-tube"}, model, {0, 1}, KnownInitial{{0.2, 0.4}},
            ContinuousDomain{{box("u0", {-0.2, -0.1}, {0.3, 0.2})}},
            {box("X0", {-1.0, -1.0}, {1.0, 1.0}),
             box("X1", {0.0, 0.1}, {0.8, 0.9})}, {}, {},
            InformationPattern::nominal_open_loop,
            QuadraticTerminal{{2, 2, {2, 0, 0, 2}}, {0, 0}, 0}};
        const auto resolved = take(problem::resolve(source,
            {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        for (auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                reachability::FeedbackFamily::ellipsoid}) {
            auto outcome=reachability::feedback_geometry(resolved,{"analytic"},
                box("physical-terminal", {0.0, 0.1}, {0.8, 0.9}),family,{},
                {{forward,intersection}, selected(lp,"csl.program-result.v1"), 1000}, {});
            if (auto* failure=std::get_if<reachability::FeedbackGeometryFailure>(&outcome)) {
                std::cerr << "family " << static_cast<int>(family) << " stage " << failure->stage.value << " phase " << static_cast<int>(failure->phase) << "\n";
                std::visit([](const auto& cause) { using T=std::decay_t<decltype(cause)>;
                    if constexpr(std::is_same_v<T,Unsupported>) for(const auto& d:cause.diagnostics) std::cerr << d.field << ": " << d.explanation << "\n";
                    else std::cerr << cause.diagnostics << "\n"; },failure->cause);
                return 2;
            }
            const auto& geometry=std::get<reachability::FeedbackGeometry>(outcome);
            if(geometry.stages.size()!=2) return 3;
            for(const auto& stage:geometry.stages) {
                if(!stage.forward || !stage.backward || !stage.intersection || !stage.forward_h || !stage.backward_h || !stage.intersection_h || !stage.forward_embedding_h || !stage.backward_embedding_h) return 4;
                if(stage.forward->id.value.empty() || stage.backward->id.value.empty() || stage.intersection->id.value.empty() ||
                    stage.forward->id==stage.backward->id || stage.forward->id==stage.intersection->id || stage.backward->id==stage.intersection->id) return 17;
                auto full=take(sets::from_handle(stage.intersection_h->output));
                auto full_repr=full.representation();
                const auto* full_h=std::get_if<sets::HRepresentation>(&full_repr);
                if(!full_h || !contains(*full_h,{0.2,0.4})) return 5;
                const auto& member=stage.intersection->membership;
                if(const auto* h=std::get_if<reachability::FeedbackHMembership>(&member)) {
                    auto data=take(sets::from_handle(h->set)); auto repr=data.representation();
                    auto* rows=std::get_if<sets::HRepresentation>(&repr);
                    if(!rows || !contains(*rows,{0.2,0.4})) return 6;
                } else {
                    Vector center; Matrix factor; bool ball=false;
                    if(const auto* z=std::get_if<reachability::FeedbackZonotopeMembership>(&member)) { center=z->center; factor=z->generators; }
                    else { const auto& e=std::get<reachability::FeedbackEllipsoidMembership>(member); center=e.center; factor=e.factor; ball=true; }
                    double norm=0;
                    for(std::size_t j=0;j<2;++j) {
                        auto d=factor.values[j*factor.cols+j];
                        if(d==0) { if(std::abs(center[j]-Vector{0.2,0.4}[j])>1e-10) return 7; }
                        else { double x=(Vector{0.2,0.4}[j]-center[j])/d; norm+=x*x; if(!ball && std::abs(x)>1+1e-10) return 8; }
                    }
                    if(ball && norm>1+1e-10) return 9;
                }
            }
            const auto& from=geometry.stages[0].forward->id;
            const auto& inputs=geometry.stages[1].forward->source_sets;
            if(std::find(inputs.begin(),inputs.end(),from)==inputs.end()) return 18;
        }
        const auto model4=std::make_shared<const SystemModel>(SystemModel{{{4,2,0}, TimeDomain::discrete,
            std::vector<LinearStage>{{{4,4,{1,1,0,0, 0,1,0,0, 0,0,1,1, 0,0,0,0}},
                {4,2,{1,0, 0,1, 1,0, 0,1}}, {4,0,{}}, {0,0,0,0}}}}, {}});
        Problem source4{{"four-singular"},model4,{0,1},KnownInitial{{0.2,0.4,0.6,0.8}},
            ContinuousDomain{{box("u4",{-0.1,-0.1},{0.1,0.1})}},
            {box("X40",{-3,-3,-3,-3},{3,3,3,3}),box("X41",{-3,-3,-3,-3},{3,3,3,3})},
            {},{},InformationPattern::nominal_open_loop,
            QuadraticTerminal{{4,4,{2,0,0,0,0,2,0,0,0,0,2,0,0,0,0,2}},{0,0,0,0},0}};
        const auto resolved4=take(problem::resolve(source4,
            {problem::UncertaintyStructure::stage_product_uncoupled,{}, {}}));
        for(auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                reachability::FeedbackFamily::ellipsoid}) {
            auto result=reachability::feedback_geometry(resolved4,{"four-singular"},
                box("terminal4",{-3,-3,-3,-3},{3,3,3,3}),family,{{0,0}},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},{});
            if(auto* failure=std::get_if<reachability::FeedbackGeometryFailure>(&result)) {
                std::cerr << "4D family " << static_cast<int>(family) << " stage " << failure->stage.value << " phase " << static_cast<int>(failure->phase) << "\n";
                std::visit([](const auto& cause) { using T=std::decay_t<decltype(cause)>;
                    if constexpr(std::is_same_v<T,Unsupported>) for(const auto& d:cause.diagnostics) std::cerr << d.field << ": " << d.explanation << "\n";
                    else std::cerr << cause.diagnostics << "\n"; },failure->cause);
                return 10;
            }
            const auto& g=std::get<reachability::FeedbackGeometry>(result);
            if(g.stages.size()!=2 || !g.stages[1].intersection_h || !g.stages[1].intersection ||
                g.stages[1].intersection->strict_source_domain.size()!=1 ||
                g.stages[1].intersection->strict_source_domain[0].lower_bound!=0) return 11;
            auto hdata=take(sets::from_handle(g.stages[1].intersection_h->output));
            auto hrepr=hdata.representation(); auto* h=std::get_if<sets::HRepresentation>(&hrepr);
            if(!h || !contains(*h,{0.6,0.4,1.4,0}) ||
                !axis_membership_contains(g.stages[1].intersection->membership,{0.6,0.4,1.4,0})) return 12;
        }
        const auto no_control_model=std::make_shared<const SystemModel>(SystemModel{{{2,0,0}, TimeDomain::discrete,
            std::vector<LinearStage>{{{2,2,{1,0,0,0}}, {2,0,{}}, {2,0,{}}, {0,0}}}}, {}});
        Problem no_control{{"no-control"},no_control_model,{0,1},KnownInitial{{0.2,0.4}},
            ContinuousDomain{{UniversalSet{0}}},
            {box("N0",{-2,-2},{2,2}),box("N1",{-2,-2},{2,2})}, {},{},
            InformationPattern::nominal_open_loop,QuadraticTerminal{{2,2,{2,0,0,2}},{0,0},0}};
        const auto resolved_no_control=take(problem::resolve(no_control,
            {problem::UncertaintyStructure::stage_product_uncoupled,{}, {}}));
        for(auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                reachability::FeedbackFamily::ellipsoid}) {
            auto result=reachability::feedback_geometry(resolved_no_control,{"no-control"},
                box("NT",{-2,-2},{2,2}),family,{},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},{});
            if(!std::holds_alternative<reachability::FeedbackGeometry>(result)) return 15;
            const auto& g=std::get<reachability::FeedbackGeometry>(result);
            if(!g.stages[1].intersection || !axis_membership_contains(g.stages[1].intersection->membership,{0.2,0})) return 16;
        }
        const auto fixed_model=std::make_shared<const SystemModel>(SystemModel{{{2,1,0}, TimeDomain::discrete,
            std::vector<LinearStage>{{{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}}, {}});
        for(double fixed : {0.0,0.75}) {
            Problem fixed_problem{{"fixed-control"},fixed_model,{0,1},KnownInitial{{0.2,0.4}},
                ContinuousDomain{{Singleton{{fixed}}}},
                {box("fixed-X0",{-2,-2},{2,2}),box("fixed-X1",{-2,-2},{2,2})}, {},{},
                InformationPattern::nominal_open_loop,QuadraticTerminal{{2,2,{2,0,0,2}},{0,0},0}};
            const auto fixed_resolved=take(problem::resolve(fixed_problem,
                {problem::UncertaintyStructure::stage_product_uncoupled,{}, {}}));
            for(auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                    reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                    reachability::FeedbackFamily::ellipsoid}) {
                auto result=reachability::feedback_geometry(fixed_resolved,{"fixed-control"},
                    box("fixed-terminal",{-2,-2},{2,2}),family,{},
                    {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},{});
                if(auto* failure=std::get_if<reachability::FeedbackGeometryFailure>(&result)) {
                    std::cerr << "fixed control " << fixed << " family " << static_cast<int>(family) << " failed at " << failure->stage.value << "\n";
                    return 19;
                }
                const auto& g=std::get<reachability::FeedbackGeometry>(result);
                if(!g.stages[1].intersection || !axis_membership_contains(g.stages[1].intersection->membership,{0.2+fixed,0.4})) return 20;
            }
        }
        const auto coupled_control=take(sets::make_h({{"rotated-control"},4,{}},
            {take(numeric::snapshot(Matrix{4,4,{1,1,0,0, -1,-1,0,0, 1,-1,0,0, -1,1,0,0}})),
             take(numeric::snapshot_vector(Vector{1,1,1,1})),
             take(numeric::snapshot(Matrix{2,4,{0,0,1,1, 0,0,1,-1}})),
             take(numeric::snapshot_vector(Vector{0,0}))})).as_handle();
        const auto rotated_model=std::make_shared<const SystemModel>(SystemModel{{{2,4,0},TimeDomain::discrete,
            std::vector<LinearStage>{{{2,2,{1,0,0,1}}, {2,4,{1,0,0,0, 0,1,0,0}}, {2,0,{}}, {0,0}}}}, {}});
        Problem rotated{{"rotated-control"},rotated_model,{0,1},KnownInitial{{0.2,0.4}},
            ContinuousDomain{{coupled_control}}, {box("R0",{-2,-2},{2,2}),box("R1",{-2,-2},{2,2})}, {},{},
            InformationPattern::nominal_open_loop,QuadraticTerminal{{2,2,{2,0,0,2}},{0,0},0}};
        const auto resolved_rotated=take(problem::resolve(rotated,
            {problem::UncertaintyStructure::stage_product_uncoupled,{}, {}}));
        for(auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                reachability::FeedbackFamily::ellipsoid}) {
            auto result=reachability::feedback_geometry(resolved_rotated,{"rotated-control"},
                box("RT",{-2,-2},{2,2}),family,{},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},{});
            if(auto* failure=std::get_if<reachability::FeedbackGeometryFailure>(&result)) {
                std::cerr << "rotated control family " << static_cast<int>(family) << " failed at " << failure->stage.value << "\n";
                return 21;
            }
            const auto& g=std::get<reachability::FeedbackGeometry>(result);
            if(!g.stages[1].intersection || !g.stages[1].forward || g.stages[1].forward->auxiliary_input_carriers.size()!=1) return 22;
            auto carrier_data=take(sets::from_handle(g.stages[1].forward->auxiliary_input_carriers[0]));
            auto carrier_repr=carrier_data.representation();
            const auto* carrier=std::get_if<sets::HRepresentation>(&carrier_repr);
            if(!carrier || !contains(*carrier,{1,0,0,0}) || !contains(*carrier,{-1,0,0,0}) ||
                !contains(*carrier,{0,1,0,0}) || !contains(*carrier,{0,-1,0,0})) return 23;
            bool found_carrier_evidence=false;
            for(const auto& evidence:g.stages[1].forward->lineage)
                if(evidence.reference.identity.request.value.find("exact-control-carrier")!=std::string::npos) {
                    found_carrier_evidence=true;
                    if(evidence.reference.identity.ideal_output.value!=g.stages[1].forward->auxiliary_input_carriers[0].id.value) return 24;
                    if(evidence.scope!=GeometryClaimScope::set_relation) return 28;
                }
            if(!found_carrier_evidence) return 25;
            for(const Vector& point : std::vector<Vector>{{0.2,0.4},{1.2,0.4},{-0.8,0.4},{0.2,1.4},{0.2,-0.6}})
                if(!axis_membership_contains(g.stages[1].intersection->membership,point)) return 22;
        }
        const reachability::FeedbackGeometryDependencies certified_deps{
            {forward, intersection}, selected(lp,"csl.program-result.v1"), 1000};
        const auto certified_mode = reachability::FeedbackPolytopeHistory::certified_whole_history;
        const auto certified = reachability::feedback_geometry(resolved,{"exact-history"},
            box("narrow-terminal", {0.25,0.375}, {0.375,0.5}),
            reachability::FeedbackFamily::polytope, {}, certified_deps, certified_mode, {});
        const auto* complete = std::get_if<reachability::FeedbackGeometry>(&certified);
        if(!complete || complete->stages.size()!=2) return 29;
        for(const auto& stage : complete->stages) {
            if(!stage.forward || !stage.backward || !stage.intersection) return 30;
            for(const auto* geometry : {&*stage.forward, &*stage.backward, &*stage.intersection})
                if(geometry->assurance!=Assurance::validated ||
                   geometry->relation!=SetRelation::outer || geometry->lineage.empty()) return 31;
            if(stage.forward->id==stage.backward->id || stage.backward->id==stage.intersection->id)
                return 32;
        }
        const auto& terminal_stage = complete->stages[1];
        if(!axis_membership_contains(terminal_stage.forward->membership,{0.45,0.45}) ||
           axis_membership_contains(terminal_stage.intersection->membership,{0.45,0.45}) ||
           !axis_membership_contains(terminal_stage.intersection->membership,{0.3,0.45}))
            return 33;
        const auto impossible = reachability::feedback_geometry(resolved,{"exact-impossible-terminal"},
            box("impossible-terminal", {2,2}, {3,3}),
            reachability::FeedbackFamily::polytope, {}, certified_deps, certified_mode, {});
        const auto* infeasible = std::get_if<reachability::FeedbackGeometry>(&impossible);
        if(!infeasible || !infeasible->stages[0].intersection ||
           axis_membership_contains(infeasible->stages[0].intersection->membership,{0.2,0.4}))
            return 34;

        auto affine_box_source = source;
        affine_box_source.id = {"affine-box-history"};
        affine_box_source.initial = KnownInitial{{0.5, 0.5}};
        affine_box_source.states = {UniversalSet{2}, UniversalSet{2}};
        affine_box_source.controls = ContinuousDomain{{box("dyadic-controls", {-0.25, -0.125},
                                                           {0.25, 0.125})}};
        const auto affine_box_resolved = take(problem::resolve(
            affine_box_source, {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        const auto universal = take(sets::make_universal({{"universal-terminal"}, 2, {}})).as_handle();
        const auto affine_box_mode = reachability::FeedbackPolytopeHistory::certified_stagewise;
        const auto affine_box = reachability::feedback_geometry(
            affine_box_resolved, {"affine-box-history"}, universal,
            reachability::FeedbackFamily::polytope, {{0, 0}}, certified_deps, affine_box_mode, {});
        const auto* affine_box_geometry = std::get_if<reachability::FeedbackGeometry>(&affine_box);
        if (!affine_box_geometry || affine_box_geometry->stages.size() != 2)
            return 37;
        const auto& affine_box_terminal = affine_box_geometry->stages.back();
        for (const auto* set : {&affine_box_terminal.forward, &affine_box_terminal.backward,
                                &affine_box_terminal.intersection}) {
            if (!*set || (*set)->assurance != Assurance::validated ||
                (*set)->relation != SetRelation::outer)
                return 38;
            for (const double x : {0.25, 0.75})
                for (const double y : {0.375, 0.625})
                    if (!axis_membership_contains((*set)->membership, {x, y}))
                        return 39;
            if (axis_membership_contains((*set)->membership, {0.875, 0.5}))
                return 40;
        }
        const auto affine_box_impossible = reachability::feedback_geometry(
            affine_box_resolved, {"affine-box-impossible"}, box("disjoint-terminal", {2, 2}, {3, 3}),
            reachability::FeedbackFamily::polytope, {{0, 0}}, certified_deps, affine_box_mode, {});
        const auto* affine_box_infeasible =
            std::get_if<reachability::FeedbackGeometry>(&affine_box_impossible);
        if (!affine_box_infeasible || !affine_box_infeasible->stages.front().intersection ||
            axis_membership_contains(affine_box_infeasible->stages.front().intersection->membership,
                                     {0.5, 0.5}))
            return 41;

        const auto too_many_rows = take(sets::make_h({{"oversized-terminal"},2,state_labels},
            {take(numeric::snapshot(Matrix{4097,2,Vector(8194,0)})),
             take(numeric::snapshot_vector(Vector(4097,1))),
             take(numeric::snapshot(Matrix{0,2,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
        const auto oversized = reachability::feedback_geometry(resolved,{"exact-oversized-terminal"},
            too_many_rows, reachability::FeedbackFamily::polytope, {}, certified_deps, certified_mode, {});
        const auto* oversized_failure = std::get_if<reachability::FeedbackGeometryFailure>(&oversized);
        if(!oversized_failure || !oversized_failure->prefix.stages.empty()) return 35;
        const auto* oversized_stop = std::get_if<OperationStopped>(&oversized_failure->cause);
        if(!oversized_stop || oversized_stop->reason!=StopReason::resource_limit) return 36;

        const auto unbounded_control=take(sets::make_h({{"unbounded-control"},4,{}},
            {take(numeric::snapshot(Matrix{0,4,{}})),take(numeric::snapshot_vector(Vector{})),
             take(numeric::snapshot(Matrix{2,4,{1,-1,0,0, 0,0,1,-1}})),
             take(numeric::snapshot_vector(Vector{0,0}))})).as_handle();
        auto unbounded=rotated; unbounded.id={"unbounded-control"};
        unbounded.controls=ContinuousDomain{{unbounded_control}};
        const auto resolved_unbounded=take(problem::resolve(unbounded,
            {problem::UncertaintyStructure::stage_product_uncoupled,{}, {}}));
        for(auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                reachability::FeedbackFamily::ellipsoid}) {
            auto result=reachability::feedback_geometry(resolved_unbounded,{"unbounded-control"},
                box("UT",{-2,-2},{2,2}),family,{},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},{});
            auto* failure=std::get_if<reachability::FeedbackGeometryFailure>(&result);
            if(!failure || failure->stage.value!=1 || !failure->prefix.stages[0].forward ||
                !failure->pending_input_carriers.empty()) return 26;
            auto* unsupported=std::get_if<Unsupported>(&failure->cause);
            if(!unsupported || unsupported->diagnostics.empty() || unsupported->diagnostics[0].field!="feedback.control.bounds") return 27;
        }
        auto limited=reachability::feedback_geometry(resolved,{"limited"},
            box("limited-terminal",{0.0,0.1},{0.8,0.9}),reachability::FeedbackFamily::zonotope,{},
            {{forward,intersection},selected(lp,"csl.program-result.v1"),0},{});
        const auto* stopped=std::get_if<reachability::FeedbackGeometryFailure>(&limited);
        if(!stopped || stopped->stage.value!=1 || stopped->prefix.stages.empty() || !stopped->prefix.stages[0].forward) return 13;
        const auto* limit=std::get_if<OperationStopped>(&stopped->cause);
        if(!limit || limit->reason!=StopReason::resource_limit) return 14;

        // Nonaxis parallelotope frames: the direct enclosure API, the rotated
        // profile through the coordinator, and the preserved axis profile.
        const double root_half = std::sqrt(0.5);
        const auto rotate = reachability::fixed_rotation_45_frame(2);
        auto shaped = reachability::frame_enclosure({"frame-enclosure-test"}, rotate,
            {-0.5,-0.25}, {0.5,0.25}, state_labels);
        if (!std::holds_alternative<reachability::FeedbackMembership>(shaped)) return 42;
        const auto& framed = std::get<reachability::FeedbackMembership>(shaped);
        const auto* framed_member = std::get_if<reachability::FeedbackHMembership>(&framed);
        if (!framed_member || !framed_member->parallelotope_frame ||
            !framed_member->parallelotope_frame_bounds) return 43;
        if (framed_member->parallelotope_frame->values != rotate.values) return 44;
        {
            const auto& [frame_lo, frame_hi] = *framed_member->parallelotope_frame_bounds;
            if (frame_lo.size()!=2 || frame_hi.size()!=2 ||
                std::abs(frame_lo[0]+0.5)>1e-12 || std::abs(frame_hi[0]-0.5)>1e-12 ||
                std::abs(frame_lo[1]+0.25)>1e-12 || std::abs(frame_hi[1]-0.25)>1e-12) return 45;
        }
        {
            auto framed_data = take(sets::from_handle(framed_member->set));
            auto framed_repr = framed_data.representation();
            const auto* framed_h = std::get_if<sets::HRepresentation>(&framed_repr);
            if (!framed_h || framed_h->inequalities.rows()!=4) return 46;
            // The H rows are the frame columns, so frame-box corners are
            // members while a point past the certified bounds is not.
            if (!contains(*framed_h, {0.75*root_half, 0.25*root_half}) ||
                !contains(*framed_h, {-0.75*root_half, -0.25*root_half}) ||
                contains(*framed_h, {0.62*root_half, 0.62*root_half})) return 47;
        }
        if (!std::holds_alternative<Diagnostics>(
                reachability::frame_enclosure({"frame-inverted"}, rotate, {0.5,0.25},
                    {-0.5,-0.25}, state_labels))) return 48;
        if (!std::holds_alternative<Diagnostics>(
                reachability::frame_enclosure({"frame-zero"}, Matrix{2,2,Vector(4,0)},
                    {-1,-1}, {1,1}, state_labels))) return 49;
        const Vector witness{0.2,0.4};
        for (auto rule : {reachability::ParallelotopeFrameRule::axis,
                reachability::ParallelotopeFrameRule::fixed_rotation_45}) {
            auto outcome_rule = reachability::feedback_geometry(resolved,{"frame-rule"},
                box("physical-terminal",{0.0,0.1},{0.8,0.9}),
                reachability::FeedbackFamily::parallelotope,{},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},
                reachability::FeedbackGeometryOptions{
                    reachability::FeedbackPolytopeHistory::stagewise, rule},{});
            if (!std::holds_alternative<reachability::FeedbackGeometry>(outcome_rule)) return 50;
            const auto& rule_geometry = std::get<reachability::FeedbackGeometry>(outcome_rule);
            const auto& expected_frame =
                rule==reachability::ParallelotopeFrameRule::axis
                    ? reachability::identity_parallelotope_frame(2) : rotate;
            for (const auto& stage : rule_geometry.stages) {
                for (const auto* member : {&stage.forward, &stage.backward, &stage.intersection}) {
                    if (!*member) return 51;
                    const auto* shaped_h = std::get_if<reachability::FeedbackHMembership>(
                        &(*member)->membership);
                    if (!shaped_h || !shaped_h->parallelotope_frame ||
                        !shaped_h->parallelotope_frame_bounds ||
                        shaped_h->parallelotope_frame->values != expected_frame.values) return 52;
                    const auto& [lo, hi] = *shaped_h->parallelotope_frame_bounds;
                    for (std::size_t i = 0; i < 2; ++i)
                        if (!(std::isfinite(lo[i]) && std::isfinite(hi[i]) && lo[i] <= hi[i]))
                            return 53;
                }
                // The intersection membership contains the observation in
                // frame coordinates: factor = frame^T * state within bounds.
                const auto* intersection_h = std::get_if<reachability::FeedbackHMembership>(
                    &stage.intersection->membership);
                const auto& [lo, hi] = *intersection_h->parallelotope_frame_bounds;
                for (std::size_t i = 0; i < 2; ++i) {
                    double factor = 0;
                    for (std::size_t j = 0; j < 2; ++j)
                        factor += expected_frame.values[j*2+i] * witness[j];
                    if (factor < lo[i]-1e-9 || factor > hi[i]+1e-9) return 54;
                }
                if (rule==reachability::ParallelotopeFrameRule::fixed_rotation_45) {
                    bool framed_note = false;
                    for (const auto& note : stage.forward->construction)
                        if (note.find("fixed-rotation-45")!=std::string::npos) framed_note = true;
                    if (!framed_note) return 55;
                }
            }
        }
        auto polytope_rotated = reachability::feedback_geometry(resolved,{"polytope-frame-rule"},
            box("physical-terminal",{0.0,0.1},{0.8,0.9}),
            reachability::FeedbackFamily::polytope,{},
            {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},
            reachability::FeedbackGeometryOptions{
                reachability::FeedbackPolytopeHistory::stagewise,
                reachability::ParallelotopeFrameRule::fixed_rotation_45},{});
        if (!std::holds_alternative<reachability::FeedbackGeometry>(polytope_rotated)) return 56;
        const auto& polytope_geometry = std::get<reachability::FeedbackGeometry>(polytope_rotated);
        for (const auto& stage : polytope_geometry.stages) {
            const auto* plain = std::get_if<reachability::FeedbackHMembership>(
                &stage.intersection->membership);
            if (!plain || plain->parallelotope_frame || plain->parallelotope_frame_bounds)
                return 57;
        }
        // Deterministic support selection. The wide-control diamond problem
        // makes the 45-degree frame tighter for the backward and intersection
        // enclosures while the forward rollout stays axis aligned; the
        // axis-aligned terminal problem retains the identity frame.
        {
            const auto wide_model = std::make_shared<const SystemModel>(SystemModel{{{2,2,0},
                TimeDomain::discrete,
                std::vector<LinearStage>{{{2,2,{1,0,0,1}}, {2,2,{1,0,0,1}},
                    {2,0,{}}, {0,0}}}}, {}});
            Problem wide{{"wide-diamond"},wide_model,{0,1},KnownInitial{{0.2,0.4}},
                ContinuousDomain{{box("wide-u",{-2,-2},{2,2})}},
                {box("W0",{-3,-3},{3,3}),box("W1",{-3,-3},{3,3})}, {},{},
                InformationPattern::nominal_open_loop,
                QuadraticTerminal{{2,2,{2,0,0,2}},{0,0},0}};
            const auto resolved_wide = take(problem::resolve(wide,
                {problem::UncertaintyStructure::stage_product_uncoupled,{}, {}}));
            auto diamond_terminal = take(sets::make_h({{"diamond-terminal"},2,state_labels},
                {take(numeric::snapshot(Matrix{4,2,{1,1, -1,-1, 1,-1, -1,1}})),
                 take(numeric::snapshot_vector(Vector{1,1,1,1})),
                 take(numeric::snapshot(Matrix{0,2,{}})),
                 take(numeric::snapshot_vector(Vector{}))})).as_handle();
            auto selection = reachability::feedback_geometry(resolved_wide,{"selected-frame"},
                diamond_terminal, reachability::FeedbackFamily::parallelotope, {},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},
                reachability::FeedbackGeometryOptions{
                    reachability::FeedbackPolytopeHistory::stagewise,
                    reachability::ParallelotopeFrameRule::support_selected},{});
            if (!std::holds_alternative<reachability::FeedbackGeometry>(selection)) return 58;
            const auto& selection_geometry = std::get<reachability::FeedbackGeometry>(selection);
            const auto& terminal_stage = selection_geometry.stages[1];
            const auto frame_of = [](const reachability::FeedbackMembership& membership) {
                return std::get<reachability::FeedbackHMembership>(membership)
                    .parallelotope_frame->values;
            };
            const auto note_of = [](const reachability::FeedbackSet& shape) {
                for (const auto& line : shape.construction)
                    if (line.find("selected ")==0) return line;
                return std::string{};
            };
            if (frame_of(terminal_stage.forward->membership) !=
                reachability::identity_parallelotope_frame(2).values) return 59;
            if (note_of(*terminal_stage.forward).find("selected axis")==std::string::npos)
                return 60;
            if (frame_of(terminal_stage.backward->membership) != rotate.values) return 61;
            if (note_of(*terminal_stage.backward).find("selected fixed-rotation-45")==
                std::string::npos) return 62;
            // The intersection encloses the axis embedding of the framed
            // backward membership, which is the diamond's outer box, so the
            // axis frame is the tighter cover there.
            if (frame_of(terminal_stage.intersection->membership) !=
                reachability::identity_parallelotope_frame(2).values) return 63;
            if (note_of(*terminal_stage.intersection).find("selected axis")==std::string::npos)
                return 64;
            auto axis_terminal_selection = reachability::feedback_geometry(resolved,
                {"selected-axis-terminal"},
                box("physical-terminal",{0.0,0.1},{0.8,0.9}),
                reachability::FeedbackFamily::parallelotope,{},
                {{forward,intersection},selected(lp,"csl.program-result.v1"),1000},
                reachability::FeedbackGeometryOptions{
                    reachability::FeedbackPolytopeHistory::stagewise,
                    reachability::ParallelotopeFrameRule::support_selected},{});
            if (!std::holds_alternative<reachability::FeedbackGeometry>(axis_terminal_selection))
                return 65;
            const auto& axis_geometry = std::get<reachability::FeedbackGeometry>(axis_terminal_selection);
            const auto& axis_terminal_stage = axis_geometry.stages[1];
            if (frame_of(axis_terminal_stage.backward->membership) !=
                reachability::identity_parallelotope_frame(2).values) return 66;
            if (note_of(*axis_terminal_stage.backward).find("selected axis")==std::string::npos)
                return 67;
        }
        std::cout << "Five-family feedback geometry: full-state and family membership passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
