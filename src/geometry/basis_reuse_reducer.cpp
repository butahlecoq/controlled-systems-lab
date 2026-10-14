#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/optimization/phase_one.hpp>
#include "exact_convex_combination.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace csl::geometry {
namespace {

using namespace csl;

HullReductionResult fallback(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context, BasisReuseMetrics metrics) {
    metrics.fell_back_to_lp_baseline = true;
    auto result = reduce_hull(cloud, lp, context);
    if (auto* reduction = std::get_if<HullReduction>(&result)) reduction->basis_reuse = metrics;
    return result;
}

std::optional<LinearProgram> bulk_program(const PointCloud& cloud) {
    if (cloud.points.empty()) return {};
    const auto dimension = cloud.points.front().size();
    const auto rows = dimension + 1;
    if (rows > std::numeric_limits<std::size_t>::max() / cloud.points.size()) return {};
    SparseMatrix matrix{rows, cloud.points.size(), {}, {}, {}};
    matrix.row_offsets.reserve(rows + 1);
    matrix.column_indices.reserve(rows * cloud.points.size());
    matrix.values.reserve(rows * cloud.points.size());
    matrix.row_offsets.push_back(0);
    for (std::size_t r = 0; r < dimension; ++r) {
        for (std::size_t c = 0; c < cloud.points.size(); ++c) {
            matrix.column_indices.push_back(c);
            matrix.values.push_back(cloud.points[c][r]);
        }
        matrix.row_offsets.push_back(matrix.values.size());
    }
    for (std::size_t c = 0; c < cloud.points.size(); ++c) {
        matrix.column_indices.push_back(c);
        matrix.values.push_back(1.0);
    }
    matrix.row_offsets.push_back(matrix.values.size());
    Vector rhs(dimension + 1, 0.0);
    const long double weight_total = static_cast<long double>(cloud.points.size()) *
        (static_cast<long double>(cloud.points.size()) + 1.0L) / 2.0L;
    if (!std::isfinite(weight_total) || weight_total <= 0.0L) return {};
    for (std::size_t c = 0; c < cloud.points.size(); ++c) {
        const long double weight = static_cast<long double>(c + 1) / weight_total;
        for (std::size_t r = 0; r < dimension; ++r)
            rhs[r] += static_cast<double>(weight * static_cast<long double>(cloud.points[c][r]));
    }
    rhs.back() = 1.0;
    auto created = optimization::phase_one::make_program(
        {cloud.problem, {"hull-basis-bulk"}}, matrix, rhs);
    if (auto* program = std::get_if<LinearProgram>(&created)) return *program;
    return {};
}

class BasisReuseWorkspace final : public HullReducerWorkspace {
public:
    explicit BasisReuseWorkspace(registry::Registration<registry::LPPort> basis_provider)
        : basis_provider_(std::move(basis_provider)) {}

    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        BasisReuseMetrics metrics{};
        if (cloud.problem.value.empty() || cloud.points.size() < 2)
            return fallback(cloud, lp, context, metrics);
        const std::size_t dimension = cloud.points.front().size();
        if (std::any_of(cloud.points.begin(), cloud.points.end(), [&](const Vector& point) {
                return point.size() != dimension || std::any_of(point.begin(), point.end(),
                    [](double x) { return !std::isfinite(x); });
            })) return fallback(cloud, lp, context, metrics);

        auto program = bulk_program(cloud);
        if (!program) return fallback(cloud, lp, context, metrics);

        registry::Registry<registry::LPPort> providers;
        if (providers.add(basis_provider_))
            return fallback(cloud, lp, context, metrics);

        registry::Requirements requirements;
        requirements.output = {{{"csl.program-result.v1"}}, Assurance::numerical, {}, {}, {}};
        requirements.basis_diagnostics = true;
        auto prepared_result = registry::prepare_pipeline(registry::select(providers,
            registry::Method{basis_provider_.identity.id, basis_provider_.identity.version}, *program, requirements));
        using Pipeline = registry::PreparedPipeline<registry::LPPort>;
        if (!std::holds_alternative<Pipeline>(prepared_result))
            return fallback(cloud, lp, context, metrics);
        auto workspaces = std::get<Pipeline>(std::move(prepared_result)).create();
        auto& phase = *std::get<0>(workspaces);
        ++metrics.basis_solves;
        const auto phase_result = phase.solve_dependency(*program, context);
        const auto* view = dynamic_cast<const optimization::phase_one::DiagnosticsView*>(phase.basis());
        if (view) {
            const auto snapshot = view->phase_one_snapshot();
            if (const auto* report = std::get_if<optimization::phase_one::Snapshot>(&snapshot)) {
                metrics.pivots = report->pivots;
                metrics.degenerate_pivots = report->degenerate_pivots;
            }
        }
        if (!view || !std::holds_alternative<ProgramResult>(phase_result))
            return fallback(cloud, lp, context, metrics);
        const auto& solved = std::get<ProgramResult>(phase_result);
        if (solved.termination != Termination::completed ||
            solved.outcome.value != MathematicalOutcome::optimal || !solved.primal)
            return fallback(cloud, lp, context, metrics);

        auto basis_result = view->snapshot();
        if (!std::holds_alternative<BasisSnapshot>(basis_result))
            return fallback(cloud, lp, context, metrics);
        const auto& basis = std::get<BasisSnapshot>(basis_result);
        if (!optimization::check_basis_snapshot(basis, phase.last_attempt()).empty() ||
            basis.columns.size() != dimension + 1)
            return fallback(cloud, lp, context, metrics);

        std::vector<std::optional<std::size_t>> basis_points;
        basis_points.reserve(basis.columns.size());
        std::vector<unsigned char> is_basis(cloud.points.size(), 0);
        for (const auto& column : basis.columns) {
            const auto* structural = std::get_if<StructuralColumn>(&column);
            if (structural) {
                if (structural->index >= cloud.points.size() || is_basis[structural->index])
                    return fallback(cloud, lp, context, metrics);
                basis_points.push_back(structural->index);
                is_basis[structural->index] = 1;
            } else if (std::holds_alternative<AuxiliaryColumn>(column)) {
                basis_points.push_back(std::nullopt);
            } else {
                return fallback(cloud, lp, context, metrics);
            }
        }

        HullReduction reduction{ReductionStatus::complete, {}, {}, 0, {}, metrics};
        std::vector<unsigned char> removed(cloud.points.size(), 0);
        for (std::size_t candidate = 0; candidate < cloud.points.size(); ++candidate) {
            if (is_basis[candidate]) continue; // retained for the final hull; never silently skipped
            ++metrics.bulk_candidates;
            Vector rhs = cloud.points[candidate];
            rhs.push_back(1.0);
            auto coordinates_result = view->coordinates(basis.reference, rhs);
            if (!std::holds_alternative<BasisCoordinates>(coordinates_result)) continue;
            const auto& coordinates = std::get<BasisCoordinates>(coordinates_result);
            if (!(coordinates.reference == basis.reference) || coordinates.values.size() != basis_points.size() ||
                !optimization::check_basis_coordinates(coordinates, basis, phase.last_attempt()).empty()) continue;

            std::vector<ConvexCombination> terms;
            terms.reserve(basis_points.size());
            bool zero_artificial = true;
            for (std::size_t i = 0; i < basis_points.size(); ++i) {
                if (basis_points[i]) {
                    if (coordinates.values[i] != 0.0)
                        terms.push_back({*basis_points[i], coordinates.values[i]});
                } else if (coordinates.values[i] != 0.0) {
                    zero_artificial = false;
                    break;
                }
            }
            if (!zero_artificial) continue;
            if (!detail::exact_convex_combination(cloud, candidate, terms)) continue;

            double residual = 0.0;
            double weight_sum = 0.0;
            for (const auto& term : terms) {
                weight_sum += term.weight;
            }
            residual = std::max(residual, std::abs(weight_sum - 1.0));
            for (std::size_t r = 0; r < dimension; ++r) {
                double value = 0.0;
                for (const auto& term : terms) value += term.weight * cloud.points[term.point][r];
                residual = std::max(residual, std::abs(value - cloud.points[candidate][r]));
            }
            reduction.removed.push_back({candidate, std::move(terms), program->identity(),
                {context.numerical.absolute_tolerance, context.numerical.relative_tolerance,
                 residual, {"phase-one-basis-coordinate-reuse/exact-binary64-convex-combination"}}});
            removed[candidate] = 1;
            ++metrics.bulk_removals;
        }

        for (std::size_t i = 0; i < cloud.points.size(); ++i)
            if (!removed[i]) reduction.retained.push_back(i);
        reduction.basis_reuse = metrics;
        return reduction;
    }
private:
    registry::Registration<registry::LPPort> basis_provider_;
};

} // namespace

HullReductionResult reduce_hull_basis_reuse(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context) {
    auto provider = optimization::phase_one::make_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(provider))
        return fallback(cloud, lp, context, {});
    BasisReuseWorkspace workspace(std::get<registry::Registration<registry::LPPort>>(std::move(provider)));
    return workspace.reduce(cloud, lp, context);
}

registry::Registration<registry::HullReducerPort> make_basis_reuse_hull_reducer_registration() {
    auto provider_result = optimization::phase_one::make_registration();
    return make_basis_reuse_hull_reducer_registration(
        std::get<registry::Registration<registry::LPPort>>(std::move(provider_result)));
}

registry::Registration<registry::HullReducerPort> make_basis_reuse_hull_reducer_registration(
        registry::Registration<registry::LPPort> basis_provider) {
    auto factory_provider = basis_provider;
    return {{{"csl.hull.phase-one-basis-bulk"}, "1.0.0"},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [factory_provider = std::move(factory_provider)](const PointCloud&) {
            return std::make_unique<BasisReuseWorkspace>(factory_provider);
        }};
}

} // namespace csl::geometry
