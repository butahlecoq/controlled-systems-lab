#include "quadcopter_mpc_task.hpp"

#include <cmath>
#include <limits>
#include <algorithm>

namespace csl::examples::quadcopter_mpc {
namespace {
using Row = std::vector<std::pair<std::size_t,double>>;

bool square(const Matrix& m, std::size_t n) { return m.rows==n && m.cols==n && m.values.size()==n*n; }
double quadratic(const Matrix& q, const Vector& x) {
    double v=0;
    for (std::size_t i=0;i<x.size();++i) for (std::size_t j=0;j<x.size();++j)
        v += x[i]*q.values[i*q.cols+j]*x[j];
    return v;
}
}

optimization::NominalQuadraticHistoryTask make_task(const NominalProblem& p) {
    const auto nx=p.initial.size(), nu=p.input_bounds.size(), n=p.horizon;
    if (!n || p.reference.size()!=nx || p.state_bounds.size()!=nx || !square(p.A,nx) ||
        p.B.rows!=nx || p.B.cols!=nu || p.B.values.size()!=nx*nu || !square(p.Q,nx) ||
        !square(p.QN,nx) || !square(p.R,nu))
        throw std::invalid_argument("Inconsistent source21 task dimensions");
    const auto scaled_hessian=[](const Matrix& q) {
        Matrix result=q;
        for(auto& value: result.values) value*=2.0;
        return result;
    };
    const auto tracking_linear=[&](const Matrix& q) {
        Vector result(nx,0.0);
        for(std::size_t i=0;i<nx;++i)
            for(std::size_t j=0;j<nx;++j) result[i]-=2.0*q.values[i*nx+j]*p.reference[j];
        return result;
    };
    const auto tracking_offset=[&](const Matrix& q) { return quadratic(q,p.reference); };

    std::vector<LinearStage> dynamics(n,{p.A,p.B,Matrix{nx,0,{}},Vector(nx,0.0)});
    std::vector<std::vector<Interval>> state_bounds(n+1,p.state_bounds);
    std::vector<std::vector<Interval>> control_bounds(n,p.input_bounds);
    std::vector<optimization::QuadraticHistoryStageCost> running;
    running.reserve(n);
    for(std::size_t stage=0;stage<n;++stage)
        running.push_back({scaled_hessian(p.Q),Matrix{nx,nu,Vector(nx*nu,0.0)},scaled_hessian(p.R),
            tracking_linear(p.Q),Vector(nu,0.0),tracking_offset(p.Q)});
    return {{{"quadcopter-mpc"},{"source21-horizon"+std::to_string(n)}},
        std::move(dynamics),KnownInitial{p.initial},std::move(state_bounds),std::move(control_bounds),
        std::nullopt,std::move(running),
        {scaled_hessian(p.QN),tracking_linear(p.QN),tracking_offset(p.QN)}};
}

double evaluate_source_cost(const NominalProblem& p,std::span<const double> states,
                            std::span<const double> controls) {
    const auto nx=p.initial.size(),nu=p.input_bounds.size();
    if(states.size()!=(p.horizon+1)*nx || controls.size()!=p.horizon*nu)
        return std::numeric_limits<double>::quiet_NaN();
    double result=0;
    auto stage=[&](std::size_t k,const Matrix& q) {
        Vector d(nx); for(std::size_t i=0;i<nx;++i)d[i]=states[k*nx+i]-p.reference[i];
        return quadratic(q,d);
    };
    for(std::size_t k=0;k<p.horizon;++k) {
        result+=stage(k,p.Q);
        for(std::size_t i=0;i<nu;++i)for(std::size_t j=0;j<nu;++j)
            result+=controls[k*nu+i]*p.R.values[i*nu+j]*controls[k*nu+j];
    }
    return result+stage(p.horizon,p.QN);
}

double evaluate_running_stage(const NominalProblem& p,std::span<const double> state,
                             std::span<const double> control) {
    const auto nx=p.initial.size(),nu=p.input_bounds.size();
    if(state.size()!=nx || control.size()!=nu) return std::numeric_limits<double>::quiet_NaN();
    Vector d(nx); for(std::size_t i=0;i<nx;++i)d[i]=state[i]-p.reference[i];
    double result=quadratic(p.Q,d);
    for(std::size_t i=0;i<nu;++i)for(std::size_t j=0;j<nu;++j)
        result+=control[i]*p.R.values[i*nu+j]*control[j];
    return result;
}
bool source_history_feasible(const NominalProblem& p,std::span<const double> states,
                             std::span<const double> controls,double tolerance) {
    const auto nx=p.initial.size(),nu=p.input_bounds.size();
    if(states.size()!=(p.horizon+1)*nx || controls.size()!=p.horizon*nu ||
       !std::isfinite(tolerance) || tolerance<0) return false;
    for(std::size_t i=0;i<nx;++i)
        if(std::abs(states[i]-p.initial[i])>tolerance) return false;
    for(std::size_t k=0;k<p.horizon;++k) for(std::size_t i=0;i<nx;++i) {
        double next=0;
        for(std::size_t j=0;j<nx;++j) next+=p.A.values[i*nx+j]*states[k*nx+j];
        for(std::size_t j=0;j<nu;++j) next+=p.B.values[i*nu+j]*controls[k*nu+j];
        if(std::abs(states[(k+1)*nx+i]-next)>tolerance) return false;
    }
    for(std::size_t k=0;k<=p.horizon;++k) for(std::size_t i=0;i<nx;++i) {
        const auto value=states[k*nx+i];
        if(!std::isfinite(value) || (p.state_bounds[i].lower && value<*p.state_bounds[i].lower-tolerance) ||
           (p.state_bounds[i].upper && value>*p.state_bounds[i].upper+tolerance)) return false;
    }
    for(std::size_t k=0;k<p.horizon;++k) for(std::size_t i=0;i<nu;++i) {
        const auto value=controls[k*nu+i];
        if(!std::isfinite(value) || (p.input_bounds[i].lower && value<*p.input_bounds[i].lower-tolerance) ||
           (p.input_bounds[i].upper && value>*p.input_bounds[i].upper+tolerance)) return false;
    }
    return true;
}

} // namespace csl::examples::quadcopter_mpc
