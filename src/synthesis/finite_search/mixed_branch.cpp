#include <csl/synthesis/finite_mixed_branch.hpp>

#include <cmath>
#include <limits>
#include <string>

namespace csl::synthesis {
namespace {
Diagnostics unsupported(std::string field, std::string message) {
    return {{DiagnosticCode::unsupported, std::move(field), std::move(message)}};
}
Diagnostics invalid(std::string field, std::string message) {
    return {{DiagnosticCode::invalid_input, std::move(field), std::move(message)}};
}
Diagnostics malformed(std::string message) {
    return {{DiagnosticCode::invalid_input, "finite_mixed_branch.relation", std::move(message)}};
}
std::optional<std::size_t> checked_product(std::size_t left, std::size_t right) {
    if (right && left > std::numeric_limits<std::size_t>::max() / right) return std::nullopt;
    return left * right;
}
std::optional<std::size_t> checked_sum(std::size_t left, std::size_t right) {
    if (left > std::numeric_limits<std::size_t>::max() - right) return std::nullopt;
    return left + right;
}
std::optional<std::size_t> joint_dimension(const JointCoordinates& coordinates) {
    if (coordinates.horizon == std::numeric_limits<std::size_t>::max()) return std::nullopt;
    const auto states = checked_product(coordinates.horizon + 1, coordinates.dimensions.state);
    const auto controls = checked_product(coordinates.horizon, coordinates.dimensions.control);
    if (!states || !controls) return std::nullopt;
    return checked_sum(*states, *controls);
}

std::variant<const MixedDomain*, Diagnostics> validate_profile(const Problem& source) {
    const auto& model = source.model->dynamics;
    const auto dimensions = model.dimensions;
    if (source.information != InformationPattern::nominal_open_loop ||
        model.time_domain != TimeDomain::discrete || source.temporal || source.external ||
        dimensions.external != 0 || !source.model->observations.empty() ||
        !std::holds_alternative<KnownInitial>(source.initial))
        return unsupported("finite_mixed_branch.profile",
            "A nominal discrete-time problem with a known initial state and no observations, external inputs, or temporal constraints is required.");

    const auto* mixed = std::get_if<MixedDomain>(&source.controls);
    if (!mixed)
        return unsupported("finite_mixed_branch.controls", "A mixed control domain is required.");
    return mixed;
}

std::optional<LinearStage> specialize_stage(const LinearStage& source,
    std::span<const double> discrete, std::size_t continuous_dimension) {
    Matrix continuous_input{source.B.rows, continuous_dimension,
                            Vector(source.B.rows * continuous_dimension)};
    Vector offset = source.offset;
    for (std::size_t row = 0; row < source.B.rows; ++row) {
        for (std::size_t column = 0; column < continuous_dimension; ++column)
            continuous_input.values[row * continuous_dimension + column] =
                source.B.values[row * source.B.cols + column];
        for (std::size_t column = 0; column < discrete.size(); ++column) {
            const auto contribution =
                source.B.values[row * source.B.cols + continuous_dimension + column] * discrete[column];
            if (!std::isfinite(contribution)) return std::nullopt;
            offset[row] += contribution;
            if (!std::isfinite(offset[row])) return std::nullopt;
        }
    }
    return LinearStage{source.A, std::move(continuous_input), source.E, std::move(offset)};
}
}

FiniteMixedBranchCursor::FiniteMixedBranchCursor(problem::ResolvedProblem source,
        FiniteActionHistoryCursor histories)
    : source_(std::move(source)), histories_(std::move(histories)) {}

std::variant<FiniteMixedBranchCursor, Diagnostics> FiniteMixedBranchCursor::prepare(
        const problem::ResolvedProblem& resolved) {
    const auto source = resolved.description();
    const auto profile = validate_profile(*source);
    if (const auto* errors = std::get_if<Diagnostics>(&profile)) return *errors;
    const auto* mixed = std::get<const MixedDomain*>(profile);
    auto histories = FiniteActionHistoryCursor::prepare(
        mixed->discrete, source->times.size() - 1);
    if (const auto* errors = std::get_if<Diagnostics>(&histories)) return *errors;
    return FiniteMixedBranchCursor(resolved,
        std::get<FiniteActionHistoryCursor>(std::move(histories)));
}

FiniteMixedBranchPrefix FiniteMixedBranchCursor::take_prefix(std::size_t max_branches) {
    auto trial = histories_;
    auto page_histories = trial.take_prefix(max_branches);
    FiniteMixedBranchPrefix page;
    page.entries.reserve(page_histories.histories.size());
    for (auto& history : page_histories.histories) {
        auto prepared = prepare_finite_mixed_branch(source_, history);
        if (auto* branch = std::get_if<FiniteMixedBranchProblem>(&prepared))
            page.entries.emplace_back(std::move(*branch));
        else
            page.entries.emplace_back(FailedFiniteMixedBranch{
                std::move(history), std::get<Diagnostics>(std::move(prepared))});
    }
    page.complete = page_histories.complete;
    histories_ = std::move(trial);
    return page;
}

FiniteMixedBranchOutcome prepare_finite_mixed_branch(
    const problem::ResolvedProblem& resolved, const FiniteActionHistory& history) {
    const auto source = resolved.description();
    const auto& model = source->model->dynamics;
    const auto dimensions = model.dimensions;
    const auto horizon = source->times.size() - 1;

    const auto profile = validate_profile(*source);
    if (const auto* errors = std::get_if<Diagnostics>(&profile)) return *errors;
    const auto* mixed = std::get<const MixedDomain*>(profile);
    if (history.catalogue_indices.size() != horizon)
        return invalid("finite_mixed_branch.history", "History length must match the problem horizon.");
    for (const auto index : history.catalogue_indices)
        if (index >= mixed->discrete.catalogue.size())
            return invalid("finite_mixed_branch.history", "History contains a catalogue index outside the discrete domain.");

    const auto discrete_dimension = mixed->discrete.dimension;
    const auto continuous_dimension = dimensions.control - discrete_dimension;
    std::vector<Vector> discrete_controls;
    discrete_controls.reserve(horizon);
    for (const auto index : history.catalogue_indices)
        discrete_controls.push_back(mixed->discrete.catalogue[index]);

    std::vector<LinearStage> stages;
    stages.reserve(horizon);
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        const auto& coefficients = model.stages;
        const auto& source_stage = std::holds_alternative<LinearStage>(coefficients)
            ? std::get<LinearStage>(coefficients)
            : std::get<std::vector<LinearStage>>(coefficients)[stage];
        auto specialized = specialize_stage(source_stage, discrete_controls[stage], continuous_dimension);
        if (!specialized)
            return unsupported("finite_mixed_branch.affine_offset",
                "Fixing the discrete action produced a non-finite binary64 affine offset at stage " +
                std::to_string(stage) + ".");
        stages.push_back(std::move(*specialized));
    }

    Problem branch = *source;
    branch.id.value += "/finite-branch";
    for (const auto index : history.catalogue_indices)
        branch.id.value += "/" + std::to_string(index);
    auto branch_model = *source->model;
    branch_model.dynamics.dimensions.control = continuous_dimension;
    branch_model.dynamics.stages = std::move(stages);
    branch.model = std::make_shared<const SystemModel>(std::move(branch_model));
    branch.controls = mixed->continuous;

    const auto branch_dimensions = Dimensions{dimensions.state, continuous_dimension, 0};
    return FiniteMixedBranchProblem{history, std::move(branch),
        {{dimensions, horizon}, {branch_dimensions, horizon}, std::move(discrete_controls)}};
}

FiniteMixedBranchRelationOutcome lift_finite_mixed_branch_relation(
    const FiniteMixedBranchProblem& branch, const sets::SetData& relation) {
    const auto& source = branch.coordinates.source;
    const auto& reduced = branch.coordinates.continuous_subproblem;
    if (source.horizon == std::numeric_limits<std::size_t>::max())
        return malformed("Branch horizon overflows the supported size range.");
    if (source.horizon != reduced.horizon || branch.history.catalogue_indices.size() != source.horizon ||
        branch.coordinates.discrete_controls.size() != source.horizon)
        return malformed("Branch coordinate and history horizons must agree.");
    if (source.dimensions.state != reduced.dimensions.state ||
        source.dimensions.external != 0 || reduced.dimensions.external != 0 ||
        reduced.dimensions.control > source.dimensions.control)
        return malformed("The branch must preserve state coordinates and remove only discrete controls.");

    const auto discrete_dimension = source.dimensions.control - reduced.dimensions.control;
    for (const auto& action : branch.coordinates.discrete_controls)
        if (action.size() != discrete_dimension)
            return malformed("Every fixed discrete action must match the removed control dimension.");

    const auto relation_metadata = relation.metadata();
    const auto source_width = joint_dimension(source);
    const auto reduced_width = joint_dimension(reduced);
    const auto state_width = checked_product(source.horizon + 1, source.dimensions.state);
    const auto reduced_state_width_value = checked_product(source.horizon + 1, reduced.dimensions.state);
    const auto discrete_equalities_value = checked_product(source.horizon, discrete_dimension);
    if (!source_width || !reduced_width || !state_width || !reduced_state_width_value ||
        !discrete_equalities_value)
        return malformed("Branch coordinate widths overflow the supported size range.");
    const auto expected_reduced_dimension = *reduced_width;
    if (relation_metadata->set.dimension != expected_reduced_dimension)
        return malformed("The branch relation ambient dimension must match its canonical joint coordinates.");
    const auto representation = relation.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h)
        return Diagnostics{{DiagnosticCode::unsupported, "finite_mixed_branch.relation.representation",
            "Only H-represented branch relations can be lifted without a conversion adapter."}};

    const auto source_dimension = *source_width;
    const auto reduced_state_width = *reduced_state_width_value;
    const auto source_state_width = *state_width;
    std::vector<std::size_t> source_to_reduced(expected_reduced_dimension);
    for (std::size_t i = 0; i < reduced_state_width; ++i) source_to_reduced[i] = i;
    for (std::size_t stage = 0; stage < source.horizon; ++stage)
        for (std::size_t coordinate = 0; coordinate < reduced.dimensions.control; ++coordinate)
            source_to_reduced[reduced_state_width + stage * reduced.dimensions.control + coordinate] =
                source_state_width + stage * source.dimensions.control + coordinate;

    const auto inequality_count = h->inequalities.rows();
    const auto equality_count_value = checked_sum(h->equalities.rows(), *discrete_equalities_value);
    if (!equality_count_value)
        return malformed("The lifted equality count overflows the supported size range.");
    const auto equality_count = *equality_count_value;
    const auto inequality_storage = checked_product(inequality_count, source_dimension);
    const auto equality_storage = checked_product(equality_count, source_dimension);
    if (!inequality_storage || !equality_storage)
        return malformed("The lifted H-representation size overflows the supported size range.");
    Matrix inequalities{inequality_count, source_dimension, Vector(*inequality_storage)};
    Matrix equalities{equality_count, source_dimension, Vector(*equality_storage)};
    Vector upper_bounds(h->upper_bounds.values().begin(), h->upper_bounds.values().end());
    Vector equality_values(equality_count);

    for (std::size_t row = 0; row < inequality_count; ++row)
        for (std::size_t column = 0; column < expected_reduced_dimension; ++column)
            inequalities.values[row * source_dimension + source_to_reduced[column]] = h->inequalities(row, column);
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        for (std::size_t column = 0; column < expected_reduced_dimension; ++column)
            equalities.values[row * source_dimension + source_to_reduced[column]] = h->equalities(row, column);
        equality_values[row] = h->equality_values[row];
    }
    for (std::size_t stage = 0; stage < source.horizon; ++stage) {
        const auto control_offset = source_state_width + stage * source.dimensions.control;
        for (std::size_t coordinate = 0; coordinate < discrete_dimension; ++coordinate) {
            const auto row = h->equalities.rows() + stage * discrete_dimension + coordinate;
            equalities.values[row * source_dimension + control_offset + reduced.dimensions.control + coordinate] = 1.0;
            equality_values[row] = branch.coordinates.discrete_controls[stage][coordinate];
        }
    }

    auto inequality_matrix = numeric::snapshot(inequalities);
    if (const auto* error = std::get_if<Diagnostic>(&inequality_matrix)) return Diagnostics{*error};
    auto inequality_vector = numeric::snapshot_vector(upper_bounds);
    if (const auto* error = std::get_if<Diagnostic>(&inequality_vector)) return Diagnostics{*error};
    auto equality_matrix = numeric::snapshot(equalities);
    if (const auto* error = std::get_if<Diagnostic>(&equality_matrix)) return Diagnostics{*error};
    auto equality_vector = numeric::snapshot_vector(equality_values);
    if (const auto* error = std::get_if<Diagnostic>(&equality_vector)) return Diagnostics{*error};

    auto lifted = sets::make_h(sets::Description{
        SetId{"finite-mixed-branch:" + relation_metadata->id.value}, source_dimension, {}},
        {std::get<numeric::MatrixView>(std::move(inequality_matrix)),
         std::get<numeric::VectorView>(std::move(inequality_vector)),
         std::get<numeric::MatrixView>(std::move(equality_matrix)),
         std::get<numeric::VectorView>(std::move(equality_vector))});
    if (const auto* error = std::get_if<Diagnostic>(&lifted)) return Diagnostics{*error};
    return std::get<sets::SetData>(std::move(lifted));
}

FiniteMixedBranchPortfolioOutcome select_finite_mixed_branch_portfolio(
    std::vector<FiniteMixedBranchEvaluation> evaluations, bool enumeration_complete,
    double near_optimal_tolerance) {
    if (!std::isfinite(near_optimal_tolerance) || near_optimal_tolerance < 0.0)
        return invalid("finite_mixed_branch.near_optimal_tolerance",
            "Near-optimal tolerance must be finite and non-negative.");

    std::optional<double> optimum;
    for (const auto& evaluation : evaluations) {
        const bool prepared = std::holds_alternative<FiniteMixedBranchProblem>(evaluation.branch);
        if (prepared != evaluation.objective.has_value())
            return invalid("finite_mixed_branch.objective",
                prepared ? "Every prepared branch requires an objective value."
                          : "A refused branch must not carry an objective value.");
        if (!prepared && evaluation.continuous_relation)
            return invalid("finite_mixed_branch.relation",
                "A refused branch must not carry a continuous solution relation.");
        if (evaluation.continuous_relation) {
            const auto& mixed_branch = std::get<FiniteMixedBranchProblem>(evaluation.branch);
            const auto expected_dimension = joint_dimension(mixed_branch.coordinates.continuous_subproblem);
            const auto metadata = evaluation.continuous_relation->metadata();
            if (!expected_dimension || !metadata || metadata->set.dimension != *expected_dimension)
                return invalid("finite_mixed_branch.relation",
                    "A continuous solution relation must use the branch's joint coordinates.");
        }
        if (!evaluation.objective) continue;
        if (!std::isfinite(*evaluation.objective))
            return invalid("finite_mixed_branch.objective", "Branch objective must be finite.");
        if (!optimum || *evaluation.objective < *optimum) optimum = *evaluation.objective;
    }

    FiniteMixedBranchPortfolio result{
        std::move(evaluations), {}, optimum, false, enumeration_complete};
    if (optimum) {
        for (std::size_t index = 0; index < result.evaluations.size(); ++index) {
            const auto& evaluation = result.evaluations[index];
            if (evaluation.objective && *evaluation.objective <= *optimum + near_optimal_tolerance) {
                result.optimal_evaluation_indices.push_back(index);
                if (result.optimal_evaluation_indices.size() == 1)
                    result.all_selected_relations_present = evaluation.continuous_relation.has_value();
                else
                    result.all_selected_relations_present = result.all_selected_relations_present &&
                        evaluation.continuous_relation.has_value();
            }
        }
    }
    return result;
}

} // namespace csl::synthesis
