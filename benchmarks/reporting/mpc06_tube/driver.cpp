#include "synthesis/exact_h_polytope.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <initializer_list>
#include <iostream>
#include <vector>

namespace exact_h = csl::synthesis::detail::exact_h;

namespace {

using Point = std::array<double, 2>;
constexpr double disturbance_radius = 0.125;
constexpr double state_bound = 1.0;
constexpr double input_bound = 1.0;
constexpr Point initial_state{0.0, 0.0};
constexpr std::size_t horizon = 3;

bool add_row(std::vector<exact_h::Row>& rows,
             std::initializer_list<double> coefficients, double bound) {
    const std::vector<double> values(coefficients);
    return exact_h::append_inequality(values, bound, false,
                                      exact_h::default_max_integer_bits, rows);
}

bool add_equality(std::vector<exact_h::Row>& rows,
                  std::initializer_list<double> coefficients, double value) {
    const std::vector<double> values(coefficients);
    return exact_h::append_equality(values, value,
                                    exact_h::default_max_integer_bits, rows);
}

std::vector<exact_h::Row> tube_rows(std::size_t first, std::size_t variables) {
    // Z = [-1/8,1/8](0,1) + [-1/8,1/8](1,-1).
    // Its exact facet normals are (1,0) and (1,1).
    const auto row = [first, variables](double a, double b, double bound) {
        std::vector<double> coefficients(variables, 0.0);
        coefficients[first] = a;
        coefficients[first + 1] = b;
        exact_h::Row result;
        if (!exact_h::make_row(coefficients, bound, false,
                               exact_h::default_max_integer_bits, result))
            return exact_h::Row{};
        return result;
    };
    std::vector<exact_h::Row> rows;
    rows.push_back(row(1.0, 0.0, disturbance_radius));
    rows.push_back(row(-1.0, 0.0, disturbance_radius));
    rows.push_back(row(1.0, 1.0, disturbance_radius));
    rows.push_back(row(-1.0, -1.0, disturbance_radius));
    if (std::any_of(rows.begin(), rows.end(), [](const auto& value) {
            return value.coefficients.empty();
        }))
        return {};
    return rows;
}

bool prove_rpi() {
    constexpr std::size_t variables = 5;
    // Relation variables are (e1,e2,w,e1_next,e2_next).
    auto source = tube_rows(0, variables);
    if (!add_row(source, {0.0, 0.0, 1.0, 0.0, 0.0}, disturbance_radius) ||
        !add_row(source, {0.0, 0.0, -1.0, 0.0, 0.0}, disturbance_radius) ||
        !add_equality(source, {-1.0, -1.0, 0.0, 1.0, 0.0}, 0.0) ||
        !add_equality(source, {1.0, 1.0, -1.0, 0.0, 1.0}, 0.0))
        return false;

    auto target = tube_rows(3, variables);
    const auto result = exact_h::included_in(source, target, variables);
    return result.state == exact_h::InclusionState::included;
}

bool in_box(Point value, double bound) {
    return std::abs(value[0]) <= bound && std::abs(value[1]) <= bound;
}

} // namespace

int main() {
    // x+ = Ax + Bu + Ew, u = v + Ke.  K makes F=A+BK nilpotent of index 2.
    constexpr std::array<std::array<double, 2>, 2> a{{{{1.0, 1.0}}, {{0.0, 1.0}}}};
    constexpr std::array<double, 2> b{{0.0, 1.0}};
    constexpr std::array<double, 2> e{{0.0, 1.0}};
    constexpr std::array<double, 2> k{{-1.0, -2.0}};
    constexpr std::array<std::array<double, 2>, 2> f{{{{1.0, 1.0}}, {{-1.0, -1.0}}}};
    std::array<std::array<double, 2>, 2> derived_f{};
    for (std::size_t row = 0; row < 2; ++row)
        for (std::size_t column = 0; column < 2; ++column)
            derived_f[row][column] = a[row][column] + b[row] * k[column];
    const bool feedback_matches = derived_f == f;
    const std::array<std::array<double, 2>, 2> f_squared{{
        {{f[0][0] * f[0][0] + f[0][1] * f[1][0],
          f[0][0] * f[0][1] + f[0][1] * f[1][1]}},
        {{f[1][0] * f[0][0] + f[1][1] * f[1][0],
          f[1][0] * f[0][1] + f[1][1] * f[1][1]}}
    }};
    const bool nilpotent = f_squared[0][0] == 0.0 && f_squared[0][1] == 0.0 &&
                           f_squared[1][0] == 0.0 && f_squared[1][1] == 0.0;
    const bool invariant = prove_rpi();

    // Exact support values for the two zonotope generators and their feedback image.
    const std::array<double, 2> state_support{{disturbance_radius,
                                               2.0 * disturbance_radius}};
    const double input_support = 3.0 * disturbance_radius;
    const std::array<double, 2> tightened_state{{state_bound - state_support[0],
                                                 state_bound - state_support[1]}};
    const double tightened_input = input_bound - input_support;
    const bool empty_tightening = tightened_state[0] < 0.0 ||
                                  tightened_state[1] < 0.0 || tightened_input < 0.0;
    constexpr double empty_fixture_state_bound = 0.2;
    const bool edge_tightening_empty = empty_fixture_state_bound - state_support[1] < 0.0;

    // e=(1/8,-1/4) is a tube vertex with K e=3/8; nominal v=3/4 is unsafe.
    constexpr Point unsafe_tube_error{0.125, -0.25};
    constexpr double unsafe_nominal_input = 0.75;
    const double unsafe_actual_input = unsafe_nominal_input +
        k[0] * unsafe_tube_error[0] + k[1] * unsafe_tube_error[1];
    const bool unsafe_plan_rejected = unsafe_actual_input > input_bound &&
        std::abs(unsafe_nominal_input) > tightened_input;

    std::size_t checked_paths = 0;
    double worst_state_abs = 0.0;
    double worst_input_abs = 0.0;
    bool all_paths_safe = true;
    for (unsigned mask = 0; mask < (1U << horizon); ++mask) {
        Point state = initial_state;
        for (std::size_t stage = 0; stage < horizon; ++stage) {
            const double disturbance = (mask & (1U << stage))
                                           ? disturbance_radius
                                           : -disturbance_radius;
            const Point nominal_control{0.0, 0.0};
            const double error_feedback = k[0] * state[0] + k[1] * state[1];
            const double control = nominal_control[0] + error_feedback;
            const Point next{{a[0][0] * state[0] + a[0][1] * state[1] + b[0] * control + e[0] * disturbance,
                              a[1][0] * state[0] + a[1][1] * state[1] + b[1] * control + e[1] * disturbance}};
            worst_state_abs = std::max(worst_state_abs,
                                       std::max(std::abs(next[0]), std::abs(next[1])));
            worst_input_abs = std::max(worst_input_abs, std::abs(control));
            all_paths_safe = all_paths_safe && in_box(next, state_bound) &&
                             std::abs(control) <= input_bound;
            state = next;
        }
        ++checked_paths;
    }

    const bool initial_in_tube = in_box(initial_state, disturbance_radius) &&
                                 std::abs(initial_state[0] + initial_state[1]) <= disturbance_radius;
    const bool nominal_plan_tightened_feasible =
        std::abs(initial_state[0]) <= tightened_state[0] &&
        std::abs(initial_state[1]) <= tightened_state[1] &&
        0.0 <= tightened_input;

    std::cout << std::setprecision(17)
              << "{\"schema\":\"csl.mpc06-nilpotent-tube-pilot/1\","
              << "\"case_id\":\"double-integrator-nilpotent-tube-v1\","
              << "\"scenario_sha256\":\"" << CSL_MPC06_SCENARIO_SHA256 << "\","
              << "\"arithmetic\":\"IEEE-754 binary64; all fixture coefficients are dyadic and selected transforms are exact\","
              << "\"system\":{\"A\":[[" << a[0][0] << ',' << a[0][1] << "],[" << a[1][0] << ',' << a[1][1]
              << "]],\"B\":[[" << b[0] << "],[" << b[1] << "]],\"E\":[[" << e[0] << "],[" << e[1]
              << "]],\"K\":[[" << k[0] << ',' << k[1] << "]]},"
              << "\"disturbance_radius\":" << disturbance_radius << ','
              << "\"horizon\":" << horizon << ','
              << "\"nilpotent_index_2_verified\":" << (nilpotent ? "true" : "false") << ','
              << "\"feedback_matrix_matches_A_plus_BK\":" << (feedback_matches ? "true" : "false") << ','
              << "\"rpi_inclusion_exactly_verified\":" << (invariant ? "true" : "false") << ','
              << "\"rpi_generator_matrix\":[[0,1],[1,-1]],"
              << "\"rpi_generator_radius\":" << disturbance_radius << ','
              << "\"state_constraints\":[[-1,1],[-1,1]],"
              << "\"input_constraints\":[-1,1],"
              << "\"state_tightening_support\":[" << state_support[0] << ',' << state_support[1] << "],"
              << "\"tightened_state_bounds\":[[" << -tightened_state[0] << ',' << tightened_state[0]
              << "],[" << -tightened_state[1] << ',' << tightened_state[1] << "]],"
              << "\"input_tightening_support\":" << input_support << ','
              << "\"tightened_input_bounds\":[" << -tightened_input << ',' << tightened_input << "],"
              << "\"empty_tightening\":" << (empty_tightening ? "true" : "false") << ','
              << "\"empty_tightening_edge_case\":{\"state_box_bound\":"
              << empty_fixture_state_bound << ",\"empty_verified_by_support\":"
              << (edge_tightening_empty ? "true" : "false") << "},"
              << "\"unsafe_nominal_plan_edge_case\":{\"nominal_input\":"
              << unsafe_nominal_input << ",\"tube_error\":[" << unsafe_tube_error[0] << ','
              << unsafe_tube_error[1] << "],\"actual_input\":" << unsafe_actual_input
              << ",\"rejected_by_tightened_bound_and_exact_input_bound\":"
              << (unsafe_plan_rejected ? "true" : "false") << "},"
              << "\"initial_tube_membership\":" << (initial_in_tube ? "true" : "false") << ','
              << "\"nominal_plan_tightened_feasible\":"
              << (nominal_plan_tightened_feasible ? "true" : "false") << ','
              << "\"matched_reference\":{\"quantifier\":\"fixed nominal plan, all disturbance vertices\","
              << "\"disturbance_paths_checked\":" << checked_paths << ','
              << "\"all_paths_safe\":" << (all_paths_safe ? "true" : "false") << ','
              << "\"worst_state_coordinate_abs\":" << worst_state_abs << ','
              << "\"worst_feedback_input_abs\":" << worst_input_abs << "},"
              << "\"objective\":{\"kind\":\"not evaluated\",\"nominal optimum\":\"not claimed\","
              << "\"minimax cost\":\"not claimed\"},"
              << "\"approximation_comparison\":\"deferred behind issues 99 and 100\"}\n";
    return feedback_matches && nilpotent && invariant && !empty_tightening &&
                   edge_tightening_empty && unsafe_plan_rejected && initial_in_tube &&
                   nominal_plan_tightened_feasible && all_paths_safe
               ? EXIT_SUCCESS
               : EXIT_FAILURE;
}
