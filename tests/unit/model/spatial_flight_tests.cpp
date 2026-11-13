#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/spatial_flight.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <utility>

TEST_CASE("synthetic spatial flight has a valid trim and native Jacobians") {
    using namespace csl::model::spatial_flight;
    auto made = Model::make(synthetic_parameters());
    REQUIRE(std::holds_alternative<Model>(made));
    const auto& model = std::get<Model>(made);
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
    const std::array<double,12> base{x.vx,x.vy,x.vz,x.phi,x.psi,x.theta,x.omega_x,x.omega_y,x.omega_z,u.u0,u.u1,u.u2};
    for (std::size_t column=0; column<12; ++column) {
        auto plus=base, minus=base;
        plus[column]+=step; minus[column]-=step;
        const State xp{plus[0],plus[1],plus[2],plus[3],plus[4],plus[5],plus[6],plus[7],plus[8]};
        const State xm{minus[0],minus[1],minus[2],minus[3],minus[4],minus[5],minus[6],minus[7],minus[8]};
        const Control up{plus[9],plus[10],plus[11]}, um{minus[9],minus[10],minus[11]};
        const auto fp=std::get<State>(model.rhs(xp,up));
        const auto fm=std::get<State>(model.rhs(xm,um));
        const double yp[]{fp.vx,fp.vy,fp.vz,fp.phi,fp.psi,fp.theta,fp.omega_x,fp.omega_y,fp.omega_z};
        const double ym[]{fm.vx,fm.vy,fm.vz,fm.phi,fm.psi,fm.theta,fm.omega_x,fm.omega_y,fm.omega_z};
        for (std::size_t row=0; row<9; ++row) {
            const double numerical=(yp[row]-ym[row])/(2*step);
            const double automatic=column<9 ? linearized.state.values[row*9+column]
                : linearized.control.values[row*3+column-9];
            CHECK(numerical == doctest::Approx(automatic).epsilon(2e-6).scale(1e-7));
        }
    }
    const double direction[]{0.03,-0.02,0.01,2e-4,-1e-4,1.5e-4,4e-5,-3e-5,2e-5,2e-4,-1e-4,1.2e-4};
    auto shifted = [&](double scale) {
        return std::pair{State{x.vx+scale*direction[0],x.vy+scale*direction[1],x.vz+scale*direction[2],
            x.phi+scale*direction[3],x.psi+scale*direction[4],x.theta+scale*direction[5],
            x.omega_x+scale*direction[6],x.omega_y+scale*direction[7],x.omega_z+scale*direction[8]},
            Control{u.u0+scale*direction[9],u.u1+scale*direction[10],u.u2+scale*direction[11]}};
    };
    auto remainder = [&](double scale) {
        const auto [state, control]=shifted(scale);
        const auto actual=std::get<State>(model.rhs(state,control));
        const double actual_values[]{actual.vx,actual.vy,actual.vz,actual.phi,actual.psi,actual.theta,actual.omega_x,actual.omega_y,actual.omega_z};
        const double center[]{linearized.rates.vx,linearized.rates.vy,linearized.rates.vz,linearized.rates.phi,linearized.rates.psi,linearized.rates.theta,linearized.rates.omega_x,linearized.rates.omega_y,linearized.rates.omega_z};
        double maximum=0;
        for (std::size_t row=0;row<9;++row) {
            double prediction=center[row];
            for (std::size_t col=0;col<9;++col) prediction+=linearized.state.values[row*9+col]*scale*direction[col];
            for (std::size_t col=0;col<3;++col) prediction+=linearized.control.values[row*3+col]*scale*direction[9+col];
            maximum=std::max(maximum,std::abs(actual_values[row]-prediction));
        }
        return maximum;
    };
    const double coarse=remainder(1.0), fine=remainder(0.5);
    CHECK(coarse > 0);
    CHECK(fine < 0.3*coarse);
}

TEST_CASE("spatial model construction rejects invalid authored parameters") {
    using namespace csl::model::spatial_flight;
    auto parameters=synthetic_parameters();
    parameters.mass=0;
    CHECK(std::holds_alternative<csl::Diagnostics>(Model::make(parameters)));
    parameters=synthetic_parameters();
    parameters.moment_control[4]=std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<csl::Diagnostics>(Model::make(parameters)));
}

TEST_CASE("B-consistent passive attitude matrix satisfies the nonzero-angle rate identity") {
    using namespace csl::model::spatial_flight;
    for (const std::array<double,3> angles : {std::array{0.23,-0.17,0.31},std::array{-0.35,0.28,-0.4}}) {
        const std::array<double,3> rate{0.03,-0.04,0.05};
        const auto b=body_from_inertial(angles[0],angles[1],angles[2]);
        double orthogonality=0;
        for (std::size_t i=0;i<3;++i) for (std::size_t j=0;j<3;++j) {
            double product=0;
            for (std::size_t k=0;k<3;++k) product+=b.values[i*3+k]*b.values[j*3+k];
            orthogonality=std::max(orthogonality,std::abs(product-(i==j ? 1.0 : 0.0)));
        }
        CHECK(orthogonality < 5e-16);
        const double h=1e-5;
        const auto plus=body_from_inertial(angles[0]+h*rate[0],angles[1]+h*rate[1],angles[2]+h*rate[2]);
        const auto minus=body_from_inertial(angles[0]-h*rate[0],angles[1]-h*rate[1],angles[2]-h*rate[2]);
        const double omega_x=rate[0]-rate[2]*std::sin(angles[1]);
        const double omega_y=rate[1]*std::cos(angles[0])+rate[2]*std::cos(angles[1])*std::sin(angles[0]);
        const double omega_z=-rate[1]*std::sin(angles[0])+rate[2]*std::cos(angles[1])*std::cos(angles[0]);
        const double omega_printed_x=rate[0]-rate[2]*std::sin(angles[2]);
        const double omega_printed_y=rate[1]*std::cos(angles[0])+rate[2]*std::cos(angles[1])*std::sin(angles[1]);
        const double omega_printed_z=omega_z;
        auto residual=[&](double wx,double wy,double wz) {
            const double omega[3][3]{{0,-wz,wy},{wz,0,-wx},{-wy,wx,0}};
            double maximum=0;
            for (std::size_t i=0;i<3;++i) for (std::size_t j=0;j<3;++j) {
                const double derivative=(plus.values[i*3+j]-minus.values[i*3+j])/(2*h);
                double product=0;
                for (std::size_t k=0;k<3;++k) product+=omega[i][k]*b.values[k*3+j];
                maximum=std::max(maximum,std::abs(derivative+product));
            }
            return maximum;
        };
        CHECK(residual(omega_x,omega_y,omega_z) < 1e-10);
        CHECK(residual(omega_printed_x,omega_printed_y,omega_printed_z) > 1e-3);
    }
}
