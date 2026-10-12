#include <csl/geometry/polyhedral_intersection.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::geometry::polyhedral {
namespace {
Diagnostic invalid(const char* field, const char* explanation) {
    return {DiagnosticCode::invalid_input, field, explanation};
}
bool supported_numerical(const EvidenceSupport& evidence) {
    return std::holds_alternative<NumericalCheck>(evidence);
}
std::optional<LinearProgram> implication_program(const sets::HRepresentation& h,
        const std::vector<std::size_t>& rows, std::size_t candidate, const SetId& set_id) {
    const auto n = h.inequalities.cols();
    if (h.equalities.rows() > std::numeric_limits<std::size_t>::max() - rows.size()) return {};
    const auto row_count = rows.size() + h.equalities.rows();
    SparseMatrix matrix{row_count, n, {0}, {}, {}};
    if (row_count == std::numeric_limits<std::size_t>::max()) return {};
    for (std::size_t r = 0; r < row_count; ++r) {
        for (std::size_t c = 0; c < n; ++c) {
            const double value = r < rows.size() ? h.inequalities(rows[r],c) : h.equalities(r-rows.size(),c);
            if (value != 0.0) {
                matrix.column_indices.push_back(c);
                matrix.values.push_back(value);
            }
        }
        matrix.row_offsets.push_back(matrix.values.size());
    }
    std::vector<Interval> intervals;
    intervals.reserve(row_count);
    for (const auto index : rows) intervals.push_back({{}, h.upper_bounds[index]});
    for (std::size_t i = 0; i < h.equalities.rows(); ++i)
        intervals.push_back({h.equality_values[i], h.equality_values[i]});
    Vector objective(n);
    for (std::size_t c = 0; c < n; ++c) objective[c] = -h.inequalities(candidate,c);
    std::vector<Interval> variables(n);
    const auto program_id = "halfspace-" + std::to_string(candidate);
    auto made = optimization::make_linear_program({{{"geo04:" + set_id.value},{program_id}},
        std::move(objective), 0.0, std::move(matrix), std::move(variables), std::move(intervals)});
    if (auto* program = std::get_if<LinearProgram>(&made)) return *program;
    return {};
}
bool proves_redundant(const ProgramResult& result, const LinearProgram& program,
        double bound) {
    if (result.termination != Termination::completed ||
        result.outcome.value != MathematicalOutcome::optimal ||
        result.outcome.subject != program.identity() || !supported_numerical(result.outcome.support) ||
        !result.objective.lower || result.objective.lower->evidence.subject != program.identity() ||
        !supported_numerical(result.objective.lower->evidence.support) || !std::isfinite(result.objective.lower->value)) return false;
    if (!optimization::check_program_result(result, program, Assurance::numerical).empty()) return false;
    // min(-a*x) >= L implies max(a*x-b) <= -L-b. Require a strict
    // nonpositive binary64 result; tolerances must not turn a positive maximum
    // violation into a deletion.
    const double maximum_violation_upper = -result.objective.lower->value - bound;
    return std::isfinite(maximum_violation_upper) && maximum_violation_upper <= 0.0;
}
} // namespace

HalfspaceReductionResult remove_redundant_halfspaces(const sets::SetData& input, SetId output_id,
        LPWorkspace& lp, const ExecutionContext& context) {
    if (output_id.value.empty()) return Diagnostics{invalid("geometry.halfspace_reducer.id", "Output set identity must be nonempty.")};
    if (!std::isfinite(context.numerical.absolute_tolerance) || context.numerical.absolute_tolerance < 0.0 ||
        !std::isfinite(context.numerical.relative_tolerance) || context.numerical.relative_tolerance < 0.0)
        return Diagnostics{invalid("geometry.halfspace_reducer.tolerance", "Finite nonnegative tolerances are required.")};
    const auto metadata = input.metadata();
    const auto representation = input.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) return Diagnostics{{DiagnosticCode::unsupported, "geometry.halfspace_reducer.representation",
        "Redundant-halfspace reduction requires native H data."}};
    std::vector<std::size_t> retained(h->inequalities.rows()), removed;
    for (std::size_t i = 0; i < retained.size(); ++i) retained[i] = i;
    HalfspaceReductionStatus status = HalfspaceReductionStatus::complete;
    std::size_t calls = 0;
    std::size_t position = 0;
    while (position < retained.size()) {
        const auto candidate = retained[position];
        std::vector<std::size_t> others;
        others.reserve(retained.size() - 1);
        for (const auto row : retained) if (row != candidate) others.push_back(row);
        auto program = implication_program(*h, others, candidate, metadata->id);
        if (!program) { status = HalfspaceReductionStatus::incomplete; ++position; continue; }
        ++calls;
        const auto outcome = lp.solve(*program, context);
        if (const auto* answer = std::get_if<ProgramResult>(&outcome)) {
            if (proves_redundant(*answer, *program, h->upper_bounds[candidate])) {
                removed.push_back(candidate);
                retained.erase(retained.begin() + static_cast<std::ptrdiff_t>(position));
                continue;
            }
            status = HalfspaceReductionStatus::incomplete;
        } else {
            status = HalfspaceReductionStatus::incomplete;
        }
        ++position;
    }
    Matrix a{retained.size(), metadata->set.dimension, {}};
    Vector b; b.reserve(retained.size());
    for (const auto row : retained) {
        for (std::size_t c = 0; c < metadata->set.dimension; ++c) a.values.push_back(h->inequalities(row,c));
        b.push_back(h->upper_bounds[row]);
    }
    Matrix e{h->equalities.rows(), metadata->set.dimension, {}};
    Vector f; f.reserve(h->equalities.rows());
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        for (std::size_t c = 0; c < metadata->set.dimension; ++c) e.values.push_back(h->equalities(row,c));
        f.push_back(h->equality_values[row]);
    }
    auto av = numeric::snapshot(a); auto bv = numeric::snapshot_vector(b);
    auto ev = numeric::snapshot(e); auto fv = numeric::snapshot_vector(f);
    if (!std::holds_alternative<numeric::MatrixView>(av) || !std::holds_alternative<numeric::VectorView>(bv) ||
        !std::holds_alternative<numeric::MatrixView>(ev) || !std::holds_alternative<numeric::VectorView>(fv))
        return Diagnostics{invalid("geometry.halfspace_reducer.storage", "Could not create immutable reduced H data.")};
    auto made = sets::make_h({output_id, metadata->set.dimension, metadata->coordinate_labels},
        {std::get<numeric::MatrixView>(av), std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(ev), std::get<numeric::VectorView>(fv)});
    if (auto* error = std::get_if<Diagnostic>(&made)) return Diagnostics{*error};
    return HalfspaceReduction{std::get<sets::SetData>(std::move(made)), status,
        std::move(retained), std::move(removed), calls};
}
} // namespace csl::geometry::polyhedral
