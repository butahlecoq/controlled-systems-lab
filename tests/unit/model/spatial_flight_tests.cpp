#include <ostream>
#include <doctest/doctest.h>
#include <csl/model/spatial_flight.hpp>
#include <csl/model/spatial_flight_catalogue.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <utility>

TEST_CASE("synthetic spatial flight has a valid trim and native Jacobians") {
    using namespace csl::model::spatial_flight;
    auto made = Model::make(synthetic_parameters());
    REQUIRE(std::holds_alternative<Model>(made));
    const auto &model = std::get<Model>(made);
    const State trim{100, 0, 0, 0, 0, 0, 0, 0, 0};
    const Control zero{0, 0, 0};
    const auto rates = model.rhs(trim, zero);
    REQUIRE(std::holds_alternative<State>(rates));
    const auto values = std::get<State>(rates);
    CHECK(std::abs(values.vx) < 1e-12);
    CHECK(std::abs(values.vy) < 1e-12);
    CHECK(std::abs(values.vz) < 1e-12);
    const auto linearization = model.linearize(trim, zero);
    REQUIRE(std::holds_alternative<Linearization>(linearization));
    CHECK(std::get<Linearization>(linearization).state.rows == 9);
    CHECK(std::get<Linearization>(linearization).state.cols == 9);
    CHECK(std::get<Linearization>(linearization).control.rows == 9);
    CHECK(std::get<Linearization>(linearization).control.cols == 3);
}

TEST_CASE("spatial flight refuses states outside its operating domain") {
    using namespace csl::model::spatial_flight;
    auto model = std::get<Model>(Model::make(synthetic_parameters()));
    State invalid{0.5, 0, 0, 0, 0, 0, 0, 0, 0};
    CHECK(std::holds_alternative<csl::Diagnostics>(model.rhs(invalid, {0, 0, 0})));
    invalid.vx = 100;
    invalid.psi = 1.4;
    CHECK(std::holds_alternative<csl::Diagnostics>(model.linearize(invalid, {0, 0, 0})));
    invalid.psi = 0;
    invalid.vx = std::numeric_limits<double>::max();
    CHECK(std::holds_alternative<csl::Diagnostics>(model.rhs(invalid, {0, 0, 0})));
}

TEST_CASE("spatial Jacobian matches independent differences and Taylor scaling") {
    using namespace csl::model::spatial_flight;
    const auto model = std::get<Model>(Model::make(synthetic_parameters()));
    const State x{96.0, 2.4, -1.7, 0.11, -0.08, 0.23, 0.04, -0.03, 0.02};
    const Control u{0.015, -0.021, 0.017};
    const auto linearized = std::get<Linearization>(model.linearize(x, u));
    const double step = 2e-6;
    const std::array<double, 12> base{x.vx,      x.vy,      x.vz,      x.phi, x.psi, x.theta,
                                      x.omega_x, x.omega_y, x.omega_z, u.u0,  u.u1,  u.u2};
    for (std::size_t column = 0; column < 12; ++column) {
        auto plus = base, minus = base;
        plus[column] += step;
        minus[column] -= step;
        const State xp{plus[0], plus[1], plus[2], plus[3], plus[4],
                       plus[5], plus[6], plus[7], plus[8]};
        const State xm{minus[0], minus[1], minus[2], minus[3], minus[4],
                       minus[5], minus[6], minus[7], minus[8]};
        const Control up{plus[9], plus[10], plus[11]}, um{minus[9], minus[10], minus[11]};
        const auto fp = std::get<State>(model.rhs(xp, up));
        const auto fm = std::get<State>(model.rhs(xm, um));
        const double yp[]{fp.vx,    fp.vy,      fp.vz,      fp.phi,    fp.psi,
                          fp.theta, fp.omega_x, fp.omega_y, fp.omega_z};
        const double ym[]{fm.vx,    fm.vy,      fm.vz,      fm.phi,    fm.psi,
                          fm.theta, fm.omega_x, fm.omega_y, fm.omega_z};
        for (std::size_t row = 0; row < 9; ++row) {
            const double numerical = (yp[row] - ym[row]) / (2 * step);
            const double automatic = column < 9 ? linearized.state.values[row * 9 + column]
                                                : linearized.control.values[row * 3 + column - 9];
            CHECK(numerical == doctest::Approx(automatic).epsilon(2e-6).scale(1e-7));
        }
    }
    const double direction[]{0.03, -0.02, 0.01, 2e-4, -1e-4, 1.5e-4,
                             4e-5, -3e-5, 2e-5, 2e-4, -1e-4, 1.2e-4};
    auto shifted = [&](double scale) {
        return std::pair{State{x.vx + scale * direction[0], x.vy + scale * direction[1],
                               x.vz + scale * direction[2], x.phi + scale * direction[3],
                               x.psi + scale * direction[4], x.theta + scale * direction[5],
                               x.omega_x + scale * direction[6], x.omega_y + scale * direction[7],
                               x.omega_z + scale * direction[8]},
                         Control{u.u0 + scale * direction[9], u.u1 + scale * direction[10],
                                 u.u2 + scale * direction[11]}};
    };
    auto remainder = [&](double scale) {
        const auto [state, control] = shifted(scale);
        const auto actual = std::get<State>(model.rhs(state, control));
        const double actual_values[]{actual.vx,      actual.vy,      actual.vz,
                                     actual.phi,     actual.psi,     actual.theta,
                                     actual.omega_x, actual.omega_y, actual.omega_z};
        const double center[]{
            linearized.rates.vx,      linearized.rates.vy,      linearized.rates.vz,
            linearized.rates.phi,     linearized.rates.psi,     linearized.rates.theta,
            linearized.rates.omega_x, linearized.rates.omega_y, linearized.rates.omega_z};
        double maximum = 0;
        for (std::size_t row = 0; row < 9; ++row) {
            double prediction = center[row];
            for (std::size_t col = 0; col < 9; ++col)
                prediction += linearized.state.values[row * 9 + col] * scale * direction[col];
            for (std::size_t col = 0; col < 3; ++col)
                prediction += linearized.control.values[row * 3 + col] * scale * direction[9 + col];
            maximum = std::max(maximum, std::abs(actual_values[row] - prediction));
        }
        return maximum;
    };
    const double coarse = remainder(1.0), fine = remainder(0.5);
    CHECK(coarse > 0);
    CHECK(fine < 0.3 * coarse);
}

TEST_CASE("spatial model construction rejects invalid authored parameters") {
    using namespace csl::model::spatial_flight;
    auto parameters = synthetic_parameters();
    parameters.mass = 0;
    CHECK(std::holds_alternative<csl::Diagnostics>(Model::make(parameters)));
    parameters = synthetic_parameters();
    parameters.moment_control[4] = std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<csl::Diagnostics>(Model::make(parameters)));
}

TEST_CASE("B-consistent passive attitude matrix satisfies the nonzero-angle rate identity") {
    using namespace csl::model::spatial_flight;
    for (const std::array<double, 3> angles :
         {std::array{0.23, -0.17, 0.31}, std::array{-0.35, 0.28, -0.4}}) {
        const std::array<double, 3> rate{0.03, -0.04, 0.05};
        const auto b = body_from_inertial(angles[0], angles[1], angles[2]);
        const double determinant =
            b.values[0] * (b.values[4] * b.values[8] - b.values[5] * b.values[7]) -
            b.values[1] * (b.values[3] * b.values[8] - b.values[5] * b.values[6]) +
            b.values[2] * (b.values[3] * b.values[7] - b.values[4] * b.values[6]);
        CHECK(determinant == doctest::Approx(1).epsilon(1e-14));
        CHECK(determinant > 0);
        double orthogonality = 0;
        for (std::size_t i = 0; i < 3; ++i)
            for (std::size_t j = 0; j < 3; ++j) {
                double product = 0;
                for (std::size_t k = 0; k < 3; ++k)
                    product += b.values[i * 3 + k] * b.values[j * 3 + k];
                orthogonality = std::max(orthogonality, std::abs(product - (i == j ? 1.0 : 0.0)));
            }
        CHECK(orthogonality < 5e-16);
        const double h = 1e-5;
        const auto plus = body_from_inertial(angles[0] + h * rate[0], angles[1] + h * rate[1],
                                             angles[2] + h * rate[2]);
        const auto minus = body_from_inertial(angles[0] - h * rate[0], angles[1] - h * rate[1],
                                              angles[2] - h * rate[2]);
        const double omega_x = rate[0] - rate[2] * std::sin(angles[1]);
        const double omega_y =
            rate[1] * std::cos(angles[0]) + rate[2] * std::cos(angles[1]) * std::sin(angles[0]);
        const double omega_z =
            -rate[1] * std::sin(angles[0]) + rate[2] * std::cos(angles[1]) * std::cos(angles[0]);
        const double omega_printed_x = rate[0] - rate[2] * std::sin(angles[2]);
        const double omega_printed_y =
            rate[1] * std::cos(angles[0]) + rate[2] * std::cos(angles[1]) * std::sin(angles[1]);
        const double omega_printed_z = omega_z;
        auto residual = [&](double wx, double wy, double wz) {
            const double omega[3][3]{{0, -wz, wy}, {wz, 0, -wx}, {-wy, wx, 0}};
            double maximum = 0;
            for (std::size_t i = 0; i < 3; ++i)
                for (std::size_t j = 0; j < 3; ++j) {
                    const double derivative =
                        (plus.values[i * 3 + j] - minus.values[i * 3 + j]) / (2 * h);
                    double product = 0;
                    for (std::size_t k = 0; k < 3; ++k)
                        product += omega[i][k] * b.values[k * 3 + j];
                    maximum = std::max(maximum, std::abs(derivative + product));
                }
            return maximum;
        };
        CHECK(residual(omega_x, omega_y, omega_z) < 1e-10);
        CHECK(residual(omega_printed_x, omega_printed_y, omega_printed_z) > 1e-3);

        const auto model = std::get<Model>(Model::make(synthetic_parameters()));
        double inverse_map[3][3]{};
        for (std::size_t column = 0; column < 3; ++column) {
            std::array<double, 3> omega{};
            omega[column] = 1;
            const State state{100,       0,        0,        angles[0], angles[1],
                              angles[2], omega[0], omega[1], omega[2]};
            const auto rates = std::get<State>(model.rhs(state, {0, 0, 0}));
            const double euler_rate[]{rates.phi, rates.psi, rates.theta};
            for (std::size_t row = 0; row < 3; ++row)
                inverse_map[row][column] = euler_rate[row];
        }
        const double inverse_rate_determinant =
            inverse_map[0][0] *
                (inverse_map[1][1] * inverse_map[2][2] - inverse_map[1][2] * inverse_map[2][1]) -
            inverse_map[0][1] *
                (inverse_map[1][0] * inverse_map[2][2] - inverse_map[1][2] * inverse_map[2][0]) +
            inverse_map[0][2] *
                (inverse_map[1][0] * inverse_map[2][1] - inverse_map[1][1] * inverse_map[2][0]);
        CHECK(inverse_rate_determinant == doctest::Approx(1 / std::cos(angles[1])).epsilon(1e-14));
        CHECK(inverse_rate_determinant * std::cos(angles[1]) == doctest::Approx(1).epsilon(1e-14));
    }
}

TEST_CASE("rigid-body coupling does zero work and forces and moments use mass and inertia") {
    using namespace csl;
    using namespace csl::model::spatial_flight;
    auto p = synthetic_parameters();
    p.thrust = 0;
    p.cx0 = p.cx_alpha_squared = p.cx_beta_squared = 0;
    p.cy0 = p.cy_alpha = p.cy_beta = p.cy_u1 = p.cy_u2 = 0;
    p.cz_beta = p.cz_alpha = p.cz_u1 = p.cz_u2 = 0;
    p.moment_alpha = {0, 0, 0};
    p.moment_beta = {0, 0, 0};
    p.moment_rate.fill(0);
    p.moment_control.fill(0);
    const auto model = std::get<Model>(Model::make(p));
    const State moving{40, 3, 4, 0.1, -0.12, 0.3, 0.7, -0.4, 0.2};
    const auto derivative = std::get<State>(model.rhs(moving, {0, 0, 0}));
    const auto rotation = body_from_inertial(moving.phi, moving.psi, moving.theta);
    const double gx = -p.gravity * rotation.values[1], gy = -p.gravity * rotation.values[4],
                 gz = -p.gravity * rotation.values[7];
    CHECK(moving.vx * (derivative.vx - gx) + moving.vy * (derivative.vy - gy) +
              moving.vz * (derivative.vz - gz) ==
          doctest::Approx(0).epsilon(1e-12));
    CHECK(p.principal_inertia[0] * moving.omega_x * derivative.omega_x +
              p.principal_inertia[1] * moving.omega_y * derivative.omega_y +
              p.principal_inertia[2] * moving.omega_z * derivative.omega_z ==
          doctest::Approx(0).epsilon(1e-12));

    p.cx0 = 0.2;
    const auto light = std::get<Model>(Model::make(p));
    auto heavier_parameters = p;
    heavier_parameters.mass *= 2;
    const auto heavier = std::get<Model>(Model::make(heavier_parameters));
    const State straight{40, 0, 0, 0, 0, 0, 0, 0, 0};
    const auto light_force = std::get<State>(light.rhs(straight, {0, 0, 0}));
    const auto heavy_force = std::get<State>(heavier.rhs(straight, {0, 0, 0}));
    CHECK(heavy_force.vx == doctest::Approx(light_force.vx / 2));

    p.cx0 = 0;
    p.moment_control[0] = 1;
    const auto nominal_inertia = std::get<Model>(Model::make(p));
    auto greater_inertia_parameters = p;
    greater_inertia_parameters.principal_inertia[0] *= 2;
    const auto greater_inertia = std::get<Model>(Model::make(greater_inertia_parameters));
    const auto nominal_moment = std::get<State>(nominal_inertia.rhs(straight, {0.1, 0, 0}));
    const auto halved_acceleration = std::get<State>(greater_inertia.rhs(straight, {0.1, 0, 0}));
    CHECK(halved_acceleration.omega_x == doctest::Approx(nominal_moment.omega_x / 2));
}

TEST_CASE("native spatial-flight reference yields a 9-state deviation LTV case") {
    using namespace csl;
    using namespace csl::model;
    using namespace csl::model::catalogue;
    REQUIRE(spatial_flight_cases().size() == 1);
    const auto &info = spatial_flight_cases().front();
    CHECK(info.id == "spatial-flight/b-consistent-body9-synthetic/1");
    CHECK(info.states.size() == 9);
    CHECK(info.controls.size() == 3);
    CHECK(info.transitions == 20);
    auto result = make_spatial_flight_case(info.id);
    REQUIRE(std::holds_alternative<SpatialFlightCase>(result));
    const auto &data = std::get<SpatialFlightCase>(result);
    const auto &reach = data.reachability;
    CHECK((reach.model.dynamics.dimensions == Dimensions{9, 3, 0}));
    REQUIRE(reach.time_grid.size() == 21);
    CHECK(reach.time_grid.front() == 0);
    CHECK(reach.time_grid.back() == doctest::Approx(1.0));
    CHECK(data.reference.size() == 21);
    CHECK(data.reference.front().vx == 100);
    CHECK(data.reference_integration.intervals == 20);
    CHECK(data.reference_integration.substeps_per_interval == 10);
    CHECK(data.reference_integration.rhs_evaluations == 800);
    CHECK(data.discretization.stages.size() == 20);
    CHECK(data.discretization.hold == HoldConvention::zero_order_hold);
    CHECK(data.discretization.variation == CoefficientVariation::piecewise_linear_ltv);
    REQUIRE(reach.controls.size() == 20);
    CHECK(reach.initial.center() == Vector(9, 0));
    CHECK(reach.initial.generators().rows == 9);
    CHECK(reach.initial.generators().cols == 9);
    CHECK(reach.initial.generators().values[0] == doctest::Approx(0.1));
    for (const auto &control : reach.controls) {
        CHECK(control.center() == Vector(3, 0));
        CHECK(control.generators().rows == 3);
        CHECK(control.generators().cols == 3);
        CHECK(control.generators().values[0] == doctest::Approx(0.001));
    }
    CHECK(reach.controls.front().factor_ids().front() !=
          reach.controls.back().factor_ids().front());
    CHECK(reach.initial.factor_ids().front() != reach.controls.front().factor_ids().front());
    CHECK(data.reference.back().vy != data.reference.front().vy);
    CHECK(data.parameters.mass == 100);
    auto unknown = make_spatial_flight_case("spatial-flight/no-such-case/1");
    CHECK(std::holds_alternative<Diagnostics>(unknown));
}
