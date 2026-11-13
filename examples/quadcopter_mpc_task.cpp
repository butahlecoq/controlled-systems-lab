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

optimization::ConvexDataResult<ConvexProgram> compile(const NominalProblem& p) {
    const auto nx=p.initial.size(), nu=p.input_bounds.size(), n=p.horizon;
    if (!n || p.reference.size()!=nx || p.state_bounds.size()!=nx || !square(p.A,nx) ||
        p.B.rows!=nx || p.B.cols!=nu || p.B.values.size()!=nx*nu || !square(p.Q,nx) ||
        !square(p.QN,nx) || !square(p.R,nu))
        return Diagnostics{{DiagnosticCode::invalid_input,"mpc.dimensions","Inconsistent nominal MPC dimensions"}};
    const auto x_offset=[&](std::size_t k){return k*nx;};
    const auto u_offset=[&](std::size_t k){return (n+1)*nx+k*nu;};
    const auto nv=(n+1)*nx+n*nu;
    Matrix hessian{nv,nv,Vector(nv*nv,0)};
    Vector linear(nv,0);
    double offset=0;
    auto add_state_cost=[&](std::size_t k,const Matrix& q) {
        const auto start=x_offset(k);
        offset+=quadratic(q,p.reference);
        for(std::size_t i=0;i<nx;++i) {
            linear[start+i]-=2*([&]{double s=0;for(std::size_t j=0;j<nx;++j)s+=q.values[i*nx+j]*p.reference[j];return s;}());
            for(std::size_t j=0;j<nx;++j) hessian.values[(start+i)*nv+start+j]=2*q.values[i*nx+j];
        }
    };
    for(std::size_t k=0;k<n;++k) {
        add_state_cost(k,p.Q);
        for(std::size_t i=0;i<nu;++i) for(std::size_t j=0;j<nu;++j)
            hessian.values[(u_offset(k)+i)*nv+u_offset(k)+j]=2*p.R.values[i*nu+j];
    }
    add_state_cost(n,p.QN);

    std::vector<Row> rows;
    std::vector<Interval> row_bounds;
    auto equality=[&](Row row,double value){rows.push_back(std::move(row));row_bounds.push_back({value,value});};
    for(std::size_t i=0;i<nx;++i) equality({{x_offset(0)+i,1}},p.initial[i]);
    for(std::size_t k=0;k<n;++k) for(std::size_t i=0;i<nx;++i) {
        Row row{{x_offset(k+1)+i,1}};
        for(std::size_t j=0;j<nx;++j) if(p.A.values[i*nx+j]!=0) row.emplace_back(x_offset(k)+j,-p.A.values[i*nx+j]);
        for(std::size_t j=0;j<nu;++j) if(p.B.values[i*nu+j]!=0) row.emplace_back(u_offset(k)+j,-p.B.values[i*nu+j]);
        equality(std::move(row),0);
    }
    // State and input bounds are rows after the initial and dynamics equalities.
    for(std::size_t k=0;k<=n;++k) for(std::size_t j=0;j<nx;++j) if(p.state_bounds[j].lower || p.state_bounds[j].upper) {
        rows.push_back({{x_offset(k)+j,1}}); row_bounds.push_back(p.state_bounds[j]);
    }
    for(std::size_t k=0;k<n;++k) for(std::size_t j=0;j<nu;++j) if(p.input_bounds[j].lower || p.input_bounds[j].upper) {
        rows.push_back({{u_offset(k)+j,1}}); row_bounds.push_back(p.input_bounds[j]);
    }
    SparseMatrix constraints{rows.size(),nv,std::vector<std::size_t>{},std::vector<std::size_t>{},Vector{}};
    constraints.row_offsets.push_back(0);
    for(auto& row: rows) {
        std::sort(row.begin(),row.end(),[](const auto& a,const auto& b){return a.first<b.first;});
        for(const auto [col,value]:row) {constraints.column_indices.push_back(col);constraints.values.push_back(value);}
        constraints.row_offsets.push_back(constraints.values.size());
    }
    auto made=optimization::make_convex_program({{{"quadcopter-mpc"},{"source21-horizon10"}},
        QuadraticTerminal{std::move(hessian),std::move(linear),offset},std::move(constraints),
        std::vector<Interval>(nv),std::move(row_bounds),std::nullopt});
    if(auto* value=std::get_if<ConvexProgram>(&made)) return std::move(*value);
    if(auto* errors=std::get_if<Diagnostics>(&made)) return std::move(*errors);
    return std::get<OperationStopped>(std::move(made));
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
} // namespace csl::examples::quadcopter_mpc
