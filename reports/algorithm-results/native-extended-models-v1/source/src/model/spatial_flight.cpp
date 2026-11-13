#include <csl/model/spatial_flight.hpp>

#include <algorithm>
#include <cmath>
#include <string>

namespace csl::model::spatial_flight {
namespace {
constexpr std::size_t seed_count = 12;
struct Dual {
    double value{};
    std::array<double, seed_count> derivative{};
    Dual() = default;
    Dual(double v) : value(v) {}
};
Dual operator+(Dual a, Dual b) {
    a.value += b.value;
    for (std::size_t i = 0; i < seed_count; ++i) a.derivative[i] += b.derivative[i];
    return a;
}
Dual operator-(Dual a, Dual b) {
    a.value -= b.value;
    for (std::size_t i = 0; i < seed_count; ++i) a.derivative[i] -= b.derivative[i];
    return a;
}
Dual operator-(Dual a) {
    a.value = -a.value;
    for (auto& d : a.derivative) d = -d;
    return a;
}
Dual operator*(Dual a, Dual b) {
    Dual out(a.value * b.value);
    for (std::size_t i = 0; i < seed_count; ++i)
        out.derivative[i] = a.derivative[i] * b.value + a.value * b.derivative[i];
    return out;
}
Dual operator/(Dual a, Dual b) {
    Dual out(a.value / b.value);
    const double denominator = b.value * b.value;
    for (std::size_t i = 0; i < seed_count; ++i)
        out.derivative[i] = (a.derivative[i] * b.value - a.value * b.derivative[i]) / denominator;
    return out;
}
Dual sqrt(Dual a) {
    Dual out(std::sqrt(a.value));
    for (std::size_t i = 0; i < seed_count; ++i)
        out.derivative[i] = a.derivative[i] / (2 * out.value);
    return out;
}
Dual sin(Dual a) {
    Dual out(std::sin(a.value));
    for (std::size_t i = 0; i < seed_count; ++i) out.derivative[i] = std::cos(a.value) * a.derivative[i];
    return out;
}
Dual cos(Dual a) {
    Dual out(std::cos(a.value));
    for (std::size_t i = 0; i < seed_count; ++i) out.derivative[i] = -std::sin(a.value) * a.derivative[i];
    return out;
}
Dual atan2(Dual y, Dual x) {
    Dual out(std::atan2(y.value, x.value));
    const double denominator = x.value * x.value + y.value * y.value;
    for (std::size_t i = 0; i < seed_count; ++i)
        out.derivative[i] = (x.value * y.derivative[i] - y.value * x.derivative[i]) / denominator;
    return out;
}

template<class T> struct Vec3 { T x, y, z; };
template<class T> std::array<T,9> rotation(const T& phi, const T& psi, const T& theta) {
    using std::cos;
    using std::sin;
    const T cp=cos(phi), sp=sin(phi), cs=cos(psi), ss=sin(psi), ct=cos(theta), st=sin(theta);
    return {cs*ct, cs*st, -ss,
            sp*ss*ct-cp*st, sp*ss*st+cp*ct, sp*cs,
            cp*ss*ct+sp*st, cp*ss*st-sp*ct, cp*cs};
}
template<class T> Vec3<T> cross(const Vec3<T>& a, const Vec3<T>& b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}

template<class T> std::array<T, 9> evaluate(const Parameters& p, const std::array<T, 9>& x,
                                           const std::array<T, 3>& u) {
    using std::atan2;
    using std::cos;
    using std::sin;
    using std::sqrt;
    const T vx=x[0], vy=x[1], vz=x[2], phi=x[3], psi=x[4], theta=x[5];
    const T wx=x[6], wy=x[7], wz=x[8];
    // B = Rx_passive(phi) Ry_passive(psi) Rz_passive(theta).
    const auto rotation_matrix=rotation(phi,psi,theta);
    const T gravity_x=-p.gravity*rotation_matrix[1];
    const T gravity_y=-p.gravity*rotation_matrix[4];
    const T gravity_z=-p.gravity*rotation_matrix[7];
    const T cp=cos(phi), sp=sin(phi), cs=cos(psi), ss=sin(psi);
    const T alpha=atan2(vy, sqrt(vx*vx+vz*vz));
    const T beta=atan2(vz, vx);
    const T speed_squared=vx*vx+vy*vy+vz*vz;
    const T dynamic_pressure=T(0.5*p.density)*speed_squared;
    const T q_area=dynamic_pressure*T(p.reference_area);
    const T q_area_length=q_area*T(p.reference_length);
    const T cx=T(p.cx0)+T(p.cx_alpha_squared)*alpha*alpha+T(p.cx_beta_squared)*beta*beta;
    const T cy=T(p.cy0)+T(p.cy_alpha)*alpha+T(p.cy_beta)*beta+T(p.cy_u1)*u[1]+T(p.cy_u2)*u[2];
    const T cz=T(p.cz_beta)*beta+T(p.cz_alpha)*alpha+T(p.cz_u1)*u[1]+T(p.cz_u2)*u[2];
    const Vec3<T> velocity{vx,vy,vz}, omega{wx,wy,wz};
    const auto transport=cross(omega,velocity);
    const T ax=gravity_x+(T(p.thrust)-q_area*cx)/T(p.mass)-transport.x;
    const T ay=gravity_y+q_area*cy/T(p.mass)-transport.y;
    const T az=gravity_z+q_area*cz/T(p.mass)-transport.z;
    const T lateral_sum=sp*wy+cp*wz;
    const T phi_rate=wx+(ss/cs)*lateral_sum;
    const T psi_rate=cp*wy-sp*wz;
    const T theta_rate=lateral_sum/cs;
    const T cmx=T(p.moment_alpha[0])*alpha+T(p.moment_beta[0])*beta;
    const T cmy=T(p.moment_alpha[1])*alpha+T(p.moment_beta[1])*beta;
    const T cmz=T(p.moment_alpha[2])*alpha+T(p.moment_beta[2])*beta;
    const T cm[3]{cmx, cmy, cmz};
    const T rates[3]{wx,wy,wz};
    T moment[3];
    for (std::size_t i=0;i<3;++i) {
        moment[i]=cm[i];
        for (std::size_t j=0;j<3;++j)
            moment[i]=moment[i]+T(p.moment_rate[3*i+j])*rates[j]+T(p.moment_control[3*i+j])*u[j];
        moment[i]=q_area_length*moment[i];
    }
    const Vec3<T> angular_momentum{T(p.principal_inertia[0])*wx,T(p.principal_inertia[1])*wy,T(p.principal_inertia[2])*wz};
    const auto gyro=cross(omega, angular_momentum);
    return {ax,ay,az,phi_rate,psi_rate,theta_rate,
            (moment[0]-gyro.x)/T(p.principal_inertia[0]),
            (moment[1]-gyro.y)/T(p.principal_inertia[1]),
            (moment[2]-gyro.z)/T(p.principal_inertia[2])};
}

std::array<double, 9> values(const State& x) {
    return {x.vx,x.vy,x.vz,x.phi,x.psi,x.theta,x.omega_x,x.omega_y,x.omega_z};
}
std::array<double, 3> values(const Control& u) { return {u.u0,u.u1,u.u2}; }
Diagnostics invalid(std::string field, std::string explanation) {
    return {{DiagnosticCode::invalid_input, std::move(field), std::move(explanation)}};
}
Diagnostics validate_point(const State& x, const Control& u) {
    for (double value : values(x)) if (!std::isfinite(value)) return invalid("model.spatial_flight.state", "all state coordinates must be finite");
    for (double value : values(u)) if (!std::isfinite(value)) return invalid("model.spatial_flight.control", "all control coordinates must be finite");
    if (!(x.vx > 1.0)) return invalid("model.spatial_flight.vx", "operating domain requires vx > 1 m/s");
    if (!(std::abs(std::cos(x.psi)) >= 0.2)) return invalid("model.spatial_flight.psi", "operating domain requires abs(cos(psi)) >= 0.2");
    return {};
}
bool finite(const Dual& value) {
    return std::isfinite(value.value) &&
        std::all_of(value.derivative.begin(), value.derivative.end(), [](double d) { return std::isfinite(d); });
}
}

Parameters synthetic_parameters() {
    return {100.0, {30.0,40.0,50.0}, 1.225,2.0,1.5,9.81,490.0,
        0.04,0.5,0.3,981.0/12250.0,-3.0,0.1,0.03,0.005,
        -2.5,0.08,-0.004,0.025,
        {0.002,0.003,0.03},{-0.004,-0.025,0.002},
        {-0.002,0.0,0.0, 0.0,-0.0025,0.0, 0.0,0.0,-0.003},
        {0.02,0.002,-0.001, 0.001,0.025,0.002, -0.001,0.003,0.03}};
}

Matrix body_from_inertial(double phi, double psi, double theta) {
    const auto values=rotation(phi,psi,theta);
    return {3,3,Vector(values.begin(),values.end())};
}

std::variant<Model, Diagnostics> Model::make(Parameters p) {
    const double scalars[]{p.mass,p.density,p.reference_area,p.reference_length,p.gravity,p.thrust,
        p.cx0,p.cx_alpha_squared,p.cx_beta_squared,p.cy0,p.cy_alpha,p.cy_beta,p.cy_u1,p.cy_u2,
        p.cz_beta,p.cz_alpha,p.cz_u1,p.cz_u2};
    for (double v : scalars) if (!std::isfinite(v)) return invalid("model.spatial_flight.parameters", "all parameters must be finite");
    for (double v : p.principal_inertia) if (!std::isfinite(v) || !(v > 0)) return invalid("model.spatial_flight.inertia", "principal inertias must be finite and positive");
    for (double v : p.moment_alpha) if (!std::isfinite(v)) return invalid("model.spatial_flight.moment_alpha", "moment coefficients must be finite");
    for (double v : p.moment_beta) if (!std::isfinite(v)) return invalid("model.spatial_flight.moment_beta", "moment coefficients must be finite");
    for (double v : p.moment_rate) if (!std::isfinite(v)) return invalid("model.spatial_flight.moment_rate", "moment coefficients must be finite");
    for (double v : p.moment_control) if (!std::isfinite(v)) return invalid("model.spatial_flight.moment_control", "moment coefficients must be finite");
    if (!(p.mass > 0) || !(p.density > 0) || !(p.reference_area > 0) || !(p.reference_length > 0) || !(p.gravity > 0))
        return invalid("model.spatial_flight.parameters", "mass, density, geometry and gravity must be positive");
    return Model(std::move(p));
}

std::variant<State, Diagnostics> Model::rhs(const State& x, const Control& u) const {
    if (auto errors=validate_point(x,u); !errors.empty()) return errors;
    const auto y=evaluate(parameters_, values(x), values(u));
    if (!std::all_of(y.begin(), y.end(), [](double value) { return std::isfinite(value); }))
        return invalid("model.spatial_flight.rhs", "finite input produced a nonfinite derivative");
    return State{y[0],y[1],y[2],y[3],y[4],y[5],y[6],y[7],y[8]};
}

std::variant<Linearization, Diagnostics> Model::linearize(const State& x, const Control& u) const {
    if (auto errors=validate_point(x,u); !errors.empty()) return errors;
    std::array<Dual,9> xd;
    std::array<Dual,3> ud;
    const auto xv=values(x); const auto uv=values(u);
    for (std::size_t i=0;i<9;++i) { xd[i]=Dual(xv[i]); xd[i].derivative[i]=1; }
    for (std::size_t i=0;i<3;++i) { ud[i]=Dual(uv[i]); ud[i].derivative[9+i]=1; }
    const auto output=evaluate(parameters_,xd,ud);
    if (!std::all_of(output.begin(), output.end(), finite))
        return invalid("model.spatial_flight.linearization", "finite input produced nonfinite rates or Jacobian entries");
    Linearization result{{output[0].value,output[1].value,output[2].value,output[3].value,output[4].value,
                          output[5].value,output[6].value,output[7].value,output[8].value},
                         Matrix{9,9,Vector(81)},Matrix{9,3,Vector(27)}};
    for (std::size_t r=0;r<9;++r) {
        for (std::size_t c=0;c<9;++c) result.state.values[r*9+c]=output[r].derivative[c];
        for (std::size_t c=0;c<3;++c) result.control.values[r*3+c]=output[r].derivative[9+c];
    }
    return result;
}
} // namespace csl::model::spatial_flight
