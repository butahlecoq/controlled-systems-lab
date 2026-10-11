#include <csl/optimization/lp_backend.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <type_traits>

namespace csl {
ProgramOutcome LPWorkspace::solve(const LinearProgram& p,const ExecutionContext& c) {
    attempt_.reset();
    if(sequence_==std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("LP attempt sequence exhausted");
    attempt_=SolveAttempt{SolveStamp{p,identity_,++sequence_},SolveAttemptState::running};
    try {
        auto outcome=do_solve(p,c);
        attempt_->state=std::holds_alternative<Unsupported>(outcome)?SolveAttemptState::unsupported:SolveAttemptState::returned_result;
        return outcome;
    } catch(...) {
        attempt_->state=SolveAttemptState::exception;
        throw;
    }
}
namespace optimization {
namespace {
Diagnostics error(DiagnosticCode code,std::string field,std::string message) {
    return {{code,std::move(field),std::move(message)}};
}
Diagnostics invalid(std::string field,std::string message) {
    return error(DiagnosticCode::invalid_claim,std::move(field),std::move(message));
}
bool nonnegative(double x) { return std::isfinite(x) && x>=0; }
bool finite(std::span<const double> values) {
    return std::all_of(values.begin(),values.end(),[](double v){return std::isfinite(v);});
}
bool supported(const EvidenceSupport& support) {
    return std::holds_alternative<NumericalCheck>(support) || std::holds_alternative<SymbolicArgument>(support);
}
bool valid_support(const EvidenceSupport& support) {
    return std::visit([](const auto& value) {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,Unestablished>) return true;
        else if constexpr(std::is_same_v<T,NumericalCheck>) return nonnegative(value.absolute_tolerance) &&
            nonnegative(value.relative_tolerance) && nonnegative(value.max_residual) && !value.verifier.value.empty();
        else if constexpr(std::is_same_v<T,SymbolicArgument>) return !value.reference.empty() && !value.assumptions.empty();
        else return !value.artifact.empty() && !value.verifier.empty();
    },support);
}
Diagnostics check_context(const ResidualContext& context,const LinearProgram& p) {
    if(context.subject!=p.identity()) return error(DiagnosticCode::evidence_mismatch,"lp.residual.subject","different program");
    if(!nonnegative(context.absolute_tolerance) || !nonnegative(context.relative_tolerance) ||
        context.verifier.id.value.empty() || context.verifier.version.empty()) return invalid("lp.residual.context","invalid numerical check metadata");
    return {};
}
bool valid_measure(const ResidualMeasure& m,const ResidualContext& context) {
    return nonnegative(m.violation) && nonnegative(m.scale) &&
        std::isfinite(context.absolute_tolerance+context.relative_tolerance*m.scale);
}
bool same_column_id(const BasisColumn& a,const BasisColumn& b) {
    if(a.index()!=b.index()) return false;
    return std::visit([&](const auto& column) {
        using T=std::decay_t<decltype(column)>;
        if constexpr(std::is_same_v<T,AuxiliaryColumn>) return column.id==std::get<T>(b).id;
        else return column.index==std::get<T>(b).index;
    },a);
}
bool valid_column(const BasisColumn& column,const LinearProgram& p) {
    return std::visit([&](const auto& c) {
        using T=std::decay_t<decltype(c)>;
        if constexpr(std::is_same_v<T,StructuralColumn>) return c.index<p.constraints().cols();
        else if constexpr(std::is_same_v<T,RowActivityColumn>) return c.index<p.constraints().rows();
        else return c.coefficients.size()==p.constraints().rows() && finite(c.coefficients);
    },column);
}
bool valid_columns(const std::vector<BasisColumn>& columns,const LinearProgram& p) {
    if(columns.size()!=p.constraints().rows()) return false;
    for(std::size_t i=0;i<columns.size();++i) {
        if(!valid_column(columns[i],p)) return false;
        for(std::size_t j=0;j<i;++j) if(same_column_id(columns[i],columns[j])) return false;
    }
    return true;
}
Diagnostics check_stamp(const SolveStamp& stamp,const std::optional<SolveAttempt>& expected) {
    if(!expected || expected->state!=SolveAttemptState::returned_result || stamp!=expected->stamp ||
        stamp.program().identity()!=expected->stamp.program().identity())
        return error(DiagnosticCode::evidence_mismatch,"basis.solve","not the current returned attempt of this workspace");
    return {};
}
}
Diagnostics check_program_result(const ProgramResult& r,const LinearProgram& p,Assurance assurance) {
    auto diagnostics=check_outcome_evidence(r.outcome,p.identity(),assurance);
    if(!diagnostics.empty()) return diagnostics;
    switch(r.termination) {
        case Termination::completed: case Termination::cancelled: case Termination::resource_limit: case Termination::numerical_failure: break;
        default: return invalid("lp.termination","unknown termination");
    }
    switch(r.outcome.value) {
        case MathematicalOutcome::optimal: case MathematicalOutcome::infeasible: case MathematicalOutcome::unbounded:
        case MathematicalOutcome::infimum_not_attained: case MathematicalOutcome::undetermined: break;
        default: return invalid("lp.outcome","unknown mathematical outcome");
    }
    if(!valid_support(r.outcome.support)) return invalid("lp.outcome.support","invalid support metadata");
    if(r.primal && (r.primal->size()!=p.objective().size() || !finite(*r.primal))) return invalid("lp.primal","invalid candidate shape or values");
    for(const auto* bound:{&r.objective.lower,&r.objective.upper}) if(*bound) {
        if((*bound)->evidence.subject!=p.identity()) return error(DiagnosticCode::evidence_mismatch,"lp.bound.subject","different program");
        if(!std::isfinite((*bound)->value) || !valid_support((*bound)->evidence.support)) return invalid("lp.bound","nonfinite bound or invalid support");
    }
    if(r.objective.lower && r.objective.upper && r.objective.lower->value>r.objective.upper->value)
        return invalid("lp.bounds","lower bound exceeds upper bound");
    if(supported(r.outcome.support)) {
        if(r.outcome.value==MathematicalOutcome::infeasible && r.objective.upper && supported(r.objective.upper->evidence.support))
            return invalid("lp.outcome","supported infeasibility conflicts with supported finite upper bound");
        if(r.outcome.value==MathematicalOutcome::unbounded && r.objective.lower && supported(r.objective.lower->evidence.support))
            return invalid("lp.outcome","supported unboundedness conflicts with supported finite lower bound");
    }
    if(r.residuals.primal) {
        const auto& d=*r.residuals.primal;
        diagnostics=check_context(d.context,p); if(!diagnostics.empty()) return diagnostics;
        if(!valid_measure(d.rows,d.context) || !valid_measure(d.variables,d.context)) return invalid("lp.residual.primal","invalid measure");
    }
    if(r.residuals.dual) {
        const auto& d=*r.residuals.dual;
        diagnostics=check_context(d.context,p); if(!diagnostics.empty()) return diagnostics;
        for(const auto* m:{&d.stationarity,&d.signs,&d.complementarity}) if(*m && !valid_measure(**m,d.context))
            return invalid("lp.residual.dual","invalid measure");
    }
    return {};
}
Result<DualEvaluation> evaluate_dual(const LinearProgram& p,const DualMultipliers& multipliers,NumericalPolicy policy,const Verifier& verifier) {
    const ResidualContext context{p.identity(),verifier,policy.absolute_tolerance,policy.relative_tolerance};
    auto diagnostics=check_context(context,p); if(!diagnostics.empty()) return diagnostics;
    const auto m=p.rows().size(),n=p.variables().size();
    if(multipliers.row_lower.size()!=m || multipliers.row_upper.size()!=m ||
        multipliers.variable_lower.size()!=n || multipliers.variable_upper.size()!=n)
        return error(DiagnosticCode::invalid_input,"lp.dual.shape","multiplier dimensions differ");
    DualEvaluation output{p.offset(),{context,ResidualMeasure{0,1},ResidualMeasure{0,1},{}}};
    auto add_bounds=[&](std::span<const Interval> bounds,const Vector& lower,const Vector& upper) {
        for(std::size_t i=0;i<bounds.size();++i) {
            if(!std::isfinite(lower[i]) || !std::isfinite(upper[i]) || (!bounds[i].lower && lower[i]!=0) || (!bounds[i].upper && upper[i]!=0)) return false;
            output.residuals.signs->violation=std::max({output.residuals.signs->violation,-lower[i],-upper[i]});
            output.residuals.signs->scale=std::max({output.residuals.signs->scale,std::abs(lower[i]),std::abs(upper[i])});
            if(bounds[i].lower) output.lagrangian_constant+=*bounds[i].lower*lower[i];
            if(bounds[i].upper) output.lagrangian_constant-=*bounds[i].upper*upper[i];
        }
        return true;
    };
    if(!add_bounds(p.rows(),multipliers.row_lower,multipliers.row_upper) ||
        !add_bounds(p.variables(),multipliers.variable_lower,multipliers.variable_upper))
        return error(DiagnosticCode::invalid_input,"lp.dual.multipliers","nonfinite multiplier or nonzero multiplier at absent endpoint");
    Vector stationarity(p.objective().values().begin(),p.objective().values().end());
    Vector scale(n,0);
    for(std::size_t j=0;j<n;++j) {
        scale[j]=std::abs(stationarity[j])+std::abs(multipliers.variable_lower[j])+std::abs(multipliers.variable_upper[j]);
        stationarity[j]-=multipliers.variable_lower[j]; stationarity[j]+=multipliers.variable_upper[j];
    }
    const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
    for(std::size_t i=0;i<m;++i) for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {
        const auto j=csr.column_indices[k];
        const double lower=csr.values[k]*multipliers.row_lower[i],upper=csr.values[k]*multipliers.row_upper[i];
        stationarity[j]-=lower; stationarity[j]+=upper; scale[j]+=std::abs(lower)+std::abs(upper);
    }
    if(!finite(stationarity) || !finite(scale) || !std::isfinite(output.lagrangian_constant))
        return error(DiagnosticCode::invalid_input,"lp.dual.arithmetic","nonfinite numerical evaluation");
    for(std::size_t j=0;j<n;++j) {
        output.residuals.stationarity->violation=std::max(output.residuals.stationarity->violation,std::abs(stationarity[j]));
        output.residuals.stationarity->scale=std::max(output.residuals.stationarity->scale,scale[j]);
    }
    if(!valid_measure(*output.residuals.stationarity,context) || !valid_measure(*output.residuals.signs,context))
        return error(DiagnosticCode::invalid_input,"lp.dual.arithmetic","nonfinite tolerance comparison");
    return output;
}
Diagnostics check_basis_snapshot(const BasisSnapshot& snapshot,const std::optional<SolveAttempt>& expected) {
    auto diagnostics=check_stamp(snapshot.reference.solve,expected); if(!diagnostics.empty()) return diagnostics;
    const auto& p=expected->stamp.program();
    if(p.rows().empty() && snapshot.reference.iteration!=0) return invalid("basis.iteration","zero rows have no pivots");
    if(!valid_columns(snapshot.columns,p)) return invalid("basis.columns","expected m distinct valid original-row columns");
    if(snapshot.last_pivot) {
        const auto& pivot=*snapshot.last_pivot;
        if(pivot.before.solve!=snapshot.reference.solve || pivot.after!=snapshot.reference ||
            pivot.before.iteration==std::numeric_limits<std::uint64_t>::max() || pivot.after.iteration!=pivot.before.iteration+1 ||
            !valid_columns(pivot.before_basis,p) || pivot.position>=snapshot.columns.size() ||
            !valid_column(pivot.entering,p) || !valid_column(pivot.leaving,p) ||
            !std::isfinite(pivot.coefficient) || pivot.coefficient==0)
            return invalid("basis.pivot","invalid pre/post pivot association or shape");
        if(pivot.before_basis[pivot.position]!=pivot.leaving) return invalid("basis.pivot.leaving","leaving column differs from pre-pivot slot");
        for(std::size_t i=0;i<snapshot.columns.size();++i) {
            if(same_column_id(pivot.before_basis[i],pivot.entering)) return invalid("basis.pivot.entering","entering column already basic");
            if(snapshot.columns[i]!=(i==pivot.position?pivot.entering:pivot.before_basis[i]))
                return invalid("basis.pivot.order","post-pivot basis must replace precisely the leaving slot");
        }
    }
    return {};
}
Diagnostics check_basis_coordinates(const BasisCoordinates& coordinates,const BasisSnapshot& snapshot,const std::optional<SolveAttempt>& expected) {
    auto diagnostics=check_basis_snapshot(snapshot,expected); if(!diagnostics.empty()) return diagnostics;
    if(coordinates.reference!=snapshot.reference) return error(DiagnosticCode::evidence_mismatch,"basis.coordinates.reference","different basis state");
    if(coordinates.values.size()!=snapshot.columns.size() || !finite(coordinates.values)) return invalid("basis.coordinates","expected m finite coordinates");
    return {};
}
}}
