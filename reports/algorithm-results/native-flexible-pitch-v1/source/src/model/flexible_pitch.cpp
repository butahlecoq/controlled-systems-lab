#include <csl/model/flexible_pitch.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <numbers>

namespace csl::model::catalogue {
namespace {
constexpr Coordinate theta{"pitch_deviation", "rad"}, theta_rate{"pitch_rate", "rad/s"};
constexpr Coordinate y{"lateral_position_deviation", "m"}, vy{"lateral_velocity_deviation", "m/s"};
constexpr Coordinate s1{"bending_1", "m"}, v1{"bending_1_rate", "m/s"};
constexpr Coordinate s2{"bending_2", "m"}, v2{"bending_2_rate", "m/s"};
constexpr Coordinate s3{"bending_3", "m"}, v3{"bending_3_rate", "m/s"};
constexpr Coordinate s4{"bending_4", "m"}, v4{"bending_4_rate", "m/s"};
constexpr Coordinate b1{"slosh_1", "rad"}, w1{"slosh_1_rate", "rad/s"};
constexpr Coordinate b2{"slosh_2", "rad"}, w2{"slosh_2_rate", "rad/s"};
constexpr std::array states8{theta, theta_rate, y, vy, s1, v1, b1, w1};
constexpr std::array states12{theta, theta_rate, y, vy, s1, v1, s2, v2, b1, w1, b2, w2};
constexpr std::array states16{theta, theta_rate, y, vy, s1, v1, s2, v2, s3, v3, s4, v4, b1, w1, b2, w2};
constexpr std::array control{Coordinate{"pitch_control_deflection", "rad"}};
constexpr std::array operations{
    std::string_view{"csl::model::discretize"},
    std::string_view{"csl::model::snapshot"},
    std::string_view{"csl::geometry::generators::affine_image"},
    std::string_view{"csl::geometry::generators::minkowski_sum"}};
constexpr Source source{
    "Bulaev and Shorikov: optimal stabilization of an elastic mechanical object",
    "648d2c6690d7a20278f4d40dbbc15e4964452c46895fec42b17e33329755452d",
    "2016 Miass author DOCX, equations (3)-(6), Table 1; local rendering pages 4-9",
    "Paper-derived synthetic constant coefficients, initial box and 0.1-second grid. "
    "No Soyuz calibration or historical reproduction. y_dot=Vy explicitly closes lateral position. "
    "Forward sets use independent amplitude-bounded controls; rate-constrained stabilization is separate."};
constexpr std::array cases{
    CaseInfo{"flexible-pitch/synthetic-8-state/1", "Synthetic flexible pitch: one bending mode and one tank",
        states8, control, 40, "s", source, operations},
    CaseInfo{"flexible-pitch/synthetic-12-state/1", "Synthetic flexible pitch: two bending modes and two tanks",
        states12, control, 40, "s", source, operations},
    CaseInfo{"flexible-pitch/synthetic-16-state/1", "Synthetic flexible pitch: four bending modes and two tanks",
        states16, control, 40, "s", source, operations}};

Diagnostics reject(std::string field, std::string reason,
                   DiagnosticCode code = DiagnosticCode::invalid_input) {
    return {{code, std::move(field), std::move(reason)}};
}
bool finite(double value) { return std::isfinite(value); }
}

std::span<const CaseInfo> flexible_pitch_cases() noexcept { return cases; }

FlexiblePitchResult<FlexiblePitchParameters> flexible_pitch_parameters(std::string_view id) {
    const auto entry = std::find_if(cases.begin(), cases.end(),
        [id](const CaseInfo& info) { return info.id == id; });
    if (entry == cases.end())
        return reject("model.flexible_pitch.id", "Unknown synthetic flexible-pitch case.");
    const auto index = static_cast<std::size_t>(entry - cases.begin());
    const std::size_t bending_count = index == 0 ? 1 : index == 1 ? 2 : 4;
    const std::size_t tank_count = index == 0 ? 1 : 2;
    FlexiblePitchParameters result{0.08, 0.002, 0.4, -0.3, 0.04, -0.6, 0.08, {}, {}};
    for (std::size_t i = 0; i < bending_count; ++i) {
        const double mode = static_cast<double>(i + 1);
        result.bending.push_back({1.2 + 0.8 * mode, 0.05 / mode,
            0.015 / mode, 0.025 / mode});
    }
    for (std::size_t i = 0; i < tank_count; ++i) {
        const double mode = static_cast<double>(i + 1);
        const double frequency = 0.35 + 0.25 * mode;
        result.slosh.push_back({frequency * frequency, 0.05 + 0.03 * mode,
            0.025 / mode, 0.045 / mode, 0.02 / mode, 0.04 / mode, 0.012 / mode});
    }
    return result;
}

FlexiblePitchResult<FlexiblePitchDescriptor>
assemble_flexible_pitch(const FlexiblePitchParameters& p) {
    if (p.bending.size() > 30 || p.slosh.size() > 30 - p.bending.size())
        return reject("model.flexible_pitch.dimension", "At most 30 coupled mode pairs are supported.");
    const std::array rigid{p.pitch_stiffness, p.pitch_lateral_velocity, p.pitch_input,
        p.lateral_pitch, p.lateral_velocity_damping, p.lateral_input, p.bending_decrement};
    if (!std::all_of(rigid.begin(), rigid.end(), finite) || p.bending_decrement < 0)
        return reject("model.flexible_pitch.coefficients", "Finite rigid coefficients and nonnegative bending decrement are required.");
    for (const auto& mode : p.bending) {
        const std::array values{mode.frequency, mode.input_gain, mode.pitch_force, mode.lateral_force};
        if (!std::all_of(values.begin(), values.end(), finite) || mode.frequency <= 0 ||
            !finite(mode.frequency * mode.frequency))
            return reject("model.flexible_pitch.bending", "Finite bending data and a positive representable squared frequency are required.");
    }
    for (const auto& mode : p.slosh) {
        const std::array values{mode.frequency_squared, mode.damping, mode.pitch_acceleration,
            mode.lateral_acceleration, mode.lateral_feedback, mode.pitch_feedback, mode.pitch_position};
        if (!std::all_of(values.begin(), values.end(), finite) || mode.frequency_squared <= 0 || mode.damping < 0)
            return reject("model.flexible_pitch.slosh", "Finite slosh data, positive squared frequency and nonnegative damping are required.");
    }
    const auto n = 4 + 2 * (p.bending.size() + p.slosh.size());
    Matrix E{n, n, Vector(n * n, 0)}, A{n, n, Vector(n * n, 0)}, B{n, 1, Vector(n, 0)};
    for (std::size_t j = 0; j < n; ++j) E.values[j * n + j] = 1;
    A.values[1] = 1;
    A.values[n] = -p.pitch_stiffness;
    A.values[n + 3] = -p.pitch_lateral_velocity;
    B.values[1] = -p.pitch_input;
    A.values[2 * n + 3] = 1;
    A.values[3 * n] = -p.lateral_pitch;
    A.values[3 * n + 3] = -p.lateral_velocity_damping;
    B.values[3] = -p.lateral_input;
    for (std::size_t i = 0; i < p.bending.size(); ++i) {
        const auto j = 4 + 2 * i;
        const auto& mode = p.bending[i];
        A.values[j * n + j + 1] = 1;
        A.values[(j + 1) * n + j] = -mode.frequency * mode.frequency;
        A.values[(j + 1) * n + j + 1] = -p.bending_decrement * mode.frequency;
        B.values[j + 1] = mode.input_gain;
        A.values[n + j] = -mode.pitch_force;
        A.values[3 * n + j] = -mode.lateral_force;
    }
    for (std::size_t i = 0; i < p.slosh.size(); ++i) {
        const auto j = 4 + 2 * p.bending.size() + 2 * i;
        const auto& mode = p.slosh[i];
        A.values[j * n + j + 1] = 1;
        E.values[n + j + 1] = mode.pitch_acceleration;
        E.values[3 * n + j + 1] = -mode.lateral_acceleration;
        E.values[(j + 1) * n + 1] = mode.pitch_feedback;
        E.values[(j + 1) * n + 3] = -mode.lateral_feedback;
        A.values[n + j] = -mode.pitch_position;
        A.values[(j + 1) * n] = -mode.frequency_squared;
        A.values[(j + 1) * n + j] = -mode.frequency_squared;
        A.values[(j + 1) * n + j + 1] = -mode.damping;
    }
    const auto finite_values = [](const Vector& values) {
        return std::all_of(values.begin(), values.end(), finite);
    };
    if (!finite_values(A.values) || !finite_values(B.values))
        return reject("model.flexible_pitch.coefficients", "Derived implicit coefficients exceed binary64 range.");

    auto mass = E.values;
    const auto width = n + 1;
    Vector rhs(n * width), solved(n * width, 0);
    for (std::size_t i = 0; i < n; ++i) {
        std::copy_n(A.values.begin() + static_cast<std::ptrdiff_t>(i * n), n,
            rhs.begin() + static_cast<std::ptrdiff_t>(i * width));
        rhs[i * width + n] = B.values[i];
    }
    double scale = 1;
    for (const auto value : mass) scale = std::max(scale, std::abs(value));
    const double threshold = 64 * std::numeric_limits<double>::epsilon() * static_cast<double>(n);
    double minimum_pivot = std::numeric_limits<double>::infinity();
    for (std::size_t column = 0; column < n; ++column) {
        std::size_t pivot = column;
        for (std::size_t row = column + 1; row < n; ++row)
            if (std::abs(mass[row * n + column]) > std::abs(mass[pivot * n + column])) pivot = row;
        const auto magnitude = std::abs(mass[pivot * n + column]) / scale;
        if (!finite(magnitude) || magnitude <= threshold)
            return reject("model.flexible_pitch.mass_matrix", "Descriptor is singular or numerically unresolved; no explicit model was formed.", DiagnosticCode::unsupported);
        minimum_pivot = std::min(minimum_pivot, magnitude);
        if (pivot != column) {
            for (std::size_t j = 0; j < n; ++j) std::swap(mass[column * n + j], mass[pivot * n + j]);
            for (std::size_t j = 0; j < width; ++j) std::swap(rhs[column * width + j], rhs[pivot * width + j]);
        }
        for (std::size_t row = column + 1; row < n; ++row) {
            const double factor = mass[row * n + column] / mass[column * n + column];
            mass[row * n + column] = 0;
            for (std::size_t j = column + 1; j < n; ++j) mass[row * n + j] -= factor * mass[column * n + j];
            for (std::size_t j = 0; j < width; ++j) rhs[row * width + j] -= factor * rhs[column * width + j];
        }
    }
    for (std::size_t reverse = n; reverse > 0; --reverse) {
        const auto row = reverse - 1;
        for (std::size_t column = 0; column < width; ++column) {
            double value = rhs[row * width + column];
            for (std::size_t j = row + 1; j < n; ++j) value -= mass[row * n + j] * solved[j * width + column];
            solved[row * width + column] = value / mass[row * n + row];
        }
    }
    if (!finite_values(solved))
        return reject("model.flexible_pitch.mass_matrix", "Descriptor solve overflowed.", DiagnosticCode::unsupported);
    double residual = 0;
    for (std::size_t i = 0; i < n; ++i) for (std::size_t column = 0; column < width; ++column) {
        long double actual = 0, magnitude = 0;
        for (std::size_t j = 0; j < n; ++j) {
            const long double term = static_cast<long double>(E.values[i * n + j]) * solved[j * width + column];
            actual += term;
            magnitude += std::abs(term);
        }
        const double expected = column == n ? B.values[i] : A.values[i * n + column];
        residual = std::max(residual, static_cast<double>(std::abs(actual - expected) / (1 + magnitude + std::abs(expected))));
    }
    if (residual > 1e-12)
        return reject("model.flexible_pitch.mass_matrix", "Descriptor residual exceeded the numerical admission threshold.", DiagnosticCode::unsupported);
    LinearStage explicit_rates{{n, n, Vector(n * n)}, {n, 1, Vector(n)}, {n, 0, {}}, Vector(n, 0)};
    for (std::size_t i = 0; i < n; ++i) {
        std::copy_n(solved.begin() + static_cast<std::ptrdiff_t>(i * width), n,
            explicit_rates.A.values.begin() + static_cast<std::ptrdiff_t>(i * n));
        explicit_rates.B.values[i] = solved[i * width + n];
    }
    return FlexiblePitchDescriptor{std::move(E), std::move(A), std::move(B), std::move(explicit_rates), minimum_pivot, residual};
}

FlexiblePitchResult<FlexiblePitchCase> make_flexible_pitch_case(std::string_view id) {
    auto parameter_result = flexible_pitch_parameters(id);
    if (const auto* error = std::get_if<Diagnostics>(&parameter_result)) return *error;
    auto parameters = std::get<FlexiblePitchParameters>(std::move(parameter_result));
    auto descriptor_result = assemble_flexible_pitch(parameters);
    if (const auto* error = std::get_if<Diagnostics>(&descriptor_result)) return *error;
    auto descriptor = std::get<FlexiblePitchDescriptor>(std::move(descriptor_result));
    const auto entry = std::find_if(cases.begin(), cases.end(),
        [id](const CaseInfo& info) { return info.id == id; });
    const auto n = entry->states.size();
    Vector times(entry->transitions + 1);
    for (std::size_t k = 0; k < times.size(); ++k) times[k] = 0.1 * static_cast<double>(k);
    auto discrete_result = discretize({{n, 1, 0}, times, HoldConvention::zero_order_hold,
        descriptor.rates});
    if (const auto* error = std::get_if<Diagnostic>(&discrete_result)) return Diagnostics{*error};
    if (const auto* stopped = std::get_if<OperationStopped>(&discrete_result))
        return reject("model.flexible_pitch.discretization", stopped->diagnostics);
    auto discrete = std::get<DiscretizedModel>(std::move(discrete_result));
    constexpr double radians = std::numbers::pi / 180;
    Vector radii{0.2 * radians, 0.05 * radians, 0.2, 0.02};
    for (std::size_t i = 0; i < parameters.bending.size(); ++i) {
        radii.push_back(0.0005); radii.push_back(0.001);
    }
    for (std::size_t i = 0; i < parameters.slosh.size(); ++i) {
        radii.push_back(0.001); radii.push_back(0.002);
    }
    const std::string prefix(id);
    Matrix generators{n, n, Vector(n * n, 0)};
    std::vector<sets::FactorId> factors;
    std::vector<std::string> labels;
    for (std::size_t j = 0; j < n; ++j) {
        generators.values[j * n + j] = radii[j];
        labels.emplace_back(entry->states[j].name);
        factors.push_back({prefix + "/initial/" + labels.back()});
    }
    auto initial_result = sets::make_generator_set({{prefix + "/initial"}, Vector(n, 0),
        std::move(generators), std::move(factors), {0, n, {}}, {}, std::move(labels)});
    if (const auto* error = std::get_if<Diagnostics>(&initial_result)) return *error;
    std::vector<sets::GeneratorSet> inputs;
    for (std::size_t k = 0; k < entry->transitions; ++k) {
        const auto stage = prefix + "/control/" + std::to_string(k);
        auto input = sets::make_generator_set({{stage}, {0}, {1, 1, {4 * radians}},
            {{stage + "/delta"}}, {0, 1, {}}, {}, {"pitch_control_deflection"}});
        if (const auto* error = std::get_if<Diagnostics>(&input)) return *error;
        inputs.push_back(std::get<sets::GeneratorSet>(std::move(input)));
    }
    DiscreteReachabilityCase reach{*entry, std::move(discrete.model), std::move(times),
        std::get<sets::GeneratorSet>(std::move(initial_result)), std::move(inputs)};
    return FlexiblePitchCase{std::move(reach), std::move(parameters),
        std::move(descriptor), std::move(discrete.receipt)};
}

} // namespace csl::model::catalogue
