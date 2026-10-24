#include "compiled_verifiers.hpp"

#include "../synthesis/exact_h_polytope.hpp"
#include "strategy_a_lineage.hpp"

#include <csl/optimization/objectives.hpp>
#include <csl/problem/domains.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <type_traits>

namespace csl::registry::detail {
namespace {
namespace exact_h = ::csl::synthesis::detail::exact_h;

constexpr char verifier_id[] = "csl.verifier.strategy-a.nominal-linear-exact";
constexpr char verifier_version[] = "1";
constexpr std::size_t max_matrix_elements = 1000000;

enum class CheckState { established, refuted, unsupported };
struct CheckResult {
    CheckState state{CheckState::unsupported};
    std::string reason;
};

bool finite(double value) { return std::isfinite(value); }

std::optional<sets::SetData> set_data(const AdmissibleSet& input, SetId id) {
    return std::visit([&](const auto& value) -> std::optional<sets::SetData> {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, SetHandle>) {
            auto imported = sets::from_handle(value);
            if (const auto* data = std::get_if<sets::SetData>(&imported)) return *data;
            return {};
        } else if constexpr (std::is_same_v<T, EmptySet>) {
            auto result = sets::make_empty({std::move(id), value.dimension, {}});
            if (const auto* data = std::get_if<sets::SetData>(&result)) return *data;
            return {};
        } else if constexpr (std::is_same_v<T, UniversalSet>) {
            auto result = sets::make_universal({std::move(id), value.dimension, {}});
            if (const auto* data = std::get_if<sets::SetData>(&result)) return *data;
            return {};
        } else {
            auto point = numeric::snapshot_vector(value.point);
            if (!std::holds_alternative<numeric::VectorView>(point)) return {};
            auto result = sets::make_singleton({std::move(id), value.point.size(), {}},
                std::get<numeric::VectorView>(std::move(point)));
            if (const auto* data = std::get_if<sets::SetData>(&result)) return *data;
            return {};
        }
    }, input);
}

bool append_inequality(std::span<const double> coefficients, double bound,
    exact_h::Limits limits, std::vector<exact_h::Row>& rows) {
    return rows.size() < limits.max_rows && exact_h::append_inequality(
        coefficients, bound, false, limits.max_integer_bits, rows);
}

bool append_equality(std::span<const double> coefficients, double value,
    exact_h::Limits limits, std::vector<exact_h::Row>& rows) {
    return rows.size() <= limits.max_rows && limits.max_rows - rows.size() >= 2 &&
        exact_h::append_equality(coefficients, value, limits.max_integer_bits, rows);
}

CheckResult append_set(const sets::SetData& set, std::size_t width,
    std::size_t offset, exact_h::Limits limits, std::vector<exact_h::Row>& rows) {
    if (set.metadata()->set.dimension > width || offset > width ||
        set.metadata()->set.dimension > width - offset)
        return {CheckState::unsupported, "Constraint set has an invalid dimension or coordinate offset"};
    const auto dimension = set.metadata()->set.dimension;
    const auto representation = set.representation();
    if (std::holds_alternative<sets::UniversalRepresentation>(representation))
        return {CheckState::established, {}};
    if (std::holds_alternative<sets::EmptyRepresentation>(representation)) {
        std::vector<double> zero(width, 0.0);
        if (append_inequality(zero, -1.0, limits, rows)) return {CheckState::established, {}};
        return {CheckState::unsupported, "Empty-set row exceeds exact resource limits"};
    }
    if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        if (singleton->point.size() != dimension)
            return {CheckState::unsupported, "Singleton point has a malformed dimension"};
        std::vector<double> row(width, 0.0);
        for (std::size_t column = 0; column < dimension; ++column) {
            row[offset + column] = 1.0;
            const bool added = append_equality(row, singleton->point[column], limits, rows);
            row[offset + column] = 0.0;
            if (!added) return {CheckState::unsupported, "Singleton rows exceed exact resource limits"};
        }
        return {CheckState::established, {}};
    }
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) return {CheckState::unsupported, "Only native H, singleton, empty and universal sets are admitted"};
    if (h->inequalities.cols() != dimension || h->upper_bounds.size() != h->inequalities.rows() ||
        h->equalities.cols() != dimension || h->equality_values.size() != h->equalities.rows())
        return {CheckState::unsupported, "H-representation dimensions are malformed"};
    if (dimension != 0 && width > max_matrix_elements / dimension)
        return {CheckState::unsupported, "Joint H matrix exceeds the reconstruction element cap"};
    std::vector<double> row(width, 0.0);
    for (std::size_t index = 0; index < h->inequalities.rows(); ++index) {
        for (std::size_t column = 0; column < dimension; ++column)
            row[offset + column] = h->inequalities(index, column);
        const bool added = append_inequality(row, h->upper_bounds[index], limits, rows);
        std::fill(row.begin(), row.end(), 0.0);
        if (!added) return {CheckState::unsupported, "H inequalities exceed exact row or integer limits"};
    }
    for (std::size_t index = 0; index < h->equalities.rows(); ++index) {
        for (std::size_t column = 0; column < dimension; ++column)
            row[offset + column] = h->equalities(index, column);
        const bool added = append_equality(row, h->equality_values[index], limits, rows);
        std::fill(row.begin(), row.end(), 0.0);
        if (!added) return {CheckState::unsupported, "H equalities exceed exact row or integer limits"};
    }
    return {CheckState::established, {}};
}

CheckResult append_admissible(const AdmissibleSet& input, std::size_t width,
    std::size_t offset, exact_h::Limits limits, std::vector<exact_h::Row>& rows,
    std::string id) {
    auto data = set_data(input, {std::move(id)});
    if (!data) return {CheckState::unsupported, "Could not import a resolved state or control set"};
    return append_set(*data, width, offset, limits, rows);
}

std::optional<std::size_t> joint_width(std::size_t horizon, std::size_t states,
    std::size_t controls) {
    const auto maximum = std::numeric_limits<std::size_t>::max();
    if (horizon == maximum || (states && horizon + 1 > maximum / states) ||
        (controls && horizon > maximum / controls)) return {};
    const auto state_width = (horizon + 1) * states;
    const auto control_width = horizon * controls;
    if (state_width > maximum - control_width) return {};
    return state_width + control_width;
}

CheckResult reconstruct(const problem::ResolvedProblem& resolved, exact_h::Limits limits,
    std::vector<exact_h::Row>& rows, std::vector<double>& objective) {
    const auto source = resolved.description();
    const auto system = resolved.model();
    const auto dimensions = system.dimensions();
    const auto horizon = system.horizon();
    if (source->model->dynamics.time_domain != TimeDomain::discrete ||
        source->information != InformationPattern::nominal_open_loop ||
        dimensions.external != 0 || source->external ||
        (source->temporal && source->temporal->joint_map.rows != 0))
        return {CheckState::unsupported, "Profile requires discrete nominal dynamics without external or temporal coupling"};
    const auto* initial = std::get_if<KnownInitial>(&source->initial);
    const auto* controls = std::get_if<ContinuousDomain>(&source->controls);
    if (!initial || !controls || controls->stages.size() != horizon ||
        source->states.size() != horizon + 1 || horizon > limits.max_stages)
        return {CheckState::unsupported, "Profile requires a known point and continuous stage controls"};
    const auto width_opt = joint_width(horizon, dimensions.state, dimensions.control);
    if (!width_opt || *width_opt >= limits.max_variables || *width_opt > 31)
        return {CheckState::unsupported, "Joint history width or objective-augmented width exceeds the exact variable cap"};
    const auto width = *width_opt;
    const auto state_width = (horizon + 1) * dimensions.state;
    if (initial->point.size() != dimensions.state ||
        std::any_of(initial->point.begin(), initial->point.end(), [](double x) { return !finite(x); }))
        return {CheckState::unsupported, "Known initial point has malformed or nonfinite coordinates"};
    for (std::size_t coordinate = 0; coordinate < dimensions.state; ++coordinate) {
        std::vector<double> row(width, 0.0);
        row[coordinate] = 1.0;
        if (!append_equality(row, initial->point[coordinate], limits, rows))
            return {CheckState::unsupported, "Known initial point exceeds exact row or integer limits"};
    }
    for (std::size_t stage = 0; stage <= horizon; ++stage) {
        auto added = append_admissible(source->states[stage], width, stage * dimensions.state,
            limits, rows, "nominal-exact/state/" + std::to_string(stage));
        if (added.state != CheckState::established) return added;
    }
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        auto added = append_admissible(controls->stages[stage], width,
            state_width + stage * dimensions.control, limits, rows,
            "nominal-exact/control/" + std::to_string(stage));
        if (added.state != CheckState::established) return added;
    }
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        auto dynamics = system.stage({stage});
        if (!std::holds_alternative<model::DynamicsStage>(dynamics))
            return {CheckState::unsupported, "Resolved dynamics stage could not be read"};
        const auto& step = std::get<model::DynamicsStage>(dynamics);
        if (step.A.rows() != dimensions.state || step.A.cols() != dimensions.state ||
            step.B.rows() != dimensions.state || step.B.cols() != dimensions.control ||
            step.E.cols() != 0 || step.offset.size() != dimensions.state)
            return {CheckState::unsupported, "Resolved nominal dynamics have malformed dimensions"};
        for (std::size_t output = 0; output < dimensions.state; ++output) {
            std::vector<double> row(width, 0.0);
            const auto next = (stage + 1) * dimensions.state + output;
            row[next] = 1.0;
            for (std::size_t state = 0; state < dimensions.state; ++state)
                row[stage * dimensions.state + state] = -step.A(output, state);
            for (std::size_t control = 0; control < dimensions.control; ++control)
                row[state_width + stage * dimensions.control + control] = -step.B(output, control);
            if (!append_equality(row, step.offset[output], limits, rows))
                return {CheckState::unsupported, "Dynamics equality exceeds exact row or integer limits"};
        }
    }
    const auto coefficients = resolved.objective().coefficients();
    const auto* linear = std::get_if<optimization::LinearCoefficients>(&coefficients);
    if (!linear || linear->coefficients.size() != dimensions.state || !finite(linear->offset))
        return {CheckState::unsupported, "Profile requires a finite linear terminal objective"};
    objective.assign(width, 0.0);
    for (std::size_t coordinate = 0; coordinate < dimensions.state; ++coordinate) {
        const auto value = linear->coefficients[coordinate];
        if (!finite(value)) return {CheckState::unsupported, "Terminal objective has nonfinite coefficients"};
        objective[horizon * dimensions.state + coordinate] = value;
    }
    if (rows.size() > limits.max_rows)
        return {CheckState::unsupported, "Reconstructed relation exceeds the exact row limit"};
    return {CheckState::established, {}};
}

bool append_objective_face(std::span<const double> objective, double offset,
    const exact_h::ExactRational& optimum, exact_h::Limits limits,
    std::vector<exact_h::Row>& rows) {
    exact_h::Row scaled;
    int exponent = 0;
    if (!exact_h::make_row(objective, offset, false, limits.max_integer_bits, scaled, &exponent))
        return false;
    if (std::all_of(scaled.coefficients.begin(), scaled.coefficients.end(), exact_h::exact_detail::is_zero))
        return true;
    auto denominator = optimum.denominator;
    if (denominator.negative || exact_h::exact_detail::is_zero(denominator)) return false;
    const auto delta = static_cast<std::int64_t>(optimum.binary_exponent) - exponent;
    exact_h::Row equality;
    equality.coefficients.resize(objective.size());
    exact_h::Integer right = optimum.numerator;
    if (delta >= 0) {
        if (static_cast<std::uint64_t>(delta) > limits.max_integer_bits ||
            !exact_h::exact_detail::shift_left(right, static_cast<std::size_t>(delta), limits.max_integer_bits))
            return false;
    } else {
        const auto shift = static_cast<std::uint64_t>(-delta);
        if (shift > limits.max_integer_bits || !exact_h::exact_detail::shift_left(denominator,
                static_cast<std::size_t>(shift), limits.max_integer_bits)) return false;
    }
    for (std::size_t i = 0; i < objective.size(); ++i)
        if (!exact_h::exact_detail::multiply(denominator, scaled.coefficients[i], limits.max_integer_bits,
                equality.coefficients[i])) return false;
    exact_h::Integer offset_term;
    if (!exact_h::exact_detail::multiply(denominator, scaled.bound, limits.max_integer_bits, offset_term)) return false;
    offset_term.negative = !exact_h::exact_detail::is_zero(offset_term) && !offset_term.negative;
    if (!exact_h::exact_detail::add(right, offset_term, limits.max_integer_bits)) return false;
    equality.bound = std::move(right);
    equality.strict = false;
    if (rows.size() > limits.max_rows || limits.max_rows - rows.size() < 2) return false;
    rows.push_back(equality);
    for (auto& coefficient : equality.coefficients)
        coefficient.negative = !exact_h::exact_detail::is_zero(coefficient) && !coefficient.negative;
    equality.bound.negative = !exact_h::exact_detail::is_zero(equality.bound) && !equality.bound.negative;
    rows.push_back(std::move(equality));
    return true;
}

std::optional<std::pair<double, double>> rational_to_outward_doubles(
    const exact_h::ExactRational& rational, std::size_t max_bits) {
    if (exact_h::exact_detail::is_zero(rational.numerator)) return std::pair{0.0, 0.0};
    if (rational.denominator.negative || exact_h::exact_detail::is_zero(rational.denominator)) return {};
    exact_h::ExactRational magnitude = rational;
    const bool negative = magnitude.numerator.negative;
    magnitude.numerator.negative = false;
    constexpr std::uint64_t max_finite_bits = 0x7fefffffffffffffULL;
    std::uint64_t low = 0;
    std::uint64_t high = max_finite_bits;
    while (low <= high) {
        const auto bits = low + (high - low) / 2;
        const auto dyadic = exact_h::exact_detail::decode(std::bit_cast<double>(bits));
        exact_h::ExactRational candidate;
        candidate.numerator = exact_h::exact_detail::from_u64(dyadic.significand);
        candidate.binary_exponent = dyadic.exponent;
        int order = 0;
        if (!exact_h::compare_scaled_rationals(magnitude, candidate, max_bits, order)) return {};
        if (order == 0) {
            const auto signed_bits = bits | (negative ? (std::uint64_t{1} << 63) : 0);
            const auto exact = std::bit_cast<double>(signed_bits);
            return std::pair{exact, exact};
        }
        if (order > 0) {
            if (bits == max_finite_bits) {
                low = max_finite_bits + 1;
                break;
            }
            low = bits + 1;
        } else {
            if (bits == 0) {
                high = 0;
                break;
            }
            high = bits - 1;
        }
    }
    if (low > max_finite_bits) return {};
    const double floor_magnitude = std::bit_cast<double>(high);
    const double ceil_magnitude = std::bit_cast<double>(low);
    if (negative) return std::pair{-ceil_magnitude, -floor_magnitude};
    return std::pair{floor_magnitude, ceil_magnitude};
}

CheckResult verify_proposal(const StrategyRequest& request, const CompleteFamilyProposal& proposal) {
    const auto& identity = proposal.identity;
    const auto& family = proposal.family;
    const auto& strategy = request.configuration.strategy;
    const auto expected_lineage = strategy_a_nominal_linear_exact_lineage(
        request.problem.identity(), request.problem.model().horizon());
    if (strategy.value != "csl.synthesis.reach-back" || request.strategy_version != "1" ||
        !strategy_a_nominal_linear_exact_profile_valid(request.problem, request.family,
            request.configuration.representation))
        return {CheckState::unsupported, "Verifier only admits the bounded nominal linear Strategy A profile"};
    if (identity.problem != request.problem.identity() || identity.request != request.family ||
        identity.coordinates != request.problem.constraints().coordinates() ||
        identity.strategy != strategy || identity.strategy_version != request.strategy_version ||
        identity.lineage != expected_lineage || request.lineage != expected_lineage ||
        family.completeness.binding != identity || family.relation.coordinates != identity.coordinates ||
        family.relation.representation != request.family.representation || family.assurance != Assurance::numerical)
        return {CheckState::refuted, "Complete-family request, identity, coordinates, lineage or assurance do not match"};
    const auto* proof = std::get_if<RegisteredCompletenessEvidence>(&family.completeness.support);
    if (!proof || proof->verifier.value != verifier_id || proof->verifier_version != verifier_version ||
        proof->proof != "nominal-linear-exact-v1")
        return {CheckState::refuted, "Complete-family proof payload does not select this verifier"};
    if (std::holds_alternative<Unestablished>(family.optimum.optimum.support) ||
        family.optimum.optimum.problem != identity.problem || !family.optimum.bounds.lower ||
        !family.optimum.bounds.upper || family.optimum.bounds.lower->evidence.problem != identity.problem ||
        family.optimum.bounds.upper->evidence.problem != identity.problem)
        return {CheckState::refuted, "Exact optimality claim and matching lower/upper objective evidence are required"};

    exact_h::Limits limits;
    std::vector<exact_h::Row> feasible_rows;
    std::vector<double> objective;
    auto built = reconstruct(request.problem, limits, feasible_rows, objective);
    if (built.state != CheckState::established) return built;
    const auto feasible = exact_h::feasible(feasible_rows, objective.size(), limits);
    if (feasible.state == exact_h::FeasibilityState::unsupported)
        return {CheckState::unsupported, feasible.reason};
    if (feasible.state == exact_h::FeasibilityState::cancelled)
        return {CheckState::unsupported, feasible.reason};
    if (feasible.state != exact_h::FeasibilityState::feasible)
        return {CheckState::unsupported, "Empty feasible history relation is outside this profile"};

    std::vector<double> direction(objective.size(), 0.0);
    for (std::size_t coordinate = 0; coordinate < direction.size(); ++coordinate) {
        direction[coordinate] = 1.0;
        const auto lower = exact_h::minimize_linear(feasible_rows, direction.size(), direction, 0.0, limits);
        direction[coordinate] = -1.0;
        const auto upper = exact_h::minimize_linear(feasible_rows, direction.size(), direction, 0.0, limits);
        direction[coordinate] = 0.0;
        if (lower.state == exact_h::LinearMinimumState::unsupported ||
            upper.state == exact_h::LinearMinimumState::unsupported)
            return {CheckState::unsupported, "Exact boundedness check exceeded the arithmetic or operation limits"};
        if (lower.state != exact_h::LinearMinimumState::minimum ||
            upper.state != exact_h::LinearMinimumState::minimum || !lower.attained || !upper.attained)
            return {CheckState::unsupported, "Feasible joint history must be bounded and nonempty"};
    }
    const auto objective_data = request.problem.objective().coefficients();
    const auto& linear = std::get<optimization::LinearCoefficients>(objective_data);
    const auto optimum = exact_h::minimize_linear(feasible_rows, objective.size(), objective,
        linear.offset, limits);
    if (optimum.state == exact_h::LinearMinimumState::unsupported)
        return {CheckState::unsupported, "Exact objective minimization exceeded the arithmetic or operation limits"};
    if (optimum.state != exact_h::LinearMinimumState::minimum || !optimum.attained)
        return {CheckState::unsupported, "Objective must have a finite attained minimum"};
    const auto exact_bounds = rational_to_outward_doubles(optimum.value, limits.max_integer_bits);
    if (!exact_bounds || family.optimum.bounds.lower->value != exact_bounds->first ||
        family.optimum.bounds.upper->value != exact_bounds->second)
        return {CheckState::refuted,
            "Published objective bounds must be the tight outward binary64 enclosure of the exact rational optimum"};

    auto optimal_rows = feasible_rows;
    if (!append_objective_face(objective, linear.offset, optimum.value, limits, optimal_rows))
        return {CheckState::unsupported, "Exact objective face exceeds the arithmetic or row limits"};
    const auto* candidate = family.relation.payload ? family.relation.payload->h_relation_for_recording() : nullptr;
    if (!candidate || !std::holds_alternative<sets::HRepresentation>(candidate->representation()))
        return {CheckState::unsupported, "Nominal exact profile requires a recorded native H relation"};
    std::vector<exact_h::Row> candidate_rows;
    auto candidate_check = append_set(*candidate, objective.size(), 0, limits, candidate_rows);
    if (candidate_check.state != CheckState::established) return candidate_check;
    const auto forward = exact_h::included_in(candidate_rows, optimal_rows, objective.size(), limits);
    if (forward.state == exact_h::InclusionState::unsupported || forward.state == exact_h::InclusionState::cancelled)
        return {CheckState::unsupported, "Candidate-to-optimal-face inclusion could not be decided within exact limits"};
    if (forward.state != exact_h::InclusionState::included)
        return {CheckState::refuted, "Candidate relation contains a history outside the exact optimal face"};
    const auto reverse = exact_h::included_in(optimal_rows, candidate_rows, objective.size(), limits);
    if (reverse.state == exact_h::InclusionState::unsupported || reverse.state == exact_h::InclusionState::cancelled)
        return {CheckState::unsupported, "Optimal-face-to-candidate inclusion could not be decided within exact limits"};
    if (reverse.state != exact_h::InclusionState::included)
        return {CheckState::refuted, "Candidate relation omits a feasible optimal history"};
    return {CheckState::established, {}};
}

class NominalLinearExactVerifier final : public CompiledCompleteFamilyVerifier {
public:
    const ModuleId& id() const noexcept override { static const ModuleId value{verifier_id}; return value; }
    const std::string& version() const noexcept override { static const std::string value{verifier_version}; return value; }
    Diagnostics verify(const StrategyRequest& request, const CompleteFamilyProposal& proposal) const override {
        const auto result = verify_proposal(request, proposal);
        if (result.state == CheckState::established) return {};
        const auto code = result.state == CheckState::unsupported ? DiagnosticCode::unsupported :
            DiagnosticCode::evidence_mismatch;
        return {{code, "nominal-linear-exact.verifier", result.reason}};
    }
};

bool supported_set(const AdmissibleSet& input, std::size_t dimension) {
    auto data = set_data(input, {"nominal-exact/admission"});
    if (!data || data->metadata()->set.dimension != dimension) return false;
    return !std::holds_alternative<sets::VRepresentation>(data->representation());
}
} // namespace

bool strategy_a_nominal_linear_exact_profile_valid(const problem::ResolvedProblem& problem,
    const FamilyRequest& family, const RepresentationId& representation) {
    if (family.profile != synthesis::strategy_a::nominal_linear_exact_profile ||
        family.target != FamilyTarget::exact_optimal_relation || family.assurance != Assurance::numerical ||
        representation.value != "csl.polyhedron.h" || family.materialization_limit) return false;
    const auto source = problem.description();
    const auto model = problem.model();
    const auto dimensions = model.dimensions();
    const auto horizon = model.horizon();
    if (source->model->dynamics.time_domain != TimeDomain::discrete ||
        source->information != InformationPattern::nominal_open_loop || dimensions.external != 0 ||
        source->external || (source->temporal && source->temporal->joint_map.rows != 0) ||
        !std::holds_alternative<KnownInitial>(source->initial) || horizon > exact_h::default_max_stages ||
        !joint_width(horizon, dimensions.state, dimensions.control) ||
        *joint_width(horizon, dimensions.state, dimensions.control) >= exact_h::default_max_variables) return false;
    const auto* controls = std::get_if<ContinuousDomain>(&source->controls);
    if (!controls || controls->stages.size() != horizon || source->states.size() != horizon + 1) return false;
    for (const auto& state : source->states)
        if (!supported_set(state, dimensions.state)) return false;
    for (const auto& control : controls->stages)
        if (!supported_set(control, dimensions.control)) return false;
    const auto objective = problem.objective().coefficients();
    const auto* linear = std::get_if<optimization::LinearCoefficients>(&objective);
    if (!linear || linear->coefficients.size() != dimensions.state || !finite(linear->offset)) return false;
    for (std::size_t index = 0; index < linear->coefficients.size(); ++index)
        if (!finite(linear->coefficients[index])) return false;
    return true;
}

std::optional<std::pair<double, double>> strategy_a_nominal_linear_exact_optimum_bounds(
    const problem::ResolvedProblem& problem) {
    std::vector<exact_h::Row> rows;
    std::vector<double> objective;
    const auto reconstructed = reconstruct(problem, {}, rows, objective);
    if (reconstructed.state != CheckState::established) return {};
    const auto objective_data = problem.objective().coefficients();
    const auto* linear = std::get_if<optimization::LinearCoefficients>(&objective_data);
    if (!linear) return {};
    const auto optimum = exact_h::minimize_linear(rows, objective.size(), objective,
        linear->offset);
    if (optimum.state != exact_h::LinearMinimumState::minimum || !optimum.attained)
        return {};
    return rational_to_outward_doubles(optimum.value, exact_h::default_max_integer_bits);
}

std::optional<sets::SetData> strategy_a_nominal_linear_exact_optimal_relation(
    const problem::ResolvedProblem& problem, SetId id, std::vector<std::string> labels) {
    exact_h::Limits limits;
    std::vector<exact_h::Row> rows;
    std::vector<double> objective;
    const auto built = reconstruct(problem, limits, rows, objective);
    if (built.state != CheckState::established) return {};
    const auto coefficients = problem.objective().coefficients();
    const auto& linear = std::get<optimization::LinearCoefficients>(coefficients);
    const auto optimum = exact_h::minimize_linear(rows, objective.size(), objective, linear.offset, limits);
    if (optimum.state != exact_h::LinearMinimumState::minimum || !optimum.attained ||
        !append_objective_face(objective, linear.offset, optimum.value, limits, rows)) return {};
    constexpr std::size_t max_binary64_search_steps = 63;
    if (objective.size() == std::numeric_limits<std::size_t>::max() ||
        rows.size() > limits.max_operations / max_binary64_search_steps / (objective.size() + 1))
        return {};

    std::vector<double> inequalities;
    std::vector<double> upper_bounds;
    std::vector<double> equalities;
    std::vector<double> equality_values;
    inequalities.reserve(rows.size() * objective.size());
    upper_bounds.reserve(rows.size());
    auto opposites = [](const exact_h::Integer& lhs, const exact_h::Integer& rhs) {
        return lhs.words == rhs.words && (exact_h::exact_detail::is_zero(lhs) || lhs.negative != rhs.negative);
    };
    auto as_exact_double = [&](const exact_h::Integer& integer, double& value) {
        exact_h::ExactRational rational;
        rational.numerator = integer;
        rational.denominator = exact_h::exact_detail::from_u64(1);
        return exact_h::exact_rational_to_double(rational, limits.max_integer_bits, value);
    };
    for (std::size_t row_index = 0; row_index < rows.size(); ++row_index) {
        const auto& row = rows[row_index];
        if (row.strict || row.coefficients.size() != objective.size()) return {};
        const bool paired_equality = row_index + 1 < rows.size() && !rows[row_index + 1].strict &&
            rows[row_index + 1].coefficients.size() == objective.size() &&
            opposites(row.bound, rows[row_index + 1].bound) &&
            std::equal(row.coefficients.begin(), row.coefficients.end(),
                rows[row_index + 1].coefficients.begin(), opposites);
        auto& target = paired_equality ? equalities : inequalities;
        auto& target_bounds = paired_equality ? equality_values : upper_bounds;
        for (const auto& coefficient : row.coefficients) {
            double value{};
            if (!as_exact_double(coefficient, value)) return {};
            target.push_back(value);
        }
        double bound{};
        if (!as_exact_double(row.bound, bound)) return {};
        target_bounds.push_back(bound);
        if (paired_equality) {
            ++row_index;
        }
    }
    auto inequality_matrix = numeric::snapshot(Matrix{
        upper_bounds.size(), objective.size(), std::move(inequalities)});
    auto upper_vector = numeric::snapshot_vector(Vector(std::move(upper_bounds)));
    auto equality_matrix = numeric::snapshot(Matrix{
        equality_values.size(), objective.size(), std::move(equalities)});
    auto equality_vector = numeric::snapshot_vector(Vector(std::move(equality_values)));
    if (!std::holds_alternative<numeric::MatrixView>(inequality_matrix) ||
        !std::holds_alternative<numeric::VectorView>(upper_vector) ||
        !std::holds_alternative<numeric::MatrixView>(equality_matrix) ||
        !std::holds_alternative<numeric::VectorView>(equality_vector)) return {};
    auto made = sets::make_h({std::move(id), objective.size(), std::move(labels)},
        {std::get<numeric::MatrixView>(std::move(inequality_matrix)),
         std::get<numeric::VectorView>(std::move(upper_vector)),
         std::get<numeric::MatrixView>(std::move(equality_matrix)),
         std::get<numeric::VectorView>(std::move(equality_vector))});
    if (!std::holds_alternative<sets::SetData>(made)) return {};
    return std::get<sets::SetData>(std::move(made));
}

std::vector<TransformStepIdentity> strategy_a_nominal_linear_exact_lineage(const ProblemId& problem,
    std::size_t horizon) {
    return synthesis::strategy_a::detail::expected_nominal_lineage(problem, horizon);
}

std::shared_ptr<const CompiledCompleteFamilyVerifier> make_nominal_linear_exact_verifier() {
    return std::make_shared<const NominalLinearExactVerifier>();
}
} // namespace csl::registry::detail
