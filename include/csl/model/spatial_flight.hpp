#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/values.hpp>
#include <array>
#include <utility>
#include <variant>

namespace csl::model::spatial_flight {

struct State {
    double vx, vy, vz;
    double phi, psi, theta;
    double omega_x, omega_y, omega_z;
};
// Synthetic allocation is zero-based: u0 acts through moments; u1 and u2 act
// through both Cy/Cz and moments. These are not recovered hardware controls.
struct Control { double u0, u1, u2; };

// Authored synthetic coefficients. Angular quantities are numerically radians.
struct Parameters {
    double mass;
    std::array<double, 3> principal_inertia;
    double density, reference_area, reference_length, gravity, thrust;
    double cx0, cx_alpha_squared, cx_beta_squared;
    double cy0, cy_alpha, cy_beta, cy_u1, cy_u2;
    double cz_beta, cz_alpha, cz_u1, cz_u2;
    std::array<double, 3> moment_alpha, moment_beta;
    std::array<double, 9> moment_rate;
    std::array<double, 9> moment_control;
};

struct Linearization {
    State rates;
    Matrix state;
    Matrix control;
};

class Model {
public:
    static std::variant<Model, Diagnostics> make(Parameters parameters);
    std::variant<State, Diagnostics> rhs(const State&, const Control&) const;
    std::variant<Linearization, Diagnostics> linearize(const State&, const Control&) const;
    const Parameters& parameters() const noexcept { return parameters_; }

private:
    explicit Model(Parameters parameters) : parameters_(std::move(parameters)) {}
    Parameters parameters_;
};

Parameters synthetic_parameters();
Matrix body_from_inertial(double phi, double psi, double theta);

} // namespace csl::model::spatial_flight
