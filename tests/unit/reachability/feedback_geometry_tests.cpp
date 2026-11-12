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
                }
            if(!found_carrier_evidence) return 25;
            for(const Vector& point : std::vector<Vector>{{0.2,0.4},{1.2,0.4},{-0.8,0.4},{0.2,1.4},{0.2,-0.6}})
                if(!axis_membership_contains(g.stages[1].intersection->membership,point)) return 22;
        }
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
        std::cout << "Five-family feedback geometry: full-state and family membership passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
