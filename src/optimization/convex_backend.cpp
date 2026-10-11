#include <csl/optimization/convex_backend.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace csl {
ProgramOutcome ConvexWorkspace::solve(const ConvexProgram& p,const ExecutionContext& c) {
    attempt_.reset();
    if(sequence_==std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("Convex attempt sequence exhausted");
    attempt_=ConvexSolveAttempt{ConvexSolveStamp{p,identity_,++sequence_},SolveAttemptState::running};
    try {
        auto outcome=do_solve(p,c);
        attempt_->state=std::holds_alternative<Unsupported>(outcome)?SolveAttemptState::unsupported:SolveAttemptState::returned_result;
        return outcome;
    } catch(...) { attempt_->state=SolveAttemptState::exception; throw; }
}
struct QuadraticProgram::Storage {
    ProgramIdentity identity;
    optimization::Objective objective;
    numeric::MatrixView hessian;
    LinearProgram geometry;
};
struct ConvexProgram::Storage {
    ProgramIdentity identity;
    optimization::Objective original;
    QuadraticProgram quadratic;
    std::optional<optimization::NormSquareReformulation> reformulation;
};
const ProgramIdentity& QuadraticProgram::identity() const noexcept { return storage_->identity; }
const optimization::Objective& QuadraticProgram::objective() const noexcept { return storage_->objective; }
const numeric::MatrixView& QuadraticProgram::hessian() const noexcept { return storage_->hessian; }
const numeric::MatrixView& QuadraticProgram::constraints() const noexcept { return storage_->geometry.constraints(); }
std::span<const Interval> QuadraticProgram::variables() const noexcept { return storage_->geometry.variables(); }
std::span<const Interval> QuadraticProgram::rows() const noexcept { return storage_->geometry.rows(); }
const ProgramIdentity& ConvexProgram::identity() const noexcept { return storage_->identity; }
const optimization::Objective& ConvexProgram::original_objective() const noexcept { return storage_->original; }
const QuadraticProgram& ConvexProgram::quadratic_program() const noexcept { return storage_->quadratic; }
const optimization::NormSquareReformulation* ConvexProgram::reformulation() const noexcept {
    return storage_->reformulation ? &*storage_->reformulation : nullptr;
}
namespace optimization {
struct ConvexAccess {
    static ConvexProgram create(Objective original,Objective solver,numeric::MatrixView hessian,
        LinearProgram geometry,ProgramIdentity solver_id,std::optional<NormSquareReformulation> reformulation) {
        QuadraticProgram q{std::make_shared<const QuadraticProgram::Storage>(QuadraticProgram::Storage{
            std::move(solver_id),solver,hessian,geometry})};
        return ConvexProgram{std::make_shared<const ConvexProgram::Storage>(ConvexProgram::Storage{geometry.identity(),original,q,reformulation})};
    }
    static const LinearProgram& geometry(const ConvexProgram& p) { return p.storage_->quadratic.storage_->geometry; }
};
ConvexDataResult<ConvexProgram> make_convex_program(const ConvexProgramInput& input,ObjectivePolicy policy) {
    auto error=[](std::string field,std::string message) -> ConvexDataResult<ConvexProgram> {
        return Diagnostics{{DiagnosticCode::invalid_input,std::move(field),std::move(message)}};
    };
    auto original_result=snapshot(input.objective,policy);
    if(auto* d=std::get_if<Diagnostic>(&original_result)) return Diagnostics{*d};
    if(auto* s=std::get_if<OperationStopped>(&original_result)) return *s;
    const auto original=std::get<Objective>(original_result);
    if(original.dimension()!=input.constraints.cols) return error("convex.shape","objective and constraints dimensions differ");
    auto geometry_result=make_linear_program({input.identity,Vector(original.dimension(),0),0,input.constraints,input.variables,input.rows});
    if(auto* d=std::get_if<Diagnostics>(&geometry_result)) return *d;
    auto solver=original;
    auto solver_id=input.identity;
    std::optional<NormSquareReformulation> reformulation;
    if(std::holds_alternative<ResidualCoefficients>(original.coefficients())) {
        if(!input.squared_program || input.squared_program->value.empty() || *input.squared_program==input.identity.program)
            return error("convex.squared_program","a distinct nonempty squared program ID is required");
        auto squared=square_residual_norm(original);
        if(auto* d=std::get_if<Diagnostic>(&squared)) return Diagnostics{*d};
        if(auto* s=std::get_if<OperationStopped>(&squared)) return *s;
        reformulation=std::get<NormSquareReformulation>(squared);
        solver=reformulation->squared(); solver_id.program=*input.squared_program;
    } else if(input.squared_program) return error("convex.squared_program","only residual norm objectives require a squared identity");
    const auto coefficients=solver.coefficients();
    if(const auto* q=std::get_if<QuadraticCoefficients>(&coefficients)) {
        for(std::size_t i=0;i<q->Q.rows();++i) for(std::size_t j=0;j<i;++j)
            if(q->Q(i,j)!=q->Q(j,i)) return error("convex.symmetry","QP requires exact entrywise symmetry");
        return ConvexAccess::create(original,solver,q->Q,std::get<LinearProgram>(geometry_result),solver_id,reformulation);
    }
    const auto n=original.dimension();
    if(n==std::numeric_limits<std::size_t>::max()) return error("convex.shape","zero Hessian row extent overflow");
    auto zero=numeric::snapshot(SparseMatrix{n,n,std::vector<std::size_t>(n+1,0),{}, {}});
    if(auto* d=std::get_if<Diagnostic>(&zero)) return Diagnostics{*d};
    return ConvexAccess::create(original,solver,std::get<numeric::MatrixView>(zero),std::get<LinearProgram>(geometry_result),solver_id,reformulation);
}
ConvexDataResult<ConvexPrimalEvaluation> evaluate_primal(const ConvexProgram& p,std::span<const double> x,NumericalPolicy policy,const Verifier& verifier) {
    auto geometry=evaluate_primal(ConvexAccess::geometry(p),x,policy,verifier);
    if(auto* d=std::get_if<Diagnostics>(&geometry)) {
        if(!d->empty() && (*d)[0].field=="lp.primal.arithmetic")
            return OperationStopped{StopReason::numerical_failure,(*d)[0].explanation};
        return *d;
    }
    auto original=evaluate(p.original_objective(),x);
    auto solver=evaluate(p.quadratic_program().objective(),x);
    for(const auto* value:{&original,&solver}) {
        if(auto* d=std::get_if<Diagnostic>(value)) return Diagnostics{*d};
        if(auto* s=std::get_if<OperationStopped>(value)) return *s;
    }
    return ConvexPrimalEvaluation{std::get<double>(original),std::get<double>(solver),std::get<PrimalEvaluation>(geometry).residuals};
}
ConvexDataResult<DualResiduals> evaluate_dual(const ConvexProgram& p,std::span<const double> x,const DualMultipliers& multipliers,NumericalPolicy policy,const Verifier& verifier) {
    auto checked=evaluate_primal(p,x,policy,verifier);
    if(auto* d=std::get_if<Diagnostics>(&checked)) return *d;
    if(auto* s=std::get_if<OperationStopped>(&checked)) return *s;
    const auto& q=p.quadratic_program();
    const auto n=x.size(),m=q.rows().size();
    if(multipliers.row_lower.size()!=m || multipliers.row_upper.size()!=m ||
        multipliers.variable_lower.size()!=n || multipliers.variable_upper.size()!=n)
        return Diagnostics{{DiagnosticCode::invalid_input,"convex.dual.shape","multiplier dimensions differ"}};
    auto arithmetic=[]() -> ConvexDataResult<DualResiduals> {
        return OperationStopped{StopReason::numerical_failure,"nonfinite original-space KKT arithmetic"};
    };
    Vector gradient(n,0),activities(m,0);
    const auto coefficients=p.original_objective().coefficients();
    std::visit([&](const auto& c) {
        using T=std::decay_t<decltype(c)>;
        if constexpr(std::is_same_v<T,LinearCoefficients>) {
            gradient.assign(c.coefficients.values().begin(),c.coefficients.values().end());
        } else if constexpr(std::is_same_v<T,QuadraticCoefficients>) {
            for(std::size_t j=0;j<n;++j) {
                gradient[j]=c.linear[j];
                for(std::size_t k=0;k<n;++k) gradient[j]+=c.Q(j,k)*x[k];
            }
        } else {
            Vector residual(c.target.size());
            bool zero=true;
            for(std::size_t i=0;i<residual.size();++i) {
                residual[i]=-c.target[i];
                for(std::size_t j=0;j<n;++j) residual[i]+=c.map(i,j)*x[j];
                zero=zero && residual[i]==0;
            }
            // At checked componentwise zero, zero is a valid norm subgradient.
            if(!zero) {
                const auto rho=std::get<ConvexPrimalEvaluation>(checked).original_objective;
                for(std::size_t j=0;j<n;++j) for(std::size_t i=0;i<residual.size();++i)
                    gradient[j]+=c.map(i,j)*(residual[i]/rho);
            }
        }
    },coefficients);
    const auto csr=std::get<numeric::CsrInput>(q.constraints().descriptor());
    for(std::size_t i=0;i<m;++i) for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k)
        activities[i]+=csr.values[k]*x[csr.column_indices[k]];
    DualResiduals result{{p.identity(),verifier,policy.absolute_tolerance,policy.relative_tolerance},
        ResidualMeasure{0,1},ResidualMeasure{0,1},ResidualMeasure{0,1}};
    auto bounds=[&](std::span<const Interval> intervals,std::span<const double> values,const Vector& lower,const Vector& upper) {
        for(std::size_t i=0;i<intervals.size();++i) {
            const auto& b=intervals[i];
            if(!std::isfinite(lower[i]) || !std::isfinite(upper[i]) || (!b.lower && lower[i]!=0) || (!b.upper && upper[i]!=0)) return false;
            result.signs->violation=std::max({result.signs->violation,-lower[i],-upper[i]});
            result.signs->scale=std::max({result.signs->scale,std::abs(lower[i]),std::abs(upper[i])});
            auto add=[&](double endpoint,double multiplier) {
                const double product=std::abs(multiplier*(values[i]-endpoint));
                const double scale=std::abs(multiplier)*std::max({1.0,std::abs(values[i]),std::abs(endpoint)});
                if(!std::isfinite(product) || !std::isfinite(scale)) {
                    result.complementarity->violation=std::numeric_limits<double>::infinity(); return;
                }
                result.complementarity->violation=std::max(result.complementarity->violation,product);
                result.complementarity->scale=std::max(result.complementarity->scale,scale);
            };
            if(b.lower) add(*b.lower,lower[i]);
            if(b.upper) add(*b.upper,upper[i]);
        }
        return true;
    };
    if(!bounds(q.rows(),activities,multipliers.row_lower,multipliers.row_upper) ||
        !bounds(q.variables(),x,multipliers.variable_lower,multipliers.variable_upper))
        return Diagnostics{{DiagnosticCode::invalid_input,"convex.dual.multipliers","nonfinite or nonzero absent-endpoint multiplier"}};
    Vector scale(n,0);
    for(std::size_t j=0;j<n;++j) {
        scale[j]=std::abs(gradient[j])+std::abs(multipliers.variable_lower[j])+std::abs(multipliers.variable_upper[j]);
        gradient[j]-=multipliers.variable_lower[j]; gradient[j]+=multipliers.variable_upper[j];
    }
    for(std::size_t i=0;i<m;++i) for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {
        const auto j=csr.column_indices[k];
        const auto lower=csr.values[k]*multipliers.row_lower[i],upper=csr.values[k]*multipliers.row_upper[i];
        gradient[j]-=lower; gradient[j]+=upper; scale[j]+=std::abs(lower)+std::abs(upper);
    }
    for(std::size_t j=0;j<n;++j) {
        if(!std::isfinite(gradient[j]) || !std::isfinite(scale[j])) return arithmetic();
        result.stationarity->violation=std::max(result.stationarity->violation,std::abs(gradient[j]));
        result.stationarity->scale=std::max(result.stationarity->scale,scale[j]);
    }
    for(const auto* measure:{&*result.stationarity,&*result.signs,&*result.complementarity})
        if(!std::isfinite(measure->violation) || !std::isfinite(measure->scale) ||
            !std::isfinite(policy.absolute_tolerance+policy.relative_tolerance*measure->scale)) return arithmetic();
    return result;
}
Diagnostics check_program_result(const ProgramResult& r,const ConvexProgram& p,Assurance assurance) {
    // The existing structural checker uses only identity, dimensions and evidence
    // metadata. This private zero-objective geometry owner is never solved.
    return check_program_result(r,ConvexAccess::geometry(p),assurance);
}
} // namespace optimization
} // namespace csl
