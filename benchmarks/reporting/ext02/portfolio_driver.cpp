#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/synthesis/finite_mixed_branch.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

using namespace csl;
using namespace csl::synthesis;

namespace {
template<class T, class Error>
T take(std::variant<T, Error> result, const char* operation) {
    if constexpr (std::is_same_v<Error, Diagnostic>) {
        if (const auto* error = std::get_if<Diagnostic>(&result))
            throw std::runtime_error(std::string(operation) + ": " + error->field + ": " + error->explanation);
    } else if constexpr (std::is_same_v<Error, Diagnostics>) {
        if (const auto* errors = std::get_if<Diagnostics>(&result); errors && !errors->empty())
            throw std::runtime_error(std::string(operation) + ": " + errors->front().field + ": " +
                                     errors->front().explanation);
    }
    if (!std::holds_alternative<T>(result))
        throw std::runtime_error(std::string(operation) + " returned a diagnostic");
    return std::get<T>(std::move(result));
}

numeric::MatrixView matrix(Matrix value) {
    return take(numeric::snapshot(value), "matrix snapshot");
}
numeric::VectorView vector(Vector value) {
    return take(numeric::snapshot_vector(value), "vector snapshot");
}
SetHandle h_set(std::string id, std::size_t dimension, Matrix inequalities, Vector upper,
                Matrix equalities, Vector equalities_rhs) {
    auto result = sets::make_h({{std::move(id)}, dimension, {}},
        {matrix(std::move(inequalities)), vector(std::move(upper)),
         matrix(std::move(equalities)), vector(std::move(equalities_rhs))});
    if (const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error("H set: " + error->field + ": " + error->explanation);
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

template<class Port>
registry::PreparedProvider<Port> selected(registry::Registration<Port> registration,
                                            std::string representation) {
    registry::Registry<Port> providers;
    const registry::Method method{registration.identity.id, registration.identity.version};
    if (auto errors = providers.add(std::move(registration)))
        throw std::runtime_error("provider registration failed: " + errors->diagnostics.front().explanation);
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
                  std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    auto prepared = registry::prepare_provider(registry::select_provider(providers, method, requirements));
    if (const auto* rejection = std::get_if<registry::Rejection>(&prepared))
        throw std::runtime_error("provider selection failed: " + rejection->diagnostics.front().explanation);
    return std::get<registry::PreparedProvider<Port>>(std::move(prepared));
}

struct StrategyFixture {
    registry::Registry<registry::GeometryPort> projections, affines;
    registry::Registry<registry::ConversionPort> conversions;
    registry::Registry<registry::LPPort> lps;
    registry::Registry<registry::ConvexPort> convexes;
    registry::StrategyRegistry strategies;

    StrategyFixture() {
        auto lp = take(adapters::lp::make_highs_registration(), "HiGHS LP registration");
        auto convex = take(adapters::convex::make_highs_registration(), "HiGHS convex registration");
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "Qhull registration");
        auto projection = geometry::polyhedral::make_projection_registration();
        auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
        const registry::Method pm{projection.identity.id, projection.identity.version};
        const registry::Method am{affine.identity.id, affine.identity.version};
        const registry::Method cm{converter.identity.id, converter.identity.version};
        const registry::Method lm{lp.identity.id, lp.identity.version};
        const registry::Method qm{convex.identity.id, convex.identity.version};
        if (auto e = projections.add(projection)) throw std::runtime_error(e->diagnostics.front().explanation);
        if (auto e = affines.add(affine)) throw std::runtime_error(e->diagnostics.front().explanation);
        if (auto e = conversions.add(converter)) throw std::runtime_error(e->diagnostics.front().explanation);
        if (auto e = lps.add(lp)) throw std::runtime_error(e->diagnostics.front().explanation);
        if (auto e = convexes.add(convex)) throw std::runtime_error(e->diagnostics.front().explanation);
        registry::Requirements h, v, program;
        h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
        v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
        program.output.representation = {"csl.program-result.v1"};
        auto providers = registry::check_providers(
            registry::select_provider(projections, pm, h), registry::select_provider(affines, am, v),
            registry::select_provider(conversions, cm, h), registry::select_provider(lps, lm, program),
            registry::select_provider(convexes, qm, program));
        using Providers = registry::CheckedProviders<registry::GeometryPort, registry::GeometryPort,
            registry::ConversionPort, registry::LPPort, registry::ConvexPort>;
        if (!std::holds_alternative<Providers>(providers))
            throw std::runtime_error("strategy provider composition failed");
        auto registration = strategy_a::make_registration(
            std::get<Providers>(std::move(providers)));
        if (auto errors = strategies.add(std::move(registration)))
            throw std::runtime_error("strategy registration failed: " + errors->diagnostics.front().explanation);
    }
};

problem::ResolvedProblem scenario() {
    auto continuous = h_set("ext02-continuous-action", 1,
        {2, 1, {1, -1}}, {1, 1}, {0, 1, {}}, {});
    auto initial = h_set("ext02-initial", 2,
        {0, 2, {}}, {}, {2, 2, {1, 0, 0, 1}}, {0, 0});
    auto terminal = h_set("ext02-terminal-halfspace", 2,
        {1, 2, {-1, 0}}, {0}, {0, 2, {}}, {});
    auto model = std::make_shared<const SystemModel>(SystemModel{{
        {2, 2, 0}, TimeDomain::discrete,
        LinearStage{{2, 2, {0, 0, 0, 0}}, {2, 2, {1, 1, 0, 1}},
                     {2, 0, {}}, {0, 0}}}, {}});
    Problem source{{"ext02-two-state-mixed-analytic-v1"}, std::move(model), {0, 1},
        KnownInitial{{0, 0}},
        MixedDomain{ContinuousDomain{{continuous}}, FiniteDomain{1, {{-1}, {0}, {1}}}},
        {initial, terminal}, {}, {}, InformationPattern::nominal_open_loop,
        LinearTerminal{{1, 0}, 0}};
    auto resolved = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    if (const auto* error = std::get_if<Diagnostic>(&resolved))
        throw std::runtime_error("scenario resolution: " + error->field + ": " + error->explanation);
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}

void validate(const FiniteMixedBranchSolveResult& result) {
    if (!result.history_enumeration_complete || !result.every_branch_solved || !result.portfolio.complete ||
        result.portfolio.evaluations.size() != 3 || !result.portfolio.optimum ||
        *result.portfolio.optimum != 0.0 || result.portfolio.optimal_evaluation_indices.size() != 3 ||
        !result.portfolio.all_selected_relations_present || result.stop)
        throw std::runtime_error("portfolio differs from the three-branch analytic oracle");
    for (std::size_t index = 0; index < 3; ++index) {
        const auto& evaluation = result.portfolio.evaluations[index];
        if (evaluation.objective != 0.0 || !evaluation.verified_continuous_family ||
            !evaluation.verified_continuous_family->registry_verified() || !evaluation.source_relation)
            throw std::runtime_error("branch result failed family/objective evidence checks");
        const auto* branch = std::get_if<FiniteMixedBranchProblem>(&evaluation.branch);
        if (!branch || branch->history.catalogue_indices != std::vector<std::size_t>{index})
            throw std::runtime_error("branch catalogue identity mismatch");
        const auto representation = evaluation.source_relation->representation();
        const auto* h = std::get_if<sets::HRepresentation>(&representation);
        if (!h) throw std::runtime_error("source relation is not H-represented");
        const double discrete = static_cast<double>(index) - 1.0;
        const Vector analytic_point{0, 0, 0, discrete, -discrete, discrete};
        if (h->inequalities.cols() != analytic_point.size() ||
            h->equalities.cols() != analytic_point.size())
            throw std::runtime_error("source relation has an unexpected joint-coordinate dimension");
        for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
            double lhs = 0;
            for (std::size_t column = 0; column < analytic_point.size(); ++column)
                lhs += h->inequalities(row, column) * analytic_point[column];
            if (lhs > h->upper_bounds[row] + 1e-10)
                throw std::runtime_error("source relation excludes the analytic optimal history");
        }
        for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
            double lhs = 0;
            for (std::size_t column = 0; column < analytic_point.size(); ++column)
                lhs += h->equalities(row, column) * analytic_point[column];
            if (std::abs(lhs - h->equality_values[row]) > 1e-10)
                throw std::runtime_error("source relation excludes the exact analytic optimal history");
        }
    }
}

void run(std::size_t repetitions, bool smoke) {
    const auto source = scenario();
    StrategyFixture fixture;
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"csl.synthesis.reach-back"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 2;
    request.limits.max_branch_evaluations = 3;
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});

    const std::size_t calls = smoke ? 1 : repetitions + 1;
    for (std::size_t trial = 0; trial < calls; ++trial) {
        const auto begin = std::chrono::steady_clock::now();
        auto outcome = solve_finite_mixed_branch_portfolio(source, fixture.strategies, request, context);
        const auto end = std::chrono::steady_clock::now();
        if (!std::holds_alternative<FiniteMixedBranchSolveResult>(outcome))
            throw std::runtime_error("portfolio solver rejected the analytic profile");
        const auto& result = std::get<FiniteMixedBranchSolveResult>(outcome);
        validate(result);
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
        if (result.retained_relation_scalars >
            std::numeric_limits<std::size_t>::max() / sizeof(double))
            throw std::runtime_error("relation byte count overflows size_t");
        const auto retained_numeric_bytes = result.retained_relation_scalars * sizeof(double);
        const bool warmup = !smoke && trial == 0;
        std::cout << "{\"schema\":\"csl.ext02-portfolio-trial/1\",\"trial\":" << trial
                  << ",\"warmup\":" << (warmup ? "true" : "false")
                  << ",\"elapsed_ns\":" << elapsed << ",\"horizon\":1,\"catalogue_size\":3"
                  << ",\"history_count\":" << result.portfolio.evaluations.size()
                  << ",\"retained_relation_rows\":" << result.retained_relation_rows
                  << ",\"retained_relation_scalars\":" << result.retained_relation_scalars
                  << ",\"retained_numeric_bytes\":" << retained_numeric_bytes
                  << ",\"status\":\"complete\",\"optimum\":0,\"branches\":[";
        for (std::size_t index = 0; index < result.portfolio.evaluations.size(); ++index) {
            if (index) std::cout << ',';
            const auto& evaluation = result.portfolio.evaluations[index];
            const auto& branch = std::get<FiniteMixedBranchProblem>(evaluation.branch);
            std::cout << "{\"catalogue_index\":" << branch.history.catalogue_indices.front()
                      << ",\"discrete_value\":" << branch.coordinates.discrete_controls.front().front()
                      << ",\"objective\":" << *evaluation.objective
                      << ",\"complete_family_verified\":"
                      << (evaluation.verified_continuous_family->registry_verified() ? "true" : "false")
                      << '}';
        }
        std::cout << "]}\n";
    }
}
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--smoke") run(0, true);
        else if (argc == 3 && std::string(argv[1]) == "--measure")
            run(static_cast<std::size_t>(std::stoull(argv[2])), false);
        else throw std::runtime_error("usage: csl_ext02_portfolio_report --smoke | --measure N");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
