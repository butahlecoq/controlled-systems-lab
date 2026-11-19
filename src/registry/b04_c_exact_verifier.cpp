#include "compiled_verifiers.hpp"
#include "strategy_a_lineage.hpp"

#include "../synthesis/b04_c_exact_family.hpp"
#include "../synthesis/exact_rational.hpp"
#include <csl/synthesis/b04_c_exact_family.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <limits>
#include <new>
#include <stdexcept>
#include <string_view>
#include <tuple>

namespace csl::registry::detail {
namespace {
namespace br = ::csl::synthesis::detail::b04_c;
namespace er = ::csl::synthesis::detail::exact_rational;
using Rational = er::Rational;
using Payload = br::ExactFamilyPayload;

constexpr std::string_view verifier_id = "csl.verifier.strategy-a.b04-c-exact-dyadic";
constexpr std::string_view verifier_version = "1";
constexpr std::string_view proof_id = "B04-C-exact-dyadic-complete-family-v1";
constexpr double dt = 25.0 / 4.0;

Diagnostics unsupported(std::string explanation) {
    return {{DiagnosticCode::unsupported, "b04-c-exact.profile", std::move(explanation)}};
}

bool same_matrix(const numeric::MatrixView &actual, std::size_t rows, std::size_t columns,
                 std::span<const double> expected) {
    if (actual.rows() != rows || actual.cols() != columns || expected.size() != rows * columns)
        return false;
    for (std::size_t row = 0; row < rows; ++row)
        for (std::size_t column = 0; column < columns; ++column)
            if (actual(row, column) != expected[row * columns + column])
                return false;
    return true;
}

bool same_vector(const numeric::VectorView &actual, std::span<const double> expected) {
    if (actual.size() != expected.size())
        return false;
    for (std::size_t index = 0; index < expected.size(); ++index)
        if (actual[index] != expected[index])
            return false;
    return true;
}

bool h_set_matches(const AdmissibleSet &set, std::size_t dimension, std::size_t rows,
                   std::span<const double> coefficients, std::span<const double> bounds) {
    const auto *handle = std::get_if<SetHandle>(&set);
    if (!handle)
        return false;
    auto converted = sets::from_handle(*handle);
    const auto *data = std::get_if<sets::SetData>(&converted);
    if (!data || data->metadata()->set.dimension != dimension)
        return false;
    const auto representation = data->representation();
    const auto *h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->inequalities.rows() != rows || h->inequalities.cols() != dimension ||
        h->upper_bounds.size() != rows || h->equalities.rows() != 0 ||
        h->equalities.cols() != dimension || h->equality_values.size() != 0)
        return false;
    return same_matrix(h->inequalities, rows, dimension, coefficients) &&
           same_vector(h->upper_bounds, bounds);
}

bool b04_c_source_matches(const problem::ResolvedProblem &problem) {
    const auto source = problem.description();
    const auto model = problem.model();
    const auto dimensions = model.dimensions();
    if (source->model->dynamics.time_domain != TimeDomain::discrete ||
        source->information != InformationPattern::nominal_open_loop || source->external ||
        source->temporal || dimensions.state != 4 || dimensions.control != 1 ||
        dimensions.external != 0 || model.horizon() != br::horizon ||
        source->times.size() != br::horizon + 1 || source->states.size() != br::horizon + 1)
        return false;

    const auto *initial = std::get_if<KnownInitial>(&source->initial);
    constexpr std::array<double, 4> initial_point{1220.28265395983, 119500.0, 440.005764648976,
                                                  45300.0};
    if (!initial || initial->point.size() != initial_point.size())
        return false;
    for (std::size_t coordinate = 0; coordinate < initial_point.size(); ++coordinate)
        if (initial->point[coordinate] != initial_point[coordinate])
            return false;

    for (std::size_t stage = 0; stage <= br::horizon; ++stage)
        if (source->times[stage] != static_cast<double>(stage) * dt)
            return false;

    const auto *controls = std::get_if<ContinuousDomain>(&source->controls);
    if (!controls || controls->stages.size() != br::horizon)
        return false;
    constexpr std::array control_rows{1.0, -1.0};
    constexpr std::array control_bounds{1.0, 1.0};
    for (const auto &control : controls->stages)
        if (!h_set_matches(control, 1, 2, control_rows, control_bounds))
            return false;

    constexpr std::array state_rows{1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0,  0.0,
                                    0.0, 0.0, 1.0, 0.0, 0.0,  0.0, -1.0, 0.0};
    constexpr std::array state_bounds{1224.0, -1176.0, 468.0, -432.0};
    for (const auto &state : source->states)
        if (!h_set_matches(state, 4, 4, state_rows, state_bounds))
            return false;

    constexpr std::array<double, 16> transition{1, 0, 0, 0, -dt, 1, 0, 0, 0, 0, 1, 0, 0, 0, -dt, 1};
    constexpr std::array<double, 4> input{2208.0 / 110.0, 0, -1152.0 / 110.0, 0};
    for (std::size_t stage = 0; stage < br::horizon; ++stage) {
        const auto dynamics = model.stage({stage});
        const auto *linear = std::get_if<::csl::model::DynamicsStage>(&dynamics);
        if (!linear || !same_matrix(linear->A, 4, 4, transition) ||
            !same_matrix(linear->B, 4, 1, input) || linear->offset.size() != 4 ||
            !std::all_of(linear->offset.values().begin(), linear->offset.values().end(),
                         [](double value) { return value == 0; }))
            return false;
    }

    const auto *objective = std::get_if<ResidualNormTerminal>(&source->objective);
    constexpr std::array<double, 20> map{-1, 0, 0, 0, 0, 1, 0, 0, 0, 0,
                                         -1, 0, 0, 0, 0, 1, 0, 1, 0, -(8.0 / 3.0)};
    constexpr std::array<double, 5> target{-1200, 0, -450, 0, 0};
    constexpr std::array<double, 5> weights{1, 1, 64.0 / 9.0, 64.0 / 9.0, 1};
    if (!objective || objective->map.rows != 5 || objective->map.cols != 4 ||
        objective->map.values.size() != map.size() ||
        objective->target != Vector(target.begin(), target.end()) ||
        objective->weights != Vector(weights.begin(), weights.end()))
        return false;
    return std::equal(objective->map.values.begin(), objective->map.values.end(), map.begin());
}

bool make_zero(Rational &value, er::Budget &budget) { return er::make_integer(0, value, budget); }
bool make_one(Rational &value, er::Budget &budget) { return er::make_integer(1, value, budget); }
bool from_double(double source, Rational &value, er::Budget &budget) {
    return er::from_binary64(source, value, budget);
}
bool exact_parse(std::string_view source, Rational &value, er::Budget &budget) {
    return er::parse(source, value, budget);
}

bool dot(std::span<const Rational> left, std::span<const Rational> right, Rational &output,
         er::Budget &budget) {
    if (left.size() != right.size() || !make_zero(output, budget))
        return false;
    for (std::size_t index = 0; index < left.size(); ++index) {
        Rational product, sum;
        if (!er::multiply(left[index], right[index], product, budget) ||
            !er::add(output, product, sum, budget))
            return false;
        output = std::move(sum);
    }
    return true;
}

bool set_exact_state_maps(const problem::ResolvedProblem &problem,
                          std::array<br::AffineState, br::horizon + 1> &maps, er::Budget &budget) {
    const auto source = problem.description();
    const auto &initial = std::get<KnownInitial>(source->initial).point;
    for (std::size_t coordinate = 0; coordinate < br::state_dimension; ++coordinate)
        if (!from_double(initial[coordinate], maps[0].offset[coordinate], budget))
            return false;

    for (std::size_t stage = 0; stage < br::horizon; ++stage) {
        const auto dynamics = problem.model().stage({stage});
        const auto &linear = std::get<::csl::model::DynamicsStage>(dynamics);
        for (std::size_t row = 0; row < br::state_dimension; ++row) {
            Rational base;
            if (!make_zero(base, budget))
                return false;
            for (std::size_t column = 0; column < br::state_dimension; ++column) {
                Rational a, product, sum;
                if (!from_double(linear.A(row, column), a, budget) ||
                    !er::multiply(a, maps[stage].offset[column], product, budget) ||
                    !er::add(base, product, sum, budget))
                    return false;
                base = std::move(sum);
            }
            if (!from_double(linear.offset[row], maps[stage + 1].offset[row], budget) ||
                !er::add(maps[stage + 1].offset[row], base, maps[stage + 1].offset[row], budget))
                return false;

            for (std::size_t control = 0; control < br::control_dimension; ++control) {
                Rational coefficient;
                if (!make_zero(coefficient, budget))
                    return false;
                for (std::size_t column = 0; column < br::state_dimension; ++column) {
                    Rational a, product, sum;
                    if (!from_double(linear.A(row, column), a, budget) ||
                        !er::multiply(a, maps[stage].controls[column][control], product, budget) ||
                        !er::add(coefficient, product, sum, budget))
                        return false;
                    coefficient = std::move(sum);
                }
                if (control == stage) {
                    Rational b, sum;
                    if (!from_double(linear.B(row, 0), b, budget) ||
                        !er::add(coefficient, b, sum, budget))
                        return false;
                    coefficient = std::move(sum);
                }
                maps[stage + 1].controls[row][control] = std::move(coefficient);
            }
        }
    }
    return true;
}

bool append_feasible_rows(Payload &family, const std::array<br::AffineState, br::horizon + 1> &maps,
                          er::Budget &budget) {
    Rational one, minus_one;
    if (!make_one(one, budget) || !er::make_integer(-1, minus_one, budget))
        return false;
    family.feasible_controls.reserve(100);
    for (std::size_t stage = 0; stage < br::horizon; ++stage) {
        br::LinearRow upper, lower;
        upper.coefficients.resize(br::control_dimension);
        lower.coefficients.resize(br::control_dimension);
        for (std::size_t control = 0; control < br::control_dimension; ++control) {
            upper.coefficients[control] = control == stage ? one : Rational{};
            lower.coefficients[control] = control == stage ? minus_one : Rational{};
        }
        upper.bound = one;
        lower.bound = one;
        family.feasible_controls.push_back(std::move(upper));
        family.feasible_controls.push_back(std::move(lower));
    }
    Rational upper_state, lower_state;
    for (std::size_t stage = 0; stage <= br::horizon; ++stage) {
        for (const auto &[coordinate, low, high] :
             {std::tuple<std::size_t, std::int64_t, std::int64_t>{0, 1176, 1224}, {2, 432, 468}}) {
            br::LinearRow upper, lower;
            upper.coefficients.assign(maps[stage].controls[coordinate].begin(),
                                      maps[stage].controls[coordinate].end());
            lower.coefficients.resize(br::control_dimension);
            for (std::size_t control = 0; control < br::control_dimension; ++control)
                if (!er::negate(upper.coefficients[control], lower.coefficients[control], budget))
                    return false;
            Rational high_value, low_value;
            if (!er::make_integer(high, high_value, budget) ||
                !er::make_integer(low, low_value, budget) ||
                !er::subtract(high_value, maps[stage].offset[coordinate], upper.bound, budget) ||
                !er::subtract(maps[stage].offset[coordinate], low_value, lower.bound, budget))
                return false;
            family.feasible_controls.push_back(std::move(upper));
            family.feasible_controls.push_back(std::move(lower));
        }
    }
    return family.feasible_controls.size() == 100;
}

constexpr std::array<std::string_view, br::control_dimension> optimal_control_values{
    "-22372732538527557968995655584885504649887873368947295001505132908576311772305610948689388831835602767915142538822180404220637/65742268634831342597332464158599530180018681724968804273528997972883832204336594969293002728400911316448736602407117160185856",
    "-159384006192329572543393651867075227748500656321159023842966030531559807327558054556393257806825108379775816226647967177095103/525938149078650740778659713268796241440149453799750434188231983783070657634692759754344021827207290531589892819256937281486848",
    "-1196986498380599/4503599627370496",
    "-8233363210229545/36028797018963968",
    "-26917321937333/140737488355328",
    "-2774152811210057/18014398509481984",
    "-8411553722468131/72057594037927936",
    "-715812017059265/9007199254740992",
    "-3041438548693817/72057594037927936",
    "-5702095653255639/1152921504606846976",
    "1164338296291569/36028797018963968",
    "5013734129466781/72057594037927936",
    "3849395875391643/36028797018963968",
    "2595962328255315/18014398509481984",
    "6534453441960373/36028797018963968",
    "7876982229687915/36028797018963968"};

constexpr std::array<std::string_view, br::control_dimension> published_point_controls{
    "6672312342553797/36028797018963968",
    "-1/1",
    "-1/1",
    "1/1",
    "-3708255628650091/18014398509481984",
    "1/1",
    "-1/1",
    "-815638874893547998410771/4398046511104000000000000",
    "-1/1",
    "1/1",
    "-1/1",
    "0/1",
    "0/1",
    "0/1",
    "1/1",
    "8270411448784247/36028797018963968"};

bool evaluate_state(const br::AffineState &state, std::span<const Rational> controls,
                    std::array<Rational, br::state_dimension> &result, er::Budget &budget) {
    for (std::size_t coordinate = 0; coordinate < br::state_dimension; ++coordinate) {
        result[coordinate] = state.offset[coordinate];
        for (std::size_t control = 0; control < br::control_dimension; ++control) {
            Rational product, sum;
            if (!er::multiply(state.controls[coordinate][control], controls[control], product,
                              budget) ||
                !er::add(result[coordinate], product, sum, budget))
                return false;
            result[coordinate] = std::move(sum);
        }
    }
    return true;
}

bool feasible_strictly(const Payload &family, std::span<const Rational> controls,
                       er::Budget &budget) {
    for (const auto &row : family.feasible_controls) {
        Rational value;
        int comparison{};
        if (!dot(row.coefficients, controls, value, budget) ||
            !er::compare(value, row.bound, comparison, budget) || comparison >= 0)
            return false;
    }
    return true;
}

bool exact_optimum(const problem::ResolvedProblem &problem, Payload &family,
                   Rational &objective_squared, er::Budget &budget, std::string &failed_stage) {
    failed_stage = "affine dynamics reconstruction";
    if (!set_exact_state_maps(problem, family.history_lift, budget))
        return false;
    failed_stage = "100 hard constraint reconstruction";
    if (!append_feasible_rows(family, family.history_lift, budget))
        return false;

    failed_stage = "exact KKT witness parsing";
    family.optimal_controls.resize(br::control_dimension);
    for (std::size_t control = 0; control < br::control_dimension; ++control)
        if (!exact_parse(optimal_control_values[control], family.optimal_controls[control], budget))
            return false;
    failed_stage = "strict feasibility of the exact KKT witness";
    if (!feasible_strictly(family, family.optimal_controls, budget))
        return false;

    failed_stage = "terminal replay and fiber reconstruction";
    std::array<Rational, br::state_dimension> terminal{};
    if (!evaluate_state(family.history_lift.back(), family.optimal_controls, terminal, budget))
        return false;
    family.unique_terminal = terminal;
    family.terminal_fiber.reserve(br::state_dimension);
    for (std::size_t coordinate = 0; coordinate < br::state_dimension; ++coordinate)
        family.terminal_fiber.push_back(
            {std::vector<Rational>(family.history_lift.back().controls[coordinate].begin(),
                                   family.history_lift.back().controls[coordinate].end()),
             family.history_lift.back().offset[coordinate]});

    failed_stage = "weighted objective and exact gradient check";
    const auto source = problem.description();
    const auto &authored = std::get<ResidualNormTerminal>(source->objective);
    std::array<Rational, 5> residuals{};
    std::array<Rational, 5> weights{};
    for (std::size_t feature = 0; feature < residuals.size(); ++feature) {
        Rational value, target;
        if (!from_double(authored.target[feature], target, budget) ||
            !er::negate(target, value, budget))
            return false;
        for (std::size_t coordinate = 0; coordinate < br::state_dimension; ++coordinate) {
            Rational coefficient, product, sum;
            if (!from_double(authored.map.values[feature * br::state_dimension + coordinate],
                             coefficient, budget) ||
                !er::multiply(coefficient, terminal[coordinate], product, budget) ||
                !er::add(value, product, sum, budget))
                return false;
            value = std::move(sum);
        }
        residuals[feature] = std::move(value);
        if (!authored.weights.empty()) {
            if (!from_double(authored.weights[feature], weights[feature], budget))
                return false;
        } else if (!make_one(weights[feature], budget))
            return false;
    }

    if (!make_zero(objective_squared, budget))
        return false;
    for (std::size_t feature = 0; feature < residuals.size(); ++feature) {
        Rational square, weighted, sum;
        if (!er::multiply(residuals[feature], residuals[feature], square, budget) ||
            !er::multiply(weights[feature], square, weighted, budget) ||
            !er::add(objective_squared, weighted, sum, budget))
            return false;
        objective_squared = std::move(sum);
    }

    // Exact zero gradient plus strict feasibility is a convex KKT certificate.
    for (std::size_t control = 0; control < br::control_dimension; ++control) {
        Rational gradient;
        if (!make_zero(gradient, budget))
            return false;
        for (std::size_t feature = 0; feature < residuals.size(); ++feature) {
            Rational feature_derivative;
            if (!make_zero(feature_derivative, budget))
                return false;
            for (std::size_t coordinate = 0; coordinate < br::state_dimension; ++coordinate) {
                Rational coefficient, product, sum;
                if (!from_double(authored.map.values[feature * br::state_dimension + coordinate],
                                 coefficient, budget) ||
                    !er::multiply(coefficient,
                                  family.history_lift.back().controls[coordinate][control], product,
                                  budget) ||
                    !er::add(feature_derivative, product, sum, budget))
                    return false;
                feature_derivative = std::move(sum);
            }
            Rational weighted, term, sum;
            if (!er::multiply(weights[feature], feature_derivative, weighted, budget) ||
                !er::multiply(weighted, residuals[feature], term, budget) ||
                !er::add(gradient, term, sum, budget))
                return false;
            gradient = std::move(sum);
        }
        Rational zero;
        if (!make_zero(zero, budget) || gradient != zero)
            return false;
    }

    failed_stage = "published rounded-point reachability witness";
    // Check the owner-authorized rounded terminal point with a separate exact replay.
    std::vector<Rational> point_controls(br::control_dimension);
    for (std::size_t control = 0; control < br::control_dimension; ++control)
        if (!exact_parse(published_point_controls[control], point_controls[control], budget))
            return false;
    if (!std::all_of(
            family.feasible_controls.begin(), family.feasible_controls.end(), [&](const auto &row) {
                Rational value;
                int comparison{};
                return dot(row.coefficients, point_controls, value, budget) &&
                       er::compare(value, row.bound, comparison, budget) && comparison <= 0;
            }))
        return false;
    std::array<Rational, br::state_dimension> point_terminal{};
    if (!evaluate_state(family.history_lift.back(), point_controls, point_terminal, budget))
        return false;
    constexpr std::array<std::string_view, 4> rounded{"12007/10", "-22929/1000", "2251/5",
                                                      "-7709/1000"};
    constexpr std::array<std::string_view, 4> radii{"1/20", "1/2000", "1/20", "1/2000"};
    for (std::size_t coordinate = 0; coordinate < br::state_dimension; ++coordinate) {
        Rational center, radius, residual, magnitude;
        int comparison{};
        if (!exact_parse(rounded[coordinate], center, budget) ||
            !exact_parse(radii[coordinate], radius, budget) ||
            !er::subtract(point_terminal[coordinate], center, residual, budget))
            return false;
        magnitude = residual;
        magnitude.numerator.negative = false;
        if (!er::compare(magnitude, radius, comparison, budget) || comparison > 0)
            return false;
    }
    return true;
}

bool objective_bounds(const Rational &squared, double &lower, double &upper, er::Budget &budget) {
    int zero_comparison{};
    Rational zero;
    if (!make_zero(zero, budget) || !er::compare(squared, zero, zero_comparison, budget) ||
        zero_comparison <= 0)
        return false;
    constexpr std::uint64_t maximum_finite = 0x7fefffffffffffffULL;
    std::uint64_t low = 0;
    std::uint64_t high = maximum_finite;
    std::uint64_t best = 0;
    while (low <= high) {
        const std::uint64_t bits = low + (high - low) / 2;
        const double candidate = std::bit_cast<double>(bits);
        Rational exact, square;
        int order{};
        if (!from_double(candidate, exact, budget) || !er::multiply(exact, exact, square, budget) ||
            !er::compare(square, squared, order, budget))
            return false;
        if (order <= 0) {
            best = bits;
            if (bits == maximum_finite)
                break;
            low = bits + 1;
        } else {
            if (bits == 0)
                break;
            high = bits - 1;
        }
    }
    lower = std::bit_cast<double>(best);
    Rational exact_lower, lower_square;
    int order{};
    if (!from_double(lower, exact_lower, budget) ||
        !er::multiply(exact_lower, exact_lower, lower_square, budget) ||
        !er::compare(lower_square, squared, order, budget))
        return false;
    if (order == 0) {
        upper = lower;
        return true;
    }
    upper = std::nextafter(lower, std::numeric_limits<double>::infinity());
    Rational exact_upper, upper_square;
    return std::isfinite(upper) && from_double(upper, exact_upper, budget) &&
           er::multiply(exact_upper, exact_upper, upper_square, budget) &&
           er::compare(upper_square, squared, order, budget) && order > 0;
}

bool relations_equal(const Payload &left, const Payload &right) {
    return left.feasible_controls == right.feasible_controls &&
           left.terminal_fiber == right.terminal_fiber && left.history_lift == right.history_lift &&
           left.unique_terminal == right.unique_terminal &&
           left.optimal_controls == right.optimal_controls;
}

} // namespace

bool strategy_a_b04_c_exact_profile_valid(const problem::ResolvedProblem &problem,
                                          const FamilyRequest &family,
                                          const RepresentationId &representation) {
    return family.profile == synthesis::b04_c::exact_family_profile &&
           family.target == FamilyTarget::exact_optimal_relation &&
           family.assurance == Assurance::numerical &&
           representation.value == synthesis::b04_c::exact_family_representation &&
           !family.materialization_limit && b04_c_source_matches(problem);
}

std::variant<B04CExactFamilyBuild, Diagnostics>
build_b04_c_exact_family(const StrategyRequest &request) {
    if (!strategy_a_b04_c_exact_profile_valid(request.problem, request.family,
                                              request.configuration.representation) ||
        request.configuration.strategy.value != "csl.synthesis.reach-back" ||
        request.strategy_version != "1" ||
        request.configuration.representation != request.family.representation ||
        request.lineage !=
            synthesis::strategy_a::detail::expected_b04_c_exact_lineage(request.problem.identity()))
        return unsupported(
            "Prepared Strategy A request is outside the frozen corrected-track exact-dyadic profile.");

    try {
        er::Budget budget;
        budget.max_operations = 2'000'000;
        Payload family;
        Rational objective_squared;
        std::string failed_stage;
        if (!exact_optimum(request.problem, family, objective_squared, budget, failed_stage))
            return unsupported(
                "Exact profile failed during " + failed_stage + " (" +
                std::to_string(budget.operations) + " exact operations, " +
                std::to_string(budget.maximum_integer_bits) +
                " maximum integer bits); proof checks and arithmetic caps remain unchanged.");
        Rational band_lower, band_upper, squared_lower, squared_upper;
        if (!exact_parse("61797/2000", band_lower, budget) ||
            !exact_parse("61799/2000", band_upper, budget) ||
            !er::multiply(band_lower, band_lower, squared_lower, budget) ||
            !er::multiply(band_upper, band_upper, squared_upper, budget))
            return unsupported("Exact acceptance-band comparison exceeded its arithmetic budget.");
        int low_order{}, high_order{};
        if (!er::compare(objective_squared, squared_lower, low_order, budget) ||
            !er::compare(objective_squared, squared_upper, high_order, budget))
            return unsupported("Exact acceptance-band comparison exceeded its arithmetic budget.");
        if (low_order < 0 || high_order > 0)
            return unsupported(
                "The exact optimum falls outside the unchanged registered confirmation band.");
        double lower{}, upper{};
        if (!objective_bounds(objective_squared, lower, upper, budget))
            return unsupported(
                "Could not produce an exact outward binary64 enclosure of the objective value.");
        return B04CExactFamilyBuild{std::make_shared<const Payload>(std::move(family)), lower,
                                    upper};
    } catch (const std::bad_alloc &) {
        return unsupported("B04-C exact-family construction exceeded available memory.");
    } catch (const std::length_error &) {
        return unsupported(
            "B04-C exact-family construction exceeded deterministic container limits.");
    }
}

namespace {
class B04CExactFamilyVerifier final : public CompiledCompleteFamilyVerifier {
  public:
    const ModuleId &id() const noexcept override {
        static const ModuleId value{std::string(verifier_id)};
        return value;
    }
    const std::string &version() const noexcept override {
        static const std::string value{verifier_version};
        return value;
    }

    Diagnostics verify(const StrategyRequest &request,
                       const CompleteFamilyProposal &proposal) const override {
        auto rebuilt = build_b04_c_exact_family(request);
        if (const auto *errors = std::get_if<Diagnostics>(&rebuilt))
            return *errors;
        const auto &expected = std::get<B04CExactFamilyBuild>(rebuilt);
        const auto &identity = proposal.identity;
        const auto &family = proposal.family;
        const auto exact_identity =
            identity.problem == request.problem.identity() && identity.request == request.family &&
            identity.coordinates == JointCoordinates{{4, 1, 0}, br::horizon} &&
            identity.strategy == request.configuration.strategy &&
            identity.strategy_version == request.strategy_version &&
            identity.lineage == request.lineage;
        if (!exact_identity || family.completeness.binding != identity ||
            family.relation.coordinates != identity.coordinates ||
            family.relation.representation != request.family.representation ||
            family.assurance != Assurance::numerical)
            return {
                {DiagnosticCode::evidence_mismatch, "b04-c-exact.binding",
                 "B04-C complete-family proof must bind the frozen Strategy A request, coordinates, representation and lineage."}};

        const auto *proof =
            std::get_if<RegisteredCompletenessEvidence>(&family.completeness.support);
        if (!proof || proof->verifier != id() || proof->verifier_version != version() ||
            proof->proof != proof_id)
            return {
                {DiagnosticCode::evidence_mismatch, "b04-c-exact.proof",
                 "B04-C proposal does not carry the registered exact-profile proof identifier."}};

        const auto *candidate = dynamic_cast<const Payload *>(family.relation.payload.get());
        const auto *canonical = dynamic_cast<const Payload *>(expected.relation.get());
        if (!candidate || !canonical || !relations_equal(*candidate, *canonical))
            return {
                {DiagnosticCode::evidence_mismatch, "b04-c-exact.relation",
                 "Candidate does not equal the reconstructed 16-control feasible terminal fiber and 84-coordinate affine lift."}};

        const SymbolicArgument derivation{
            "B04-C exact represented-dyadic KKT and full-history fiber",
            "All 100 hard inequalities are strictly feasible at the exact witness and the exact gradient of the convex weighted squared terminal objective is zero, proving global optimality. The positive weighted residual map is injective in terminal state, so the optimum terminal state is unique. The complete optimizer family is exactly the feasible 16-control polytope intersected with that terminal fiber and lifted affinely to all 84 canonical history coordinates. A separate exact feasible history lies in the rounding box of the published terminal row. The source variant remains B04-c-exact-dyadic-20261102; no historical reproduction claim is made."};
        const auto same_claim = [&](const ClaimEvidence &claim) {
            const auto *support = std::get_if<SymbolicArgument>(&claim.support);
            return claim.problem == request.problem.identity() && support &&
                   support->reference == derivation.reference &&
                   support->assumptions == derivation.assumptions;
        };
        if (!same_claim(family.optimum.optimum) || !family.optimum.bounds.lower ||
            !family.optimum.bounds.upper ||
            family.optimum.bounds.lower->value != expected.objective_lower ||
            family.optimum.bounds.upper->value != expected.objective_upper ||
            !same_claim(family.optimum.bounds.lower->evidence) ||
            !same_claim(family.optimum.bounds.upper->evidence))
            return {
                {DiagnosticCode::evidence_mismatch, "b04-c-exact.optimum",
                 "Published objective bounds must be the exact outward enclosure of the KKT-certified objective and retain the unchanged issue bands."}};
        return {};
    }
};
}

std::shared_ptr<const CompiledCompleteFamilyVerifier> make_b04_c_exact_family_verifier() {
    return std::make_shared<const B04CExactFamilyVerifier>();
}

} // namespace csl::registry::detail
