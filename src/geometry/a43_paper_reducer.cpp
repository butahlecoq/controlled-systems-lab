#include <csl/geometry/hull_reducer.hpp>
#include <csl/optimization/phase_one.hpp>
#include "hull/reducer_internal.hpp"
#include "exact_convex_combination.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <string>

namespace csl::geometry {
namespace {

struct BasisCertificate {
    std::vector<ConvexCombination> terms;
    ProgramIdentity program;
};
struct CertifiedRemoval { std::size_t point; BasisCertificate certificate; };

std::optional<BasisCertificate> certificate_from_basis(const PointCloud& cloud,
        std::size_t candidate, const std::vector<std::optional<std::size_t>>& basis_points,
        const BasisSnapshot& basis, const BasisDiagnostics& view,
        const std::optional<SolveAttempt>& attempt) {
    Vector rhs = cloud.points[candidate];
    rhs.push_back(1.0);
    auto coordinates_result = view.coordinates(basis.reference, rhs);
    if (!std::holds_alternative<BasisCoordinates>(coordinates_result)) return {};
    const auto& coordinates = std::get<BasisCoordinates>(coordinates_result);
    if (!(coordinates.reference == basis.reference) || coordinates.values.size() != basis_points.size() ||
        !optimization::check_basis_coordinates(coordinates, basis, attempt).empty()) return {};

    std::vector<ConvexCombination> terms;
    terms.reserve(basis_points.size());
    for (std::size_t i = 0; i < basis_points.size(); ++i) {
        const auto weight = coordinates.values[i];
        if (!std::isfinite(weight) || weight < 0.0) return {};
        if (basis_points[i]) {
            if (weight != 0.0) terms.push_back({*basis_points[i], weight});
        } else if (weight != 0.0) {
            return {};
        }
    }
    if (!detail::exact_convex_combination(cloud, candidate, terms)) return {};
    return BasisCertificate{std::move(terms), basis.reference.solve.program().identity()};
}

std::optional<LinearProgram> candidate_program(const PointCloud& cloud,
        const std::vector<std::size_t>& retained, std::size_t candidate,
        optimization::phase_one::Options& options) {
    const auto dimension = cloud.points[candidate].size();
    std::vector<std::size_t> columns;
    columns.reserve(retained.size() - 1);
    for (const auto id : retained) if (id != candidate) columns.push_back(id);
    if (columns.empty() || dimension > std::numeric_limits<std::size_t>::max() - 2 ||
        dimension + 1 > std::numeric_limits<std::size_t>::max() / columns.size()) return {};

    SparseMatrix matrix{dimension + 1, columns.size(), {}, {}, {}};
    matrix.row_offsets.reserve(dimension + 2);
    matrix.column_indices.reserve((dimension + 1) * columns.size());
    matrix.values.reserve((dimension + 1) * columns.size());
    matrix.row_offsets.push_back(0);
    std::vector<long double> norms(columns.size(), 1.0L);
    long double maximum_norm = 1.0L;
    for (std::size_t column = 0; column < columns.size(); ++column) {
        for (std::size_t row = 0; row < dimension; ++row)
            norms[column] = std::hypot(norms[column],
                static_cast<long double>(cloud.points[columns[column]][row]));
        maximum_norm = std::max(maximum_norm, norms[column]);
    }
    for (std::size_t row = 0; row < dimension; ++row) {
        for (std::size_t column = 0; column < columns.size(); ++column) {
            matrix.column_indices.push_back(column);
            matrix.values.push_back(cloud.points[columns[column]][row]);
        }
        matrix.row_offsets.push_back(matrix.values.size());
    }
    for (std::size_t column = 0; column < columns.size(); ++column) {
        matrix.column_indices.push_back(column);
        matrix.values.push_back(1.0);
        options.structural_entering_priorities.push_back(static_cast<double>(norms[column] / maximum_norm));
    }
    matrix.row_offsets.push_back(matrix.values.size());

    Vector rhs = cloud.points[candidate];
    rhs.push_back(1.0);
    auto program = optimization::phase_one::make_program(
        {cloud.problem, {"itis17-a43-candidate-" + std::to_string(candidate)}}, matrix, rhs);
    if (const auto* accepted = std::get_if<LinearProgram>(&program)) return *accepted;
    return {};
}

std::vector<CertifiedRemoval> solve_candidate(const PointCloud& cloud,
        const std::vector<std::size_t>& retained, std::size_t candidate,
        const ExecutionContext& context, A43PivotRule pivot_rule,
        A43PaperMetrics& metrics, MembershipOutcome& outcome) {
    optimization::phase_one::Options options;
    auto program = candidate_program(cloud, retained, candidate, options);
    if (!program) {
        outcome = MembershipOutcome::unsupported;
        return {};
    }
    if (pivot_rule == A43PivotRule::phase_one_order) options.structural_entering_priorities.clear();
    auto provider_result = optimization::phase_one::make_registration(std::move(options));
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(provider_result)) {
        outcome = MembershipOutcome::unsupported;
        return {};
    }
    auto provider = std::get<registry::Registration<registry::LPPort>>(std::move(provider_result));
    const registry::Method method{provider.identity.id, provider.identity.version};
    registry::Registry<registry::LPPort> providers;
    if (providers.add(std::move(provider))) {
        outcome = MembershipOutcome::unsupported;
        return {};
    }
    registry::Requirements requirements;
    requirements.output = {{{"csl.program-result.v1"}}, Assurance::numerical, {}, {}, {}};
    requirements.basis_diagnostics = true;
    auto selected = registry::select(providers, method, *program, requirements);
    auto prepared = registry::prepare_pipeline(std::move(selected));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::LPPort>>(prepared)) {
        outcome = MembershipOutcome::unsupported;
        return {};
    }
    auto workspaces = std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(prepared)).create();
    auto& phase = *std::get<0>(workspaces);
    ++metrics.candidate_solves;
    const auto result = phase.solve_dependency(*program, context);
    const auto* view = dynamic_cast<const optimization::phase_one::DiagnosticsView*>(phase.basis());
    if (!view || !std::holds_alternative<ProgramResult>(result)) {
        outcome = MembershipOutcome::numerical_failure;
        return {};
    }
    const auto snapshot_result = view->phase_one_snapshot();
    if (!std::holds_alternative<optimization::phase_one::Snapshot>(snapshot_result)) {
        outcome = MembershipOutcome::numerical_failure;
        return {};
    }
    const auto& snapshot = std::get<optimization::phase_one::Snapshot>(snapshot_result);
    metrics.phase_one_pivots += snapshot.pivots;
    metrics.largest_norm_tie_breaks += snapshot.entering_tie_breaks;
    if (snapshot.reason == optimization::phase_one::Reason::positive_auxiliary_optimum) {
        outcome = MembershipOutcome::infeasible;
        return {};
    }
    if (snapshot.reason != optimization::phase_one::Reason::feasible ||
        snapshot.termination != Termination::completed) {
        outcome = MembershipOutcome::stopped;
        return {};
    }
    const auto& basis_result = view->snapshot();
    if (!std::holds_alternative<BasisSnapshot>(basis_result)) {
        outcome = MembershipOutcome::numerical_failure;
        return {};
    }
    const auto& basis = std::get<BasisSnapshot>(basis_result);
    if (!optimization::check_basis_snapshot(basis, phase.last_attempt()).empty() ||
        basis.columns.size() != cloud.points[candidate].size() + 1) {
        outcome = MembershipOutcome::numerical_failure;
        return {};
    }
    std::vector<std::optional<std::size_t>> basis_points;
    basis_points.reserve(basis.columns.size());
    const std::vector<std::size_t> columns = [&] {
        std::vector<std::size_t> ids;
        for (const auto id : retained) if (id != candidate) ids.push_back(id);
        return ids;
    }();
    for (const auto& column : basis.columns) {
        if (const auto* structural = std::get_if<StructuralColumn>(&column)) {
            if (structural->index >= columns.size()) {
                outcome = MembershipOutcome::malformed_result;
                return {};
            }
            basis_points.push_back(columns[structural->index]);
        } else if (std::holds_alternative<AuxiliaryColumn>(column)) {
            basis_points.push_back({});
        } else {
            outcome = MembershipOutcome::malformed_result;
            return {};
        }
    }
    ++metrics.basis_coordinate_checks;
    auto certificate = certificate_from_basis(cloud, candidate, basis_points, basis, *view,
        phase.last_attempt());
    if (!certificate) {
        outcome = MembershipOutcome::numerical_failure;
        return {};
    }
    outcome = MembershipOutcome::feasible;
    std::vector<CertifiedRemoval> removals;
    removals.push_back({candidate, std::move(*certificate)});
    std::vector<unsigned char> basis_member(cloud.points.size(), 0);
    for (const auto id : basis_points) if (id) basis_member[*id] = 1;
    for (const auto point : retained) {
        if (point == candidate || basis_member[point]) continue;
        ++metrics.basis_coordinate_checks;
        auto additional = certificate_from_basis(cloud, point, basis_points, basis, *view,
            phase.last_attempt());
        if (additional) removals.push_back({point, std::move(*additional)});
    }
    if (removals.size() > 1) metrics.certified_batch_removals += removals.size() - 1;
    return removals;
}

class A43PaperWorkspace final : public HullReducerWorkspace {
public:
    explicit A43PaperWorkspace(A43PivotRule rule) : rule_(rule) {}
    HullReductionResult reduce(const PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        return reduce_itis17_a43_paper_hull(cloud, lp, context, rule_);
    }
private:
    A43PivotRule rule_;
};

} // namespace

HullReductionResult reduce_itis17_a43_paper_hull(const PointCloud& cloud, LPWorkspace& lp,
        const ExecutionContext& context, A43PivotRule pivot_rule) {
    if (cloud.points.empty()) return Diagnostics{{{DiagnosticCode::invalid_input,
        "hull.points", "A43 requires a nonempty point cloud"}}};
    const auto dimension = cloud.points.front().size();
    if (std::any_of(cloud.points.begin(), cloud.points.end(), [&](const Vector& point) {
            return point.size() != dimension || std::any_of(point.begin(), point.end(),
                [](double coordinate) { return !std::isfinite(coordinate); });
        })) return Diagnostics{{{DiagnosticCode::invalid_input, "hull.points",
            "A43 requires finite points with one common dimension"}}};

    std::vector<std::size_t> source_order(cloud.points.size());
    std::iota(source_order.begin(), source_order.end(), std::size_t{0});
    std::vector<unsigned char> removed_mask(cloud.points.size(), 0);
    std::vector<RemovalCertificate> removed;
    std::vector<MembershipAttempt> attempts;
    A43PaperMetrics metrics;
    metrics.largest_norm_tie_rule = pivot_rule == A43PivotRule::largest_norm_tie;
    bool incomplete = false;
    for (const auto candidate : source_order) {
        std::vector<std::size_t> retained;
        for (const auto id : source_order) if (!removed_mask[id]) retained.push_back(id);
        if (removed_mask[candidate] || retained.size() < 2) continue;
        MembershipOutcome outcome = MembershipOutcome::unsupported;
        auto certified = solve_candidate(cloud, retained, candidate, context, pivot_rule,
            metrics, outcome);
        attempts.push_back({candidate, outcome});
        if (outcome == MembershipOutcome::feasible && !certified.empty()) {
            for (std::size_t index = 0; index < certified.size(); ++index) {
                auto& item = certified[index];
                if (index > 0) attempts.push_back({item.point, MembershipOutcome::feasible});
                removed_mask[item.point] = 1;
                removed.push_back({item.point, std::move(item.certificate.terms), item.certificate.program,
                {context.numerical.absolute_tolerance, context.numerical.relative_tolerance, 0.0,
                 {metrics.largest_norm_tie_rule ? "itis17-a43-largest-norm-tie/exact-binary64-convex-combination" :
                    "itis17-a43-phase-one-order/exact-binary64-convex-combination"}}});
            }
            continue;
        }
        if (outcome != MembershipOutcome::infeasible) {
            incomplete = true;
            if (outcome == MembershipOutcome::stopped) break;
        }
    }

    std::vector<std::size_t> retained;
    for (const auto id : source_order) if (!removed_mask[id]) retained.push_back(id);
    auto final_result = detail::reduce_hull_in_order(cloud, lp, context, retained,
        std::move(removed), metrics.largest_norm_tie_rule ?
            "itis17-a43-largest-norm-final-recheck" : "itis17-a43-order-final-recheck");
    if (!std::holds_alternative<HullReduction>(final_result)) return final_result;
    auto reduction = std::get<HullReduction>(std::move(final_result));
    metrics.final_recheck_calls = reduction.lp_calls;
    reduction.attempts.insert(reduction.attempts.begin(), attempts.begin(), attempts.end());
    if (incomplete) reduction.status = ReductionStatus::incomplete;
    reduction.itis17_a43_paper = metrics;
    return reduction;
}

registry::Registration<registry::HullReducerPort>
make_itis17_a43_paper_hull_reducer_registration(A43PivotRule pivot_rule) {
    const bool largest_norm = pivot_rule == A43PivotRule::largest_norm_tie;
    const auto id = largest_norm ? "csl.hull.itis17.a43-largest-norm-tie" :
        "csl.hull.itis17.a43-artificial-basis";
    const auto version = "1.0.0";
    return {{{id}, version},
        [](const PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [pivot_rule](const PointCloud&) { return std::make_unique<A43PaperWorkspace>(pivot_rule); }};
}

} // namespace csl::geometry
