#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/flexible_pitch.hpp>
#include <csl/model/linear_system.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace {
template <class T, class... Errors> T take(std::variant<T, Errors...> value) {
    if constexpr (std::is_constructible_v<std::variant<T, Errors...>, csl::Diagnostics>) {
        if (const auto *errors = std::get_if<csl::Diagnostics>(&value))
            for (const auto &error : *errors)
                FAIL(error.field << ": " << error.explanation);
    }
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
}

TEST_CASE("synthetic flexible pitch ladder retains the source acceleration couplings") {
    using namespace csl;
    using namespace csl::model::catalogue;
    const auto cases = flexible_pitch_cases();
    REQUIRE(cases.size() == 3);
    const std::size_t dimensions[]{8, 12, 16};
    for (std::size_t entry = 0; entry < cases.size(); ++entry) {
        const auto parameters = take(flexible_pitch_parameters(cases[entry].id));
        const auto descriptor = take(assemble_flexible_pitch(parameters));
        const auto n = dimensions[entry];
        REQUIRE(descriptor.mass.rows == n);
        REQUIRE(descriptor.mass.cols == n);
        CHECK(cases[entry].states.size() == n);
        CHECK(n == 4 + 2 * (parameters.bending.size() + parameters.slosh.size()));
        CHECK(cases[entry].source.sha256 ==
              "648d2c6690d7a20278f4d40dbbc15e4964452c46895fec42b17e33329755452d");
        CHECK(cases[entry].source.qualification.find("synthetic") != std::string_view::npos);
        CHECK(descriptor.minimum_scaled_pivot > 0.9);
        CHECK(descriptor.maximum_relative_residual < 1e-12);

        Vector x(n), rate(n, 0);
        for (std::size_t i = 0; i < n; ++i)
            x[i] = 0.001 * static_cast<double>(i + 1);
        constexpr double input = 0.02;
        for (std::size_t i = 0; i < n; ++i) {
            rate[i] = descriptor.rates.B.values[i] * input;
            for (std::size_t j = 0; j < n; ++j)
                rate[i] += descriptor.rates.A.values[i * n + j] * x[j];
        }
        CHECK(rate[0] == doctest::Approx(x[1]));
        CHECK(rate[2] == doctest::Approx(x[3]));
        double pitch = rate[1] + parameters.pitch_stiffness * x[0] +
                       parameters.pitch_lateral_velocity * x[3] + parameters.pitch_input * input;
        double lateral = rate[3] + parameters.lateral_pitch * x[0] +
                         parameters.lateral_velocity_damping * x[3] +
                         parameters.lateral_input * input;
        for (std::size_t mode = 0; mode < parameters.bending.size(); ++mode) {
            const auto j = 4 + 2 * mode;
            const auto &b = parameters.bending[mode];
            pitch += b.pitch_force * x[j];
            lateral += b.lateral_force * x[j];
            CHECK(rate[j] == doctest::Approx(x[j + 1]));
            CHECK(rate[j + 1] + parameters.bending_decrement * b.frequency * x[j + 1] +
                      b.frequency * b.frequency * x[j] ==
                  doctest::Approx(b.input_gain * input));
            CHECK(descriptor.implicit_state.values[n + j] != 0);
            CHECK(descriptor.implicit_state.values[3 * n + j] != 0);
        }
        for (std::size_t mode = 0; mode < parameters.slosh.size(); ++mode) {
            const auto j = 4 + 2 * parameters.bending.size() + 2 * mode;
            const auto &s = parameters.slosh[mode];
            pitch += s.pitch_acceleration * rate[j + 1] + s.pitch_position * x[j];
            lateral -= s.lateral_acceleration * rate[j + 1];
            CHECK(rate[j] == doctest::Approx(x[j + 1]));
            CHECK(rate[j + 1] + s.damping * x[j + 1] + s.frequency_squared * x[j] ==
                  doctest::Approx(s.lateral_feedback * rate[3] - s.pitch_feedback * rate[1] -
                                  s.frequency_squared * x[0]));
            CHECK(descriptor.mass.values[n + j + 1] == s.pitch_acceleration);
            CHECK(descriptor.mass.values[3 * n + j + 1] == -s.lateral_acceleration);
            CHECK(descriptor.mass.values[(j + 1) * n + 1] == s.pitch_feedback);
            CHECK(descriptor.mass.values[(j + 1) * n + 3] == -s.lateral_feedback);
        }
        CHECK(std::abs(pitch) < 1e-12);
        CHECK(std::abs(lateral) < 1e-12);
    }
}

TEST_CASE("flexible pitch rejects a singular descriptor before explicit dynamics") {
    using namespace csl;
    using namespace csl::model::catalogue;
    auto parameters = take(flexible_pitch_parameters(flexible_pitch_cases()[0].id));
    auto &slosh = parameters.slosh[0];
    slosh.pitch_acceleration = 1;
    slosh.pitch_feedback = 1;
    slosh.lateral_acceleration = 0;
    slosh.lateral_feedback = 0;
    const auto singular = assemble_flexible_pitch(parameters);
    REQUIRE(std::holds_alternative<Diagnostics>(singular));
    CHECK(std::get<Diagnostics>(singular)[0].field == "model.flexible_pitch.mass_matrix");
    parameters = take(flexible_pitch_parameters(flexible_pitch_cases()[0].id));
    parameters.bending[0].frequency = 0;
    CHECK(std::holds_alternative<Diagnostics>(assemble_flexible_pitch(parameters)));
    parameters.pitch_input = std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<Diagnostics>(assemble_flexible_pitch(parameters)));
    CHECK(std::holds_alternative<Diagnostics>(flexible_pitch_parameters("missing-flexible-case")));
}

TEST_CASE("flexible pitch catalogue executes physical-time zero-order hold cases") {
    using namespace csl;
    using namespace csl::model::catalogue;
    const auto catalogue = discrete_reachability_cases();
    for (const auto &info : flexible_pitch_cases()) {
        CHECK(std::count_if(catalogue.begin(), catalogue.end(),
                            [&](const CaseInfo &entry) { return entry.id == info.id; }) == 1);
        const auto data = take(make_flexible_pitch_case(info.id));
        const auto &reach = data.reachability;
        CHECK(reach.info.id == info.id);
        REQUIRE(reach.time_grid.size() == 41);
        CHECK(reach.time_grid.front() == 0);
        CHECK(reach.time_grid.back() == 4);
        REQUIRE(reach.controls.size() == 40);
        CHECK(reach.initial.center().size() == info.states.size());
        CHECK(data.discretization.stages.size() == 40);
        CHECK(data.discretization.hold == model::HoldConvention::zero_order_hold);
        CHECK(data.discretization.variation == model::CoefficientVariation::constant_lti);
        CHECK(take(make_discrete_reachability_case(info.id)).info.id == info.id);
    }
}

TEST_CASE("flexible pitch ZOH agrees with an independent augmented matrix exponential") {
    using namespace csl;
    using namespace csl::model::catalogue;
    for (const auto &info : flexible_pitch_cases()) {
        const auto data = take(make_flexible_pitch_case(info.id));
        const auto n = info.states.size(), m = n + 1;
        // Long-double Taylor series of exp(h*[A B; 0 0]), independent of RK4.
        std::vector<long double> generator(m * m, 0), term(m * m, 0), sum(m * m, 0);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j)
                generator[i * m + j] = 0.1L * data.descriptor.rates.A.values[i * n + j];
            generator[i * m + n] = 0.1L * data.descriptor.rates.B.values[i];
        }
        for (std::size_t i = 0; i < m; ++i)
            term[i * m + i] = sum[i * m + i] = 1;
        for (std::size_t order = 1; order <= 40; ++order) {
            std::vector<long double> next(m * m, 0);
            for (std::size_t i = 0; i < m; ++i)
                for (std::size_t j = 0; j < m; ++j)
                    for (std::size_t k = 0; k < m; ++k)
                        next[i * m + j] += term[i * m + k] * generator[k * m + j] /
                                           static_cast<long double>(order);
            term = std::move(next);
            for (std::size_t i = 0; i < sum.size(); ++i)
                sum[i] += term[i];
        }
        const auto system =
            take(model::snapshot(data.reachability.model, data.reachability.time_grid));
        for (std::size_t k = 0; k < system.horizon(); ++k) {
            const auto stage = take(system.stage({k}));
            for (std::size_t i = 0; i < n; ++i) {
                for (std::size_t j = 0; j < n; ++j)
                    CHECK(std::abs(stage.A(i, j) - sum[i * m + j]) < 2e-9L);
                CHECK(std::abs(stage.B(i, 0) - sum[i * m + n]) < 2e-9L);
            }
        }
    }
}

TEST_CASE("descriptor residuals outside the checking precision never become a finite admission") {
    using namespace csl;
    using namespace csl::model::catalogue;
    auto parameters = take(flexible_pitch_parameters("flexible-pitch/synthetic-12-state/1"));
    parameters.pitch_input = 0.8 * std::numeric_limits<double>::max();
    for (auto &tank : parameters.slosh) {
        tank.pitch_feedback = 0.5;
        tank.lateral_feedback = 0;
        tank.lateral_acceleration = 0;
    }
    parameters.slosh[0].pitch_acceleration = -1;
    parameters.slosh[1].pitch_acceleration = 1;
    // The finite solution has theta_B=-M and both tank_B=M/2. Reconstructing
    // its pitch row visits -M-M/2+M/2, beyond double's intermediate range.
    const auto result = assemble_flexible_pitch(parameters);
    if constexpr (std::numeric_limits<long double>::max_exponent ==
                  std::numeric_limits<double>::max_exponent) {
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        const auto &error = std::get<Diagnostics>(result).front();
        CHECK(error.code == DiagnosticCode::unsupported);
        CHECK(error.field == "model.flexible_pitch.mass_matrix");
        CHECK(error.explanation.find("residual") != std::string::npos);
    } else {
        REQUIRE(std::holds_alternative<FlexiblePitchDescriptor>(result));
        const auto &descriptor = std::get<FlexiblePitchDescriptor>(result);
        CHECK(std::isfinite(descriptor.maximum_relative_residual));
        CHECK(descriptor.maximum_relative_residual < 1e-12);
        for (const auto value : descriptor.rates.B.values)
            CHECK(std::isfinite(value));
    }
}
