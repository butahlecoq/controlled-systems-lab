#include <csl/synthesis/hybrid_path_program.hpp>

#include "hybrid_exact_model_relation.hpp"
#include "exact_h_polytope.hpp"
#include "hybrid_family_verifier_internal.hpp"

#include <algorithm>
#include <limits>
#include <optional>

namespace csl::synthesis {
namespace {
namespace hx = detail::exact_h;
using namespace model;

enum class RowsState { built, unsupported, cancelled };

RowsState append_rows(const sets::SetData& data, std::size_t variables,
    hx::Limits limits, std::vector<hx::Row>& rows, std::string& reason,
    std::stop_token cancellation) {
    if (cancellation.stop_requested()) return RowsState::cancelled;
    if (data.metadata()->set.dimension != variables) {
        reason = "Set dimension does not match the joint path relation";
        return RowsState::unsupported;
    }
    const auto inequality = [&](std::span<const double> coefficients, double bound) {
        return rows.size() < limits.max_rows && hx::append_inequality(
            coefficients, bound, false, limits.max_integer_bits, rows);
    };
    const auto equality = [&](std::span<const double> coefficients, double value) {
        return rows.size() <= limits.max_rows &&
            limits.max_rows - rows.size() >= 2 && hx::append_equality(
                coefficients, value, limits.max_integer_bits, rows);
    };
    const auto representation = data.representation();
    if (std::holds_alternative<sets::UniversalRepresentation>(representation))
        return RowsState::built;
    if (std::holds_alternative<sets::EmptyRepresentation>(representation)) {
        const std::vector<double> zero(variables, 0.0);
        if (inequality(zero, -1.0)) return RowsState::built;
        reason = "Empty set exceeds the exact relation row limit";
        return RowsState::unsupported;
    }
    if (const auto* singleton =
            std::get_if<sets::SingletonRepresentation>(&representation)) {
        if (singleton->point.size() != variables) {
            reason = "Singleton set has a malformed point dimension";
            return RowsState::unsupported;
        }
        std::vector<double> row(variables, 0.0);
        for (std::size_t column = 0; column < variables; ++column) {
            if (cancellation.stop_requested()) return RowsState::cancelled;
            row[column] = 1.0;
            const bool added = equality(row, singleton->point[column]);
            row[column] = 0.0;
            if (!added) {
                reason = "Singleton set exceeds exact row or integer limits";
                return RowsState::unsupported;
            }
        }
        return RowsState::built;
    }
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) {
        reason = "V-representations are outside the exact H-verifier domain";
        return RowsState::unsupported;
    }
    if (h->inequalities.cols() != variables ||
        h->upper_bounds.size() != h->inequalities.rows() ||
        h->equalities.cols() != variables ||
        h->equality_values.size() != h->equalities.rows()) {
        reason = "H-representation dimensions are malformed";
        return RowsState::unsupported;
    }
    std::vector<double> row(variables, 0.0);
    for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
        if (cancellation.stop_requested()) return RowsState::cancelled;
        for (std::size_t j = 0; j < variables; ++j) row[j] = h->inequalities(i, j);
        const bool added = inequality(row, h->upper_bounds[i]);
        std::fill(row.begin(), row.end(), 0.0);
        if (!added) {
            reason = "H inequalities exceed exact row or integer limits";
            return RowsState::unsupported;
        }
    }
    for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
        if (cancellation.stop_requested()) return RowsState::cancelled;
        for (std::size_t j = 0; j < variables; ++j) row[j] = h->equalities(i, j);
        const bool added = equality(row, h->equality_values[i]);
        std::fill(row.begin(), row.end(), 0.0);
        if (!added) {
            reason = "H equalities exceed exact row or integer limits";
            return RowsState::unsupported;
        }
    }
    return RowsState::built;
}

std::optional<LinearTerminal> path_objective(const HybridSystem& system,
    const HybridRequest& request, const HybridPath& path,
    const hx::RawRelationResult& raw) {
    const auto found = std::find_if(request.terminal_objectives.begin(),
        request.terminal_objectives.end(), [&](const auto& item) {
            return item.mode == path.modes.back();
        });
    if (found == request.terminal_objectives.end()) return {};
    const auto* linear = std::get_if<LinearTerminal>(&found->objective);
    const auto mode = std::find_if(system.modes.begin(), system.modes.end(),
        [&](const auto& item) { return item.id == path.modes.back(); });
    if (!linear || mode == system.modes.end() ||
        linear->coefficients.size() != mode->state_dimension ||
        mode->state_dimension > raw.variables)
        return {};
    const auto terminal_offset = raw.variables - mode->state_dimension;
    std::vector<double> objective(raw.variables, 0.0);
    std::copy(linear->coefficients.begin(), linear->coefficients.end(),
        objective.begin() + static_cast<std::ptrdiff_t>(terminal_offset));
    return LinearTerminal{std::move(objective), linear->offset};
}

bool append_optimum(std::vector<hx::Row>& rows,
    std::span<const double> objective, double offset,
    const hx::ExactRational& minimum, hx::Limits limits) {
    if (rows.size() > limits.max_rows || limits.max_rows - rows.size() < 2 ||
        minimum.denominator.negative || hx::exact_detail::is_zero(minimum.denominator))
        return false;
    hx::Row scaled_objective;
    int exponent = 0;
    if (!hx::make_row(objective, offset, false, limits.max_integer_bits,
                      scaled_objective, &exponent) ||
        exponent != minimum.binary_exponent)
        return false;
    hx::Row row;
    row.coefficients.reserve(objective.size());
    for (const auto& coefficient : scaled_objective.coefficients) {
        hx::Integer value;
        if (!hx::exact_detail::multiply(coefficient, minimum.denominator,
                                        limits.max_integer_bits, value))
            return false;
        row.coefficients.push_back(std::move(value));
    }
    hx::Integer offset_term;
    if (!hx::exact_detail::multiply(scaled_objective.bound, minimum.denominator,
                                    limits.max_integer_bits, offset_term))
        return false;
    row.bound = minimum.numerator;
    offset_term.negative = !hx::exact_detail::is_zero(offset_term) &&
                           !offset_term.negative;
    if (!hx::exact_detail::add(row.bound, offset_term,
                               limits.max_integer_bits))
        return false;
    hx::Row inverse = row;
    for (auto& coefficient : inverse.coefficients)
        coefficient.negative = !hx::exact_detail::is_zero(coefficient) &&
                               !coefficient.negative;
    inverse.bound.negative = !hx::exact_detail::is_zero(inverse.bound) &&
                             !inverse.bound.negative;
    rows.push_back(std::move(row));
    rows.push_back(std::move(inverse));
    return true;
}

hx::InclusionResult equal_rows(std::span<const hx::Row> lhs,
    std::span<const hx::Row> rhs, std::size_t variables, hx::Limits limits,
    std::stop_token cancellation) {
    const auto forward = hx::included_in(lhs, rhs, variables, limits, cancellation);
    if (forward.state != hx::InclusionState::included) return forward;
    return hx::included_in(rhs, lhs, variables, limits, cancellation);
}

bool make_point_rows(std::span<const double> point, std::size_t variables,
    hx::Limits limits, std::vector<hx::Row>& rows) {
    if (point.size() != variables || variables > limits.max_rows / 2)
        return false;
    std::vector<double> coordinate(variables, 0.0);
    for (std::size_t i = 0; i < variables; ++i) {
        coordinate[i] = 1.0;
        const bool added = hx::append_equality(coordinate, point[i],
            limits.max_integer_bits, rows);
        coordinate[i] = 0.0;
        if (!added) return false;
    }
    return true;
}

std::size_t saturated_product(std::size_t lhs, std::size_t rhs) {
    if (lhs != 0 && rhs > std::numeric_limits<std::size_t>::max() / lhs)
        return std::numeric_limits<std::size_t>::max();
    return lhs * rhs;
}
std::size_t saturated_increment(std::size_t value) {
    return value == std::numeric_limits<std::size_t>::max() ? value : value + 1;
}

} // namespace

HybridFamilyVerificationCapabilities ExactLinearHHybridFamilyVerifier::capabilities() const noexcept {
    return {true, true, true, Assurance::numerical};
}

HybridFamilyVerificationPreflightResult ExactLinearHHybridFamilyVerifier::preflight(
    const HybridSystem& system, const HybridRequest& request,
    std::span<const HybridPath> paths, std::stop_token cancellation) const {
    hx::Limits limits;
    constexpr HybridRelationLimits relation_limits{
        hx::default_max_variables, hx::default_max_rows,
        hx::default_max_variables * hx::default_max_rows};
    limits.max_variables = relation_limits.max_variables;
    limits.max_rows = relation_limits.max_rows;
    for (const auto& path : paths) {
        if (cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Exact linear H verifier preflight was cancelled between paths"};
        const auto raw = hx::reconstruct_path_relation(
            system, request, path, relation_limits, limits, cancellation);
        if (raw.state == hx::RawRelationState::cancelled)
            return OperationStopped{StopReason::cancelled, raw.reason};
        if (raw.state != hx::RawRelationState::built)
            return Diagnostics{{DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_domain",
                detail::describe_hybrid_path(path) + ": " + raw.reason}};
        if (raw.variables >= limits.max_variables ||
            raw.rows.size() > limits.max_rows -
                std::min<std::size_t>(2, limits.max_rows))
            return Diagnostics{{DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_limits",
                detail::describe_hybrid_path(path) +
                ": augmented objective relation exceeds exact limits"}};
        const auto objective = path_objective(system, request, path, raw);
        if (!objective)
            return Diagnostics{{DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_objective",
                detail::describe_hybrid_path(path) +
                ": exact H verification currently supports linear terminal objectives"}};
        hx::Row objective_row;
        if (!hx::make_row(objective->coefficients, objective->offset, false,
                          limits.max_integer_bits, objective_row))
            return Diagnostics{{DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_objective_limits",
                detail::describe_hybrid_path(path) +
                ": terminal objective exceeds exact integer limits"}};
    }
    return std::monostate{};
}

HybridFamilyVerificationResult ExactLinearHHybridFamilyVerifier::verify(
    const HybridSystem& system, const HybridRequest& request,
    std::span<const HybridPath> paths, std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,
    NumericalPolicy policy, std::stop_token cancellation) const {
    const auto cancelled = [] {
        return HybridFamilyVerificationResult{OperationStopped{
            StopReason::cancelled,
            "Exact linear H family verification was cancelled during independent analysis"}};
    };
    if (cancellation.stop_requested()) return cancelled();
    constexpr std::size_t max_visits = 1'000'000;
    auto visits = saturated_product(saturated_increment(paths.size()),
                                    saturated_increment(system.horizon));
    visits = saturated_product(visits, saturated_increment(system.edges.size()));
    visits = std::min(max_visits, saturated_product(visits, 64));
    const auto inventory = detail::independently_enumerate_paths(system, request,
        paths.size(), visits, [&] { return cancellation.stop_requested(); });
    if (cancellation.stop_requested() || inventory.cancelled) return cancelled();
    if (inventory.resource_limit || inventory.paths !=
        std::vector<HybridPath>(paths.begin(), paths.end()))
        return Diagnostics{{DiagnosticCode::evidence_mismatch,
            "hybrid.verification.exact_linear_h_paths",
            "Independent path enumeration disagrees with the admitted inventory"}};
    if (programs.size() != paths.size())
        return Diagnostics{{DiagnosticCode::evidence_mismatch,
            "hybrid.verification.exact_linear_h_programs",
            "Exact H verifier requires one program per enumerated path"}};

    struct Branch {
        LinearTerminal objective;
        hx::LinearMinimumResult minimum;
        hx::Limits limits;
        bool raw_built{};
        bool supported{};
        bool program_matches{};
        std::string reason;
    };
    std::vector<Branch> branches;
    branches.reserve(paths.size());
    std::optional<hx::ExactRational> best;
    bool unsupported_path = false;
    bool unbounded_path = false;
    for (std::size_t i = 0; i < paths.size(); ++i) {
        if (cancellation.stop_requested()) return cancelled();
        Branch branch;
        branch.limits.max_variables = std::min(hx::default_max_variables,
                                               programs[i].relation_limits.max_variables);
        branch.limits.max_rows = std::min(hx::default_max_rows,
                                          programs[i].relation_limits.max_rows);
        const auto per_path_phases = saturated_product(
            std::max<std::size_t>(paths.size(), 1), 6);
        branch.limits.max_operations = hx::default_max_operations / per_path_phases;
        branch.limits.max_generated_rows =
            hx::default_max_generated_rows / per_path_phases;
        auto raw = hx::reconstruct_path_relation(system, request, paths[i],
            programs[i].relation_limits, branch.limits, cancellation);
        if (raw.state == hx::RawRelationState::cancelled) return cancelled();
        if (raw.state != hx::RawRelationState::built) {
            branch.reason = raw.reason;
            unsupported_path = true;
            branches.push_back(std::move(branch));
            continue;
        }
        branch.raw_built = true;
        const auto objective = path_objective(system, request, paths[i], raw);
        if (!objective || raw.variables >= branch.limits.max_variables) {
            branch.reason = "Path objective or augmented relation exceeds the exact linear H limits";
            unsupported_path = true;
            branches.push_back(std::move(branch));
            continue;
        }
        branch.objective = *objective;
        std::vector<hx::Row> program_rows;
        std::string relation_reason;
        const auto parsed = append_rows(programs[i].joint_relation,
            raw.variables, branch.limits, program_rows, relation_reason, cancellation);
        if (parsed == RowsState::cancelled) return cancelled();
        if (parsed == RowsState::built) {
            const auto relation = equal_rows(raw.rows, program_rows,
                raw.variables, branch.limits, cancellation);
            if (relation.state == hx::InclusionState::cancelled) return cancelled();
            branch.program_matches = relation.state == hx::InclusionState::included;
            if (relation.state == hx::InclusionState::unsupported)
                relation_reason = relation.reason;
        }
        branch.minimum = hx::minimize_linear(raw.rows,
            raw.variables, branch.objective.coefficients,
            branch.objective.offset, branch.limits, cancellation);
        if (branch.minimum.state == hx::LinearMinimumState::cancelled) return cancelled();
        if (branch.minimum.state == hx::LinearMinimumState::unsupported) {
            branch.reason = branch.minimum.reason;
            unsupported_path = true;
        } else if (branch.minimum.state == hx::LinearMinimumState::unbounded_below) {
            unbounded_path = true;
        } else if (branch.minimum.state == hx::LinearMinimumState::minimum) {
            if (!branch.minimum.attained) {
                branch.reason = "The linear objective infimum is not attained";
                unsupported_path = true;
            } else if (!best) {
                best = branch.minimum.value;
            } else {
                int order = 0;
                if (!hx::compare_scaled_rationals(branch.minimum.value, *best,
                        branch.limits.max_integer_bits, order)) {
                    branch.reason = "Cross-path rational comparison exceeds exact limits";
                    unsupported_path = true;
                } else if (order < 0) {
                    best = branch.minimum.value;
                }
            }
        }
        if (!branch.program_matches && branch.reason.empty())
            branch.reason = relation_reason.empty()
                ? "Program relation differs from the independently reconstructed raw relation"
                : relation_reason;
        branch.supported = branch.minimum.state == hx::LinearMinimumState::minimum &&
                           branch.minimum.attained;
        branches.push_back(std::move(branch));
    }

    HybridFamilyVerificationReport report;
    report.verifier_id = "csl.hybrid.exact-linear-h";
    report.verifier_version = "1";
    report.numerical_policy = policy;
    report.assurance = Assurance::numerical;
    report.enumerated_paths.assign(paths.begin(), paths.end());
    report.branches.reserve(paths.size());
    bool coverage = !unsupported_path && !unbounded_path && best.has_value();
    for (std::size_t i = 0; i < paths.size(); ++i) {
        if (cancellation.stop_requested()) return cancelled();
        const auto& branch = branches[i];
        HybridPathVerificationRecord record{};
        record.path = paths[i];
        record.relation_limits = programs[i].relation_limits;
        record.relation_operations = programs[i].relation_operations;
        if (!branch.program_matches) {
            coverage = false;
            record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                "hybrid.verification.exact_linear_h_program_mismatch",
                branch.reason.empty()
                    ? "Supplied path program relation differs from the independent raw relation"
                    : branch.reason});
        }
        const auto candidate = std::find_if(candidates.begin(), candidates.end(),
            [&](const auto& item) { return item.path == paths[i]; });
        if (!branch.raw_built) {
            record.feasibility = HybridVerificationStatus::unsupported;
            record.objective_optimality = HybridVerificationStatus::unsupported;
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            record.diagnostics.push_back({DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_branch", branch.reason});
            coverage = false;
            report.branches.push_back(std::move(record));
            continue;
        }
        if (branch.minimum.state == hx::LinearMinimumState::infeasible) {
            record.feasibility = HybridVerificationStatus::refuted;
            record.objective_optimality = HybridVerificationStatus::refuted;
            record.continuous_coverage = candidate == candidates.end()
                ? HybridVerificationStatus::established : HybridVerificationStatus::refuted;
            if (!branch.program_matches || candidate != candidates.end()) {
                coverage = false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                    "hybrid.verification.exact_linear_h_infeasible",
                    "An infeasible path has a mismatched program relation or supplied candidate face"});
            }
            report.branches.push_back(std::move(record));
            continue;
        }
        if (branch.minimum.state == hx::LinearMinimumState::unbounded_below) {
            record.feasibility = HybridVerificationStatus::established;
            record.objective_optimality = HybridVerificationStatus::refuted;
            record.continuous_coverage = candidate == candidates.end()
                ? HybridVerificationStatus::established : HybridVerificationStatus::refuted;
            if (candidate != candidates.end()) coverage = false;
            report.branches.push_back(std::move(record));
            continue;
        }
        if (!branch.supported) {
            record.feasibility = HybridVerificationStatus::unsupported;
            record.objective_optimality = HybridVerificationStatus::unsupported;
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            record.diagnostics.push_back({DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_minimum", branch.reason});
            coverage = false;
            report.branches.push_back(std::move(record));
            continue;
        }
        record.feasibility = HybridVerificationStatus::established;
        int order = 0;
        if (!best || !hx::compare_scaled_rationals(branch.minimum.value, *best,
                branch.limits.max_integer_bits, order)) {
            record.objective_optimality = HybridVerificationStatus::unsupported;
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            coverage = false;
            report.branches.push_back(std::move(record));
            continue;
        }
        const bool optimal = order == 0;
        record.objective_optimality = unbounded_path
            ? HybridVerificationStatus::refuted
            : (unsupported_path
                ? (optimal ? HybridVerificationStatus::unsupported : HybridVerificationStatus::refuted)
                : (optimal ? HybridVerificationStatus::established : HybridVerificationStatus::refuted));
        if (!optimal) {
            record.continuous_coverage = candidate == candidates.end()
                ? HybridVerificationStatus::established : HybridVerificationStatus::refuted;
            if (candidate != candidates.end()) coverage = false;
            report.branches.push_back(std::move(record));
            continue;
        }
        if (unbounded_path) {
            record.continuous_coverage = candidate == candidates.end()
                ? HybridVerificationStatus::established : HybridVerificationStatus::refuted;
            if (candidate != candidates.end()) {
                coverage = false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                    "hybrid.verification.exact_linear_h_unbounded_portfolio",
                    "A finite path face cannot be globally optimal while another path is unbounded below"});
            }
            report.branches.push_back(std::move(record));
            continue;
        }
        if (unsupported_path) {
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            coverage = false;
            report.branches.push_back(std::move(record));
            continue;
        }
        if (candidate == candidates.end()) {
            record.continuous_coverage = HybridVerificationStatus::refuted;
            coverage = false;
            record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                "hybrid.verification.exact_linear_h_missing_face",
                "A globally optimal branch is missing its candidate optimal-face relation"});
            report.branches.push_back(std::move(record));
            continue;
        }
        auto raw = hx::reconstruct_path_relation(system, request, paths[i],
            programs[i].relation_limits, branch.limits, cancellation);
        if (raw.state == hx::RawRelationState::cancelled) return cancelled();
        if (raw.state != hx::RawRelationState::built) {
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            coverage = false;
            record.diagnostics.push_back({DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_face_reconstruction",
                raw.reason});
            report.branches.push_back(std::move(record));
            continue;
        }
        auto expected = std::move(raw.rows);
        if (!append_optimum(expected, branch.objective.coefficients,
                branch.objective.offset, branch.minimum.value, branch.limits)) {
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            coverage = false;
            record.diagnostics.push_back({DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_face",
                "Objective-face equality exceeds exact arithmetic or row limits"});
            report.branches.push_back(std::move(record));
            continue;
        }
        std::vector<hx::Row> face;
        std::string reason;
        const auto parsed = append_rows(candidate->relation, raw.variables,
            branch.limits, face, reason, cancellation);
        if (parsed == RowsState::cancelled) return cancelled();
        if (parsed != RowsState::built) {
            record.continuous_coverage = HybridVerificationStatus::unsupported;
            coverage = false;
            record.diagnostics.push_back({DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_candidate", reason});
            report.branches.push_back(std::move(record));
            continue;
        }
        const auto relation = equal_rows(expected, face, raw.variables,
                                         branch.limits, cancellation);
        if (relation.state == hx::InclusionState::cancelled) return cancelled();
        bool face_matches = relation.state == hx::InclusionState::included;
        if (face_matches) {
            std::vector<hx::Row> anchor_rows;
            if (!make_point_rows(candidate->anchor, raw.variables,
                                 branch.limits, anchor_rows)) {
                record.continuous_coverage = HybridVerificationStatus::unsupported;
                coverage = false;
                record.diagnostics.push_back({DiagnosticCode::unsupported,
                    "hybrid.verification.exact_linear_h_anchor",
                    "Candidate anchor is malformed or exceeds exact limits"});
                report.branches.push_back(std::move(record));
                continue;
            }
            const auto anchor_check = hx::included_in(anchor_rows, expected,
                raw.variables, branch.limits, cancellation);
            if (anchor_check.state == hx::InclusionState::cancelled) return cancelled();
            if (anchor_check.state != hx::InclusionState::included) {
                face_matches = false;
                if (anchor_check.state == hx::InclusionState::unsupported)
                    reason = anchor_check.reason;
                else
                    reason = "Candidate optimizer anchor is outside the exact global optimal face";
            }
        }
        record.continuous_coverage = face_matches
            ? HybridVerificationStatus::established
            : (relation.state == hx::InclusionState::unsupported ||
               (relation.state == hx::InclusionState::included &&
                !reason.empty() && reason !=
                    "Candidate optimizer anchor is outside the exact global optimal face")
                ? HybridVerificationStatus::unsupported : HybridVerificationStatus::refuted);
        if (record.continuous_coverage != HybridVerificationStatus::established) {
            coverage = false;
            record.diagnostics.push_back({
                relation.state == hx::InclusionState::not_included ||
                reason == "Candidate optimizer anchor is outside the exact global optimal face"
                    ? DiagnosticCode::evidence_mismatch : DiagnosticCode::unsupported,
                "hybrid.verification.exact_linear_h_face_mismatch",
                !reason.empty() ? reason : relation.reason.empty()
                    ? "Candidate relation differs from the exact global optimal face"
                    : relation.reason});
        }
        report.branches.push_back(std::move(record));
    }

    if (unbounded_path) {
        report.global_objective_optimality = HybridVerificationStatus::refuted;
        report.complete_family_coverage = HybridVerificationStatus::refuted;
    } else if (unsupported_path) {
        report.global_objective_optimality = HybridVerificationStatus::unsupported;
        report.complete_family_coverage = HybridVerificationStatus::unsupported;
    } else if (!best) {
        report.global_objective_optimality = HybridVerificationStatus::refuted;
        report.complete_family_coverage = HybridVerificationStatus::refuted;
    } else {
        report.global_objective_optimality = HybridVerificationStatus::established;
        report.complete_family_coverage = coverage
            ? HybridVerificationStatus::established : HybridVerificationStatus::refuted;
    }
    return report;
}

} // namespace csl::synthesis
