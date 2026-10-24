#include <csl/problem/temporal_lifts.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>
#include <vector>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The EXT-03 measurement executable must be compiled as a Release target"
#endif

using namespace csl;
using namespace csl::problem;
using namespace csl::registry;

namespace {
template<class T, class... R>
T take(std::variant<T, R...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("unexpected diagnostic or unsupported result");
    return std::get<T>(std::move(value));
}

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

sets::SetData interval_data(double lower, double upper, std::string id) {
    const auto h = take(numeric::snapshot(Matrix{2, 1, {1, -1}}));
    const auto bounds = take(numeric::snapshot_vector(Vector{upper, -lower}));
    const auto equalities = take(numeric::snapshot(Matrix{0, 1, {}}));
    const auto values = take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{std::move(id)}, 1, {"u"}},
        {h, bounds, equalities, values}));
}

SetHandle interval(double lower, double upper, std::string id) {
    return interval_data(lower, upper, std::move(id)).as_handle();
}

Problem original_problem() {
    const auto controls = interval(-1, 1, "ext03-control");
    auto model = std::make_shared<const SystemModel>(SystemModel{{
        {1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}});
    return {{"ext03-temporal-lift-measurement"}, std::move(model), {0, 1, 2},
        KnownInitial{{0}}, ContinuousDomain{{controls, controls}},
        {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{1}, 0}};
}

SlewMemoryRequest slew_request() {
    return {RateLimitedFirstAction{{0.25}, interval(-0.25, 0.25, "ext03-first-rate")},
        {interval(-0.25, 0.25, "ext03-later-rate")}};
}

template<class Port>
PreparedProvider<Port> selected(Registration<Port> entry, std::string representation) {
    Registry<Port> registry;
    const Method method{entry.identity.id, entry.identity.version};
    require(!registry.add(std::move(entry)), "subprovider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)));
}

bool contains(const sets::SetData& set, const Vector& point) {
    const auto h = std::get<sets::HRepresentation>(set.representation());
    if (point.size() != h.equalities.cols()) return false;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        double lhs = 0;
        for (std::size_t col = 0; col < point.size(); ++col)
            lhs += h.inequalities(row, col) * point[col];
        if (lhs > h.upper_bounds[row] + 1e-10) return false;
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        double lhs = 0;
        for (std::size_t col = 0; col < point.size(); ++col)
            lhs += h.equalities(row, col) * point[col];
        if (std::abs(lhs - h.equality_values[row]) > 1e-10) return false;
    }
    return true;
}

void check_original_history(const ControlHistory& history) {
    require(history.states == std::vector<Vector>{{0}, {0}, {-0.25}},
        "recovered physical states differ from the analytic optimizer");
    require(history.controls == std::vector<Vector>{{0}, {-0.25}},
        "recovered controls differ from the analytic optimizer");
    require(history.controls[0][0] >= -1 && history.controls[0][0] <= 1 &&
        history.controls[1][0] >= -1 && history.controls[1][0] <= 1,
        "recovered controls violate absolute bounds");
    require(std::abs(history.states[1][0] - history.states[0][0] - history.controls[0][0]) <= 1e-12 &&
        std::abs(history.states[2][0] - history.states[1][0] - history.controls[1][0]) <= 1e-12,
        "recovered history violates original dynamics");
    require(std::abs(history.controls[0][0] - 0.25) <= 0.25 + 1e-12 &&
        std::abs(history.controls[1][0] - history.controls[0][0]) <= 0.25 + 1e-12,
        "recovered history violates the slew constraints");
    require(history.states.back()[0] == -0.25,
        "recovered terminal objective differs from the analytic optimum");
}

void one_run() {
    const auto original = original_problem();
    const auto request = slew_request();
    auto lifted_result = lift_one_step_slew(original, request);
    const auto lifted = take(std::move(lifted_result));
    require(lifted.coordinates.original == JointCoordinates{{1, 1, 0}, 2},
        "original coordinate identity differs");
    require(lifted.coordinates.lifted == JointCoordinates{{2, 1, 0}, 2},
        "lifted coordinate identity differs");

    auto resolved = take(problem::resolve(lifted.problem,
        {UncertaintyStructure::stage_product_uncoupled, {}, {}}));
    FamilyRequest family;
    family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    family.objective = resolved.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};

    auto lp_registration = take(adapters::lp::make_highs_registration());
    auto convex_registration = take(adapters::convex::make_highs_registration());
    auto converter_registration = take(adapters::polyhedral::make_qhull_registration(lp_registration));
    auto projection_registration = geometry::polyhedral::make_projection_registration();
    auto hull_provider = selected(geometry::make_lp_hull_reducer_registration(), "");
    auto affine_lp_provider = selected(lp_registration, "csl.program-result.v1");
    auto affine_converter_provider = selected(converter_registration, "csl.polyhedron.v");
    auto affine_registration = geometry::make_affine_sum_registration({
        std::move(hull_provider), std::move(affine_lp_provider), std::move(affine_converter_provider)});

    Registry<GeometryPort> projections, affines;
    Registry<ConversionPort> conversions;
    Registry<LPPort> lp;
    Registry<ConvexPort> convex;
    const Method projection_method{projection_registration.identity.id, projection_registration.identity.version};
    const Method affine_method{affine_registration.identity.id, affine_registration.identity.version};
    const Method converter_method{converter_registration.identity.id, converter_registration.identity.version};
    const Method lp_method{lp_registration.identity.id, lp_registration.identity.version};
    const Method convex_method{convex_registration.identity.id, convex_registration.identity.version};
    require(!projections.add(std::move(projection_registration)), "projection provider registration failed");
    require(!affines.add(std::move(affine_registration)), "affine provider registration failed");
    require(!conversions.add(std::move(converter_registration)), "conversion provider registration failed");
    require(!lp.add(std::move(lp_registration)), "LP provider registration failed");
    require(!convex.add(std::move(convex_registration)), "convex provider registration failed");

    Requirements h_output, v_output, program;
    h_output.output.representation = {"csl.polyhedron.h"};
    h_output.output.relation = SetRelation::equivalent;
    v_output.output.representation = {"csl.polyhedron.v"};
    v_output.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(check_providers(
        select_provider(projections, projection_method, h_output),
        select_provider(affines, affine_method, v_output),
        select_provider(conversions, converter_method, h_output),
        select_provider(lp, lp_method, program), select_provider(convex, convex_method, program)));
    StrategyRegistry strategies;
    require(!strategies.add(synthesis::strategy_a::make_registration(std::move(providers))),
        "Strategy A registration failed");

    StrategyConfiguration configuration;
    configuration.strategy = {"csl.synthesis.reach-back"};
    configuration.representation = family.representation;
    StrategyRequest strategy_request{std::move(resolved), configuration, family, "1"};
    Requirements output;
    output.output.representation = family.representation;
    output.output.family = family.target;
    output.output.completeness = Completeness::established;
    auto prepared = take(strategies.prepare(strategy_request, output));
    auto workspace = prepared.create();
    ExecutionContext context;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    auto result = take(workspace->run(context));
    require(result.termination == Termination::completed, "Strategy A did not complete");
    require(result.outcome.value == MathematicalOutcome::optimal, "Strategy A did not return optimal");
    require(result.family && result.family->registry_verified(), "complete family was not registry verified");
    const auto& complete = std::get<CompleteOptimalFamily>(result.family->outcome());
    require(complete.relation.coordinates == JointCoordinates{{2, 1, 0}, 2},
        "verified family coordinates differ");
    require(result.objective.lower && result.objective.upper &&
        result.objective.lower->value == -0.25 && result.objective.upper->value == -0.25,
        "exact dyadic objective bounds differ from the analytic optimum");
    require(static_cast<bool>(complete.relation.payload), "verified family relation is missing");
    const auto* relation = complete.relation.payload->h_relation_for_recording();
    require(relation && contains(*relation, {0, 0.25, 0, 0, -0.25, -0.25, -0.25, -0.25}),
        "verified relation omits the analytic optimal history");

    const LiftedControlHistory auxiliary{{{0, 0.25}, {0, 0}, {-0.25, -0.25}}, {{-0.25}, {-0.25}}};
    const auto recovered = take(recover_history(lifted.coordinates, auxiliary, 0, 0));
    check_original_history(recovered);
}

std::uint64_t positive_count(const char* text) {
    const auto parsed = std::stoull(text);
    if (parsed == 0) throw std::invalid_argument("counts must be positive");
    return parsed;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 4)
            throw std::invalid_argument("usage: csl_ext03_temporal_lift_report BATCH WARMUPS REPETITIONS");
        const auto batch = positive_count(argv[1]);
        const auto warmups = positive_count(argv[2]);
        const auto repetitions = positive_count(argv[3]);
        std::cout << "{\"event\":\"header\",\"schema\":\"csl.ext03-strategy-a-measurement/1\",\"batch\":"
                  << batch << ",\"warmups\":" << warmups << ",\"repetitions\":" << repetitions << "}\n";
        for (std::uint64_t round = 0; round < warmups + repetitions; ++round) {
            const auto start = std::chrono::steady_clock::now();
            for (std::uint64_t call = 0; call < batch; ++call) one_run();
            const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - start).count();
            std::cout << "{\"event\":\"trial\",\"fixture\":\"two_step_slew_integrator\",\"round\":"
                      << round << ",\"warmup\":" << (round < warmups ? "true" : "false")
                      << ",\"batch\":" << batch << ",\"elapsed_ns\":" << elapsed
                      << ",\"checked_calls\":" << batch << ",\"failures\":0,\"status\":\"passed\"}\n";
            if (elapsed <= 0) throw std::runtime_error("nonpositive measured interval");
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
