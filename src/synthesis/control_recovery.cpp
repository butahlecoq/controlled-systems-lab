#include <csl/synthesis/control_recovery.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <string_view>
#include <type_traits>

namespace csl::synthesis {
namespace {

Diagnostic unsupported(std::string field, std::string explanation) {
    return {DiagnosticCode::unsupported, std::move(field), std::move(explanation)};
}

Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

std::string identity_field(std::string_view value) {
    return std::to_string(value.size()) + ":" + std::string(value);
}

bool finite(const Vector& values) {
    return std::all_of(values.begin(), values.end(),
        [](double value) { return std::isfinite(value); });
}

struct SparseEntry {
    std::size_t column;
    double value;
};

class JointRows {
    std::size_t columns_;
    SparseMatrix inequalities_;
    Vector upper_bounds_;
    SparseMatrix equalities_;
    Vector equality_values_;

public:
    bool append(std::vector<SparseEntry> coefficients, double bound, bool equality) {
        if (!std::isfinite(bound)) return false;
        std::stable_sort(coefficients.begin(), coefficients.end(),
            [](const SparseEntry& left, const SparseEntry& right) { return left.column < right.column; });

        auto& matrix = equality ? equalities_ : inequalities_;
        auto& bounds = equality ? equality_values_ : upper_bounds_;
        std::size_t retained = 0;
        for (std::size_t index = 0; index < coefficients.size(); ++index) {
            const auto entry = coefficients[index];
            if (entry.column >= columns_ || !std::isfinite(entry.value)) return false;
            if (entry.value == 0.0) continue;
            if (retained != 0 && coefficients[retained - 1].column == entry.column) {
                coefficients[retained - 1].value += entry.value;
                if (!std::isfinite(coefficients[retained - 1].value)) return false;
                if (coefficients[retained - 1].value == 0.0) --retained;
            } else {
                coefficients[retained++] = entry;
            }
        }
        coefficients.resize(retained);

        const auto maximum = std::numeric_limits<std::size_t>::max();
        if (matrix.rows >= maximum - 1 || coefficients.size() > maximum - matrix.values.size())
            return false;
        for (const auto& entry : coefficients) {
            matrix.column_indices.push_back(entry.column);
            matrix.values.push_back(entry.value);
        }
        matrix.row_offsets.push_back(matrix.values.size());
        ++matrix.rows;
        bounds.push_back(bound);
        return true;
    }

public:
    explicit JointRows(std::size_t columns)
        : columns_(columns), inequalities_{0, columns, {0}, {}, {}},
          equalities_{0, columns, {0}, {}, {}} {}

    bool append_set(const sets::SetData& data, std::size_t offset) {
        const auto dimension = data.metadata()->set.dimension;
        if (offset > columns_ || dimension > columns_ - offset) return false;
        const auto representation = data.representation();
        if (const auto* h = std::get_if<sets::HRepresentation>(&representation)) {
            const auto append_rows = [&](numeric::MatrixView matrix, numeric::VectorView bounds,
                                         bool equality) {
                const auto descriptor = matrix.descriptor();
                for (std::size_t row = 0; row < matrix.rows(); ++row) {
                    std::vector<SparseEntry> coefficients;
                    if (const auto* csr = std::get_if<numeric::CsrInput>(&descriptor)) {
                        for (auto index = csr->row_offsets[row]; index < csr->row_offsets[row + 1]; ++index)
                            coefficients.push_back({offset + csr->column_indices[index], csr->values[index]});
                    } else {
                        for (std::size_t column = 0; column < dimension; ++column) {
                            const auto value = matrix(row, column);
                            if (value != 0.0) coefficients.push_back({offset + column, value});
                        }
                    }
                    if (!append(std::move(coefficients), bounds[row], equality)) return false;
                }
                return true;
            };
            return append_rows(h->inequalities, h->upper_bounds, false) &&
                append_rows(h->equalities, h->equality_values, true);
        }
        if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
            for (std::size_t column = 0; column < dimension; ++column) {
                std::vector<SparseEntry> coefficients{{offset + column, 1.0}};
                if (!append(std::move(coefficients), singleton->point[column], true)) return false;
            }
            return true;
        }
        if (std::holds_alternative<sets::EmptyRepresentation>(representation)) {
            // 0 <= -1 preserves emptiness in the lifted ambient space.
            return append({}, -1.0, false);
        }
        if (std::holds_alternative<sets::UniversalRepresentation>(representation)) return true;
        return false;
    }

    sets::Result<sets::SetData> finish(SetId id, std::size_t dimension) const {
        auto inequalities = numeric::snapshot(inequalities_);
        if (const auto* failure = std::get_if<Diagnostic>(&inequalities)) return *failure;
        auto upper = numeric::snapshot_vector(upper_bounds_);
        if (const auto* failure = std::get_if<Diagnostic>(&upper)) return *failure;
        auto equalities = numeric::snapshot(equalities_);
        if (const auto* failure = std::get_if<Diagnostic>(&equalities)) return *failure;
        auto values = numeric::snapshot_vector(equality_values_);
        if (const auto* failure = std::get_if<Diagnostic>(&values)) return *failure;
        return sets::make_h({std::move(id), dimension, {}},
            {std::get<numeric::MatrixView>(std::move(inequalities)),
             std::get<numeric::VectorView>(std::move(upper)),
             std::get<numeric::MatrixView>(std::move(equalities)),
             std::get<numeric::VectorView>(std::move(values))});
    }
};

std::variant<sets::SetData, Diagnostic> state_or_control_data(const AdmissibleSet& input,
        SetId id) {
    return std::visit([&](const auto& value) -> std::variant<sets::SetData, Diagnostic> {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, SetHandle>) {
            auto data = sets::from_handle(value);
            if (const auto* failure = std::get_if<Diagnostic>(&data)) return *failure;
            return std::get<sets::SetData>(std::move(data));
        } else if constexpr (std::is_same_v<T, EmptySet>) {
            return sets::make_empty({std::move(id), value.dimension, {}});
        } else if constexpr (std::is_same_v<T, UniversalSet>) {
            return sets::make_universal({std::move(id), value.dimension, {}});
        } else {
            auto point = numeric::snapshot_vector(value.point);
            if (const auto* failure = std::get_if<Diagnostic>(&point)) return *failure;
            return sets::make_singleton({std::move(id), value.point.size(), {}},
                std::get<numeric::VectorView>(std::move(point)));
        }
    }, input);
}

} // namespace

ControlRecoveryOutcome recover_joint_history(const problem::ResolvedProblem& resolved,
        const sets::SetData& terminal_relation) {
    const auto source = resolved.description();
    const auto system = resolved.model();
    const auto dimensions = system.dimensions();
    const auto horizon = system.horizon();
    const auto fail = [](Diagnostic diagnostic) -> ControlRecoveryOutcome {
        return Diagnostics{std::move(diagnostic)};
    };

    if (source->model->dynamics.time_domain != TimeDomain::discrete ||
        source->information != InformationPattern::nominal_open_loop)
        return fail(unsupported("recovery.profile", "Discrete nominal open-loop dynamics are required."));
    if (dimensions.external != 0 || source->external)
        return fail(unsupported("recovery.external", "External inputs are outside this recovery profile."));
    if (source->temporal && source->temporal->joint_map.rows != 0)
        return fail(unsupported("recovery.temporal", "Temporal coupling is outside this first recovery profile."));
    const auto* initial = std::get_if<KnownInitial>(&source->initial);
    if (!initial)
        return fail(unsupported("recovery.initial", "A known initial point is required."));
    const auto* controls = std::get_if<ContinuousDomain>(&source->controls);
    if (!controls)
        return fail(unsupported("recovery.controls", "Finite and mixed control catalogues are not supported."));
    if (terminal_relation.metadata()->set.dimension != dimensions.state)
        return fail(invalid("recovery.terminal.dimension", "Terminal relation dimension must equal the state dimension."));

    const auto terminal_representation = terminal_relation.representation();
    if (std::holds_alternative<sets::VRepresentation>(terminal_representation))
        return fail(unsupported("recovery.terminal.representation", "Terminal relation must use native H, singleton, empty, or universal geometry."));

    const auto coordinates = resolved.constraints().coordinates();
    const auto n = dimensions.state;
    const auto m = dimensions.control;
    const auto maximum = std::numeric_limits<std::size_t>::max();
    if (horizon == maximum || (n != 0 && horizon + 1 > maximum / n))
        return fail(unsupported("recovery.capacity", "Canonical state-history width overflows size_t."));
    const auto state_width = (horizon + 1) * n;
    if (m != 0 && horizon > maximum / m)
        return fail(unsupported("recovery.capacity", "Canonical control-history width overflows size_t."));
    const auto control_width = horizon * m;
    if (state_width > maximum - control_width)
        return fail(unsupported("recovery.capacity", "Canonical joint-history width overflows size_t."));
    const auto width = state_width + control_width;
    if (coordinates.horizon != horizon || coordinates.dimensions != dimensions ||
        resolved.constraints().joint_dimension() != width)
        return fail({DiagnosticCode::evidence_mismatch, "recovery.coordinates",
            "Resolved joint-coordinate schema does not match the canonical history layout."});
    if (controls->stages.size() != horizon || source->states.size() != horizon + 1)
        return fail({DiagnosticCode::evidence_mismatch, "recovery.stages",
            "Resolved state/control stage counts do not match the dynamics horizon."});

    JointRows rows(width);
    if (initial->point.size() != n || !finite(initial->point))
        return fail(invalid("recovery.initial", "Known initial point has an invalid dimension or nonfinite value."));
    for (std::size_t column = 0; column < n; ++column) {
        std::vector<SparseEntry> coefficients{{column, 1.0}};
        if (!rows.append(std::move(coefficients), initial->point[column], true))
            return fail(unsupported("recovery.arithmetic", "Could not encode the known initial point."));
    }

    for (std::size_t stage = 0; stage <= horizon; ++stage) {
        auto imported = state_or_control_data(source->states[stage],
            {"recovery/state/" + std::to_string(stage)});
        if (const auto* diagnostic = std::get_if<Diagnostic>(&imported)) return fail(*diagnostic);
        const auto& state_set = std::get<sets::SetData>(imported);
        if (state_set.metadata()->set.dimension != n)
            return fail({DiagnosticCode::evidence_mismatch, "recovery.state.dimension",
                "A resolved state constraint changed dimension."});
        if (std::holds_alternative<sets::VRepresentation>(state_set.representation()))
            return fail(unsupported("recovery.state.representation", "State constraints must use native H, singleton, empty, or universal geometry."));
        if (n != 0 && stage > maximum / n)
            return fail(unsupported("recovery.capacity", "State coordinate offset overflows size_t."));
        if (!rows.append_set(state_set, stage * n))
            return fail(unsupported("recovery.arithmetic", "Could not append a state constraint to the joint history."));
    }

    for (std::size_t stage = 0; stage < horizon; ++stage) {
        auto imported = state_or_control_data(controls->stages[stage],
            {"recovery/control/" + std::to_string(stage)});
        if (const auto* diagnostic = std::get_if<Diagnostic>(&imported)) return fail(*diagnostic);
        const auto& control_set = std::get<sets::SetData>(imported);
        if (control_set.metadata()->set.dimension != m)
            return fail({DiagnosticCode::evidence_mismatch, "recovery.control.dimension",
                "A resolved control constraint changed dimension."});
        if (std::holds_alternative<sets::VRepresentation>(control_set.representation()))
            return fail(unsupported("recovery.control.representation", "Control constraints must use native H, singleton, empty, or universal geometry."));
        if (m != 0 && stage > maximum / m)
            return fail(unsupported("recovery.capacity", "Control coordinate offset overflows size_t."));
        const auto offset = state_width + stage * m;
        if (!rows.append_set(control_set, offset))
            return fail(unsupported("recovery.arithmetic", "Could not append a control constraint to the joint history."));
    }

    for (std::size_t stage = 0; stage < horizon; ++stage) {
        const auto dynamics = system.stage({stage});
        if (const auto* diagnostic = std::get_if<Diagnostic>(&dynamics)) return fail(*diagnostic);
        const auto& step = std::get<model::DynamicsStage>(dynamics);
        if (step.A.rows() != n || step.A.cols() != n || step.B.rows() != n || step.B.cols() != m ||
            step.E.rows() != n || step.E.cols() != 0 || step.offset.size() != n)
            return fail({DiagnosticCode::evidence_mismatch, "recovery.dynamics.shape",
                "Resolved nominal dynamics have inconsistent stage dimensions."});
        if (n != 0 && stage + 1 > maximum / n)
            return fail(unsupported("recovery.capacity", "Next-state coordinate offset overflows size_t."));
        const auto next_offset = (stage + 1) * n;
        const auto control_offset = state_width + stage * m;
        for (std::size_t row = 0; row < n; ++row) {
            std::vector<SparseEntry> coefficients{{next_offset + row, 1.0}};
            for (std::size_t column = 0; column < n; ++column)
                if (step.A(row, column) != 0.0)
                    coefficients.push_back({stage * n + column, -step.A(row, column)});
            for (std::size_t column = 0; column < m; ++column)
                if (step.B(row, column) != 0.0)
                    coefficients.push_back({control_offset + column, -step.B(row, column)});
            // x_(t+1) - A_t*x_t - B_t*u_t = a_t. E is absent by profile.
            if (!rows.append(std::move(coefficients), step.offset[row], true))
                return fail(unsupported("recovery.arithmetic", "Could not encode a finite dynamics equality."));
        }
    }

    if (!rows.append_set(terminal_relation, horizon * n))
        return fail(unsupported("recovery.terminal.representation", "Could not append the terminal relation to the joint history."));

    const auto output_id = "recovery/joint-history/" +
        identity_field(resolved.identity().value) +
        identity_field(terminal_relation.metadata()->id.value);
    auto result = rows.finish({output_id}, width);
    if (const auto* diagnostic = std::get_if<Diagnostic>(&result)) return fail(*diagnostic);
    return JointHistoryRelation{coordinates, std::get<sets::SetData>(std::move(result))};
}

} // namespace csl::synthesis
