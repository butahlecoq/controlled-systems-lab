#include <csl/model/spatial_flight_catalogue.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <string>

namespace csl::model::catalogue {
namespace {
using spatial_flight::Control;
using spatial_flight::Model;
using spatial_flight::State;

constexpr Coordinate states[]{
    {"vx", "m/s"}, {"vy", "m/s"}, {"vz", "m/s"},
    {"phi", "rad"}, {"psi", "rad"}, {"theta", "rad"},
    {"omega_x", "rad/s"}, {"omega_y", "rad/s"}, {"omega_z", "rad/s"}};
constexpr Coordinate controls[]{{"u0", "rad"}, {"u1", "rad"}, {"u2", "rad"}};
constexpr std::string_view operations[]{
    "csl::model::discretize", "csl::model::snapshot",
    "csl::geometry::generators::affine_image", "csl::geometry::generators::minkowski_sum"};
constexpr Source source{
    "Goranov and Shorikov: linearization of an aircraft dynamic model along a reference trajectory",
    "68fc05d895d5c5c347ced535ea455c767ce0c789f3a2b90c1416cbcd37d1f1af",
    "2016 Russian-language draft, symbolic equations and kinematics; private source not redistributed",
    "Corrected B-consistent nine-state rigid-body equations with fully authored synthetic parameters, Y-up gravity, controls, reference and perturbation sets. Zero-based controls u0,u1,u2: u0 enters moments only; u1 and u2 also enter Cy/Cz. Not a historical numerical reproduction or calibrated aircraft."};
constexpr CaseInfo entry{
    "spatial-flight/b-consistent-body9-synthetic/1",
    "Synthetic B-consistent nine-state spatial flight along a varying reference",
    states, controls, 20, "s", source, operations};
constexpr std::array<CaseInfo,1> entries{entry};
constexpr std::size_t intervals=20, reference_substeps=10;
constexpr double dt=0.05, substep=dt/static_cast<double>(reference_substeps);
constexpr Control nominal{0.003,-0.002,0.002};

Diagnostics reject(std::string field, std::string reason,
                   DiagnosticCode code=DiagnosticCode::invalid_input) {
    return {{code,std::move(field),std::move(reason)}};
}
std::array<double,9> components(const State& x) {
    return {x.vx,x.vy,x.vz,x.phi,x.psi,x.theta,x.omega_x,x.omega_y,x.omega_z};
}
State state_from(const std::array<double,9>& x) {
    return {x[0],x[1],x[2],x[3],x[4],x[5],x[6],x[7],x[8]};
}
std::variant<std::array<double,9>,Diagnostics> rhs(const Model& model,
        const std::array<double,9>& x, const Control& u, std::size_t& evaluations) {
    ++evaluations;
    const auto result=model.rhs(state_from(x),u);
    if (const auto* error=std::get_if<Diagnostics>(&result)) return *error;
    return components(std::get<State>(result));
}
std::array<double,9> shifted(const std::array<double,9>& x,
        const std::array<double,9>& k, double scale) {
    std::array<double,9> out{};
    for (std::size_t i=0;i<out.size();++i) out[i]=x[i]+scale*k[i];
    return out;
}
std::variant<std::array<double,9>,Diagnostics> rk4(const Model& model,
        const std::array<double,9>& x, const Control& u, double h, std::size_t& evaluations) {
    const auto k1=rhs(model,x,u,evaluations);
    if (const auto* error=std::get_if<Diagnostics>(&k1)) return *error;
    const auto k2=rhs(model,shifted(x,std::get<std::array<double,9>>(k1),h/2),u,evaluations);
    if (const auto* error=std::get_if<Diagnostics>(&k2)) return *error;
    const auto k3=rhs(model,shifted(x,std::get<std::array<double,9>>(k2),h/2),u,evaluations);
    if (const auto* error=std::get_if<Diagnostics>(&k3)) return *error;
    const auto k4=rhs(model,shifted(x,std::get<std::array<double,9>>(k3),h),u,evaluations);
    if (const auto* error=std::get_if<Diagnostics>(&k4)) return *error;
    std::array<double,9> out{};
    for (std::size_t i=0;i<out.size();++i) {
        out[i]=x[i]+(h/6)*(std::get<std::array<double,9>>(k1)[i]+
            2*std::get<std::array<double,9>>(k2)[i]+2*std::get<std::array<double,9>>(k3)[i]+
            std::get<std::array<double,9>>(k4)[i]);
        if (!std::isfinite(out[i])) return reject("model.spatial_flight.reference", "RK4 state became nonfinite.");
    }
    return out;
}

} // namespace

std::span<const CaseInfo> spatial_flight_cases() noexcept { return entries; }

SpatialFlightResult<SpatialFlightCase> make_spatial_flight_case(
        std::string_view id, const IntegrationOptions& options) {
    if (id!=entry.id) return reject("model.spatial_flight.id", "Unknown spatial-flight case.");
    auto parameters=spatial_flight::synthetic_parameters();
    auto made=Model::make(parameters);
    if (const auto* error=std::get_if<Diagnostics>(&made)) return *error;
    const auto& model=std::get<Model>(made);

    std::vector<State> reference;
    reference.reserve(intervals+1);
    State current{100,0,0,0,0,0,0,0,0};
    reference.push_back(current);
    std::size_t evaluations=0;
    for (std::size_t stage=0;stage<intervals;++stage) {
        for (std::size_t step=0;step<reference_substeps;++step) {
            if (options.cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,"Spatial-flight reference integration cancelled."};
            const auto integrated=rk4(model,components(current),nominal,substep,evaluations);
            if (const auto* error=std::get_if<Diagnostics>(&integrated)) return *error;
            current=state_from(std::get<std::array<double,9>>(integrated));
        }
        reference.push_back(current);
    }

    Vector times(intervals+1);
    std::vector<CoefficientEndpoints> endpoints;
    endpoints.reserve(intervals);
    for (std::size_t i=0;i<=intervals;++i) times[i]=dt*static_cast<double>(i);
    std::vector<spatial_flight::Linearization> jacobians;
    jacobians.reserve(reference.size());
    for (const auto& point:reference) {
        auto checked=model.linearize(point,nominal);
        if (const auto* error=std::get_if<Diagnostics>(&checked)) return *error;
        jacobians.push_back(std::get<spatial_flight::Linearization>(std::move(checked)));
    }
    auto stage=[&](std::size_t index) {
        const auto& j=jacobians[index];
        return LinearStage{j.state,j.control,{9,0,{}},Vector(9,0)};
    };
    for (std::size_t i=0;i<intervals;++i) endpoints.push_back({stage(i),stage(i+1)});
    ContinuousAffineModel continuous{{9,3,0},times,HoldConvention::zero_order_hold,std::move(endpoints)};
    auto discretized=discretize(continuous,options);
    if (const auto* error=std::get_if<Diagnostic>(&discretized)) return Diagnostics{*error};
    if (const auto* stopped=std::get_if<OperationStopped>(&discretized)) return *stopped;
    auto discrete=std::get<DiscretizedModel>(std::move(discretized));

    const std::string prefix(entry.id);
    const Vector radii{0.1,0.02,0.02,0.001,0.001,0.001,0.0002,0.0002,0.0002};
    Matrix initial_map{9,9,Vector(81,0)};
    std::vector<sets::FactorId> initial_factors;
    std::vector<std::string> labels;
    for (std::size_t j=0;j<9;++j) {
        initial_map.values[j*9+j]=radii[j];
        labels.emplace_back(states[j].name);
        initial_factors.push_back({prefix+"/initial/"+labels.back()});
    }
    auto initial=sets::make_generator_set({{prefix+"/initial"},Vector(9,0),std::move(initial_map),
        std::move(initial_factors),{0,9,{}},{},std::move(labels)});
    if (const auto* error=std::get_if<Diagnostics>(&initial)) return *error;
    std::vector<sets::GeneratorSet> control_sets;
    control_sets.reserve(intervals);
    for (std::size_t k=0;k<intervals;++k) {
        Matrix map{3,3,{0.001,0,0,0,0.001,0,0,0,0.001}};
        const auto stage_id=prefix+"/control/"+std::to_string(k);
        auto input=sets::make_generator_set({{stage_id},Vector(3,0),std::move(map),
            {{stage_id+"/u0"},{stage_id+"/u1"},{stage_id+"/u2"}},
            {0,3,{}},{},{"u0","u1","u2"}});
        if (const auto* error=std::get_if<Diagnostics>(&input)) return *error;
        control_sets.push_back(std::get<sets::GeneratorSet>(std::move(input)));
    }
    SystemModel model_data{{{9,3,0},TimeDomain::discrete,
        std::get<std::vector<LinearStage>>(discrete.model.dynamics.stages)}, {}};
    DiscreteReachabilityCase reach{entry,std::move(model_data),std::move(times),
        std::get<sets::GeneratorSet>(std::move(initial)),std::move(control_sets)};
    return SpatialFlightCase{std::move(reach),std::move(parameters),std::move(reference),nominal,
        std::move(discrete.receipt),{"classical RK4; fixed 0.005 s steps; domain checked at every RHS evaluation",
            intervals,reference_substeps,evaluations}};
}

} // namespace csl::model::catalogue
