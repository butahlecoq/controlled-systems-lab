#include <csl/optimization/history_optimizer.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace csl::optimization {
namespace {
Diagnostic invalid(std::string field,std::string why) {
    return {DiagnosticCode::invalid_input,std::move(field),std::move(why)};
}
std::size_t history_size(const JointCoordinates& c) {
    return c.dimensions.state*(c.horizon+1)+c.dimensions.control*c.horizon;
}
bool size_is_valid(const JointCoordinates& c) {
    const auto max=std::numeric_limits<std::size_t>::max();
    if(c.dimensions.external!=0||c.dimensions.state==0||c.dimensions.control==0||c.horizon==0||c.horizon==max)return false;
    const auto states=c.horizon+1;
    if(c.dimensions.state>max/states||c.dimensions.control>max/c.horizon)return false;
    const auto state_size=c.dimensions.state*states,control_size=c.dimensions.control*c.horizon;
    return state_size<=max-control_size;
}
bool finite(std::span<const double> x) {
    return std::all_of(x.begin(),x.end(),[](double v){return std::isfinite(v);});
}
double tolerance(const ExecutionContext& c,double scale) {
    return c.numerical.absolute_tolerance+c.numerical.relative_tolerance*scale;
}
double coordinate_scale(std::span<const double> values) {
    double scale=1;
    for(const double value:values)scale=std::max(scale,std::abs(value));
    return scale;
}
double domain_violation(const sets::SetData& set,std::span<const double> x,Diagnostic& error) {
    const auto metadata=set.metadata();
    if(metadata->set.dimension!=x.size()) {
        error=invalid("history.domain","Feasible-history domain dimension differs from canonical history size."); return INFINITY;
    }
    const auto rep=set.representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&rep)) {
        if(h->inequalities.cols()!=x.size()||h->upper_bounds.size()!=h->inequalities.rows()||
           h->equalities.cols()!=x.size()||h->equality_values.size()!=h->equalities.rows()) {
            error=invalid("history.domain","H-representation storage has inconsistent dimensions."); return INFINITY;
        }
        double worst=0;
        for(std::size_t i=0;i<h->inequalities.rows();++i) {
            double lhs=0;
            for(std::size_t j=0;j<x.size();++j)lhs+=h->inequalities(i,j)*x[j];
            worst=std::max(worst,lhs-h->upper_bounds[i]);
        }
        for(std::size_t i=0;i<h->equalities.rows();++i) {
            double lhs=0; for(std::size_t j=0;j<x.size();++j)lhs+=h->equalities(i,j)*x[j];
            worst=std::max(worst,std::abs(lhs-h->equality_values[i]));
        }
        return std::max(0.0,worst);
    }
    if(const auto* point=std::get_if<sets::SingletonRepresentation>(&rep)) {
        if(point->point.size()!=x.size()) {error=invalid("history.domain","Singleton domain dimension is inconsistent.");return INFINITY;}
        double worst=0; for(std::size_t i=0;i<x.size();++i)worst=std::max(worst,std::abs(x[i]-point->point[i])); return worst;
    }
    if(std::holds_alternative<sets::UniversalRepresentation>(rep))return 0;
    error=invalid("history.domain","Whole-history optimizer requires a nonempty H, singleton, or universal domain.");
    return INFINITY;
}
double domain_scale(const sets::SetData& set,std::span<const double> x) {
    double scale=1;
    const auto rep=set.representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&rep)) {
        for(std::size_t i=0;i<h->inequalities.rows();++i) {
            double row_scale=std::abs(h->upper_bounds[i]);
            for(std::size_t j=0;j<x.size();++j)row_scale+=std::abs(h->inequalities(i,j)*x[j]);
            scale=std::max(scale,row_scale);
        }
        for(std::size_t i=0;i<h->equalities.rows();++i) {
            double row_scale=std::abs(h->equality_values[i]);
            for(std::size_t j=0;j<x.size();++j)row_scale+=std::abs(h->equalities(i,j)*x[j]);
            scale=std::max(scale,row_scale);
        }
    } else if(const auto* point=std::get_if<sets::SingletonRepresentation>(&rep)) {
        scale=std::max(scale,coordinate_scale(point->point.values()));
    }
    return scale;
}
std::pair<std::vector<Vector>,std::vector<Vector>> unpack(const JointCoordinates& c,std::span<const double> z) {
    std::vector<Vector> states(c.horizon+1,Vector(c.dimensions.state));
    std::vector<Vector> controls(c.horizon,Vector(c.dimensions.control));
    std::size_t at=0;
    for(auto& state:states)for(auto& v:state)v=z[at++];
    for(auto& control:controls)for(auto& v:control)v=z[at++];
    return {std::move(states),std::move(controls)};
}
}

Diagnostics check_history_optimization_request(const HistoryOptimizationRequest& r) {
    Diagnostics out;
    const auto& c=r.feasible_histories.coordinates;
    if(r.identity.problem.value.empty()||r.identity.program.value.empty())out.push_back(invalid("history.identity","Problem and program identities are required."));
    if(!size_is_valid(c)) {
        out.push_back(invalid("history.coordinates","Whole-history optimization requires bounded nonzero nominal state/control coordinates and horizon.")); return out;
    }
    const auto size=history_size(c);
    if(size>std::numeric_limits<std::size_t>::max()/size) {
        out.push_back(invalid("history.coordinates","Canonical history matrix size overflows addressable storage.")); return out;
    }
    if(r.source_cost.coordinates!=c||r.source_cost.quadratic.dimension!=size||
       r.source_cost.quadratic.Q.rows!=size||r.source_cost.quadratic.Q.cols!=size||
       r.source_cost.quadratic.Q.values.size()!=size*size||r.source_cost.quadratic.linear.size()!=size||
       !finite(r.source_cost.quadratic.Q.values)||!finite(r.source_cost.quadratic.linear)||
       !std::isfinite(r.source_cost.quadratic.offset))out.push_back(invalid("history.cost","Compiled source-cost polynomial does not match canonical history coordinates."));
    if (const auto *supplied = std::get_if<SuppliedStart>(&r.start)) {
        if (supplied->history.size() != size || !finite(supplied->history))
            out.push_back(
                invalid("history.initial",
                        "Supplied full-history vector has invalid shape or non-finite entries."));
    }
    if(r.feasible_histories.relation.metadata()->set.dimension!=size)out.push_back(invalid("history.domain","Full feasible-history domain has the wrong ambient dimension."));
    const auto representation=r.feasible_histories.relation.representation();
    if(!std::holds_alternative<sets::HRepresentation>(representation)&&
       !std::holds_alternative<sets::SingletonRepresentation>(representation)&&
       !std::holds_alternative<sets::UniversalRepresentation>(representation))
        out.push_back(invalid("history.domain","Whole-history optimizer requires a nonempty H, singleton, or universal domain."));
    for(const auto& norm:r.source_cost.residual_norms) {
        if(norm.map.cols!=size||norm.map.rows>std::numeric_limits<std::size_t>::max()/std::max<std::size_t>(1,norm.map.cols)||
           norm.map.values.size()!=norm.map.rows*norm.map.cols||norm.target.size()!=norm.map.rows||norm.weights.size()!=norm.map.rows||
           !finite(norm.map.values)||!finite(norm.target)||!finite(norm.weights)||!std::isfinite(norm.coefficient)||norm.coefficient<0||
           std::any_of(norm.weights.begin(),norm.weights.end(),[](double v){return v<0;}))
            out.push_back(invalid("history.cost.norm","Compiled source norm has invalid dimensions, weights, or coefficient."));
    }
    if(out.empty()) {
        const auto recompilation=compile_history_cost(r.feasible_histories,r.source_cost.terminal_source,
            r.source_cost.running_source,r.source_cost.absolute_stage_offset);
        const auto* expected=std::get_if<HistoryCostProgram>(&recompilation);
        if(!expected) {
            if(const auto* diagnostics=std::get_if<Diagnostics>(&recompilation))out.insert(out.end(),diagnostics->begin(),diagnostics->end());
            else out.push_back(invalid("history.cost","Source cost could not be recompiled from its authored formulas."));
        } else {
            const auto same_norm=[](const WeightedHistoryResidualNorm& a,const WeightedHistoryResidualNorm& b) {
                return a.map.rows==b.map.rows&&a.map.cols==b.map.cols&&a.map.values==b.map.values&&
                    a.target==b.target&&a.weights==b.weights&&a.coefficient==b.coefficient;
            };
            const auto same=expected->quadratic.Q.values==r.source_cost.quadratic.Q.values&&
                expected->quadratic.linear==r.source_cost.quadratic.linear&&
                expected->quadratic.offset==r.source_cost.quadratic.offset&&
                expected->residual_norms.size()==r.source_cost.residual_norms.size()&&
                std::equal(expected->residual_norms.begin(),expected->residual_norms.end(),
                    r.source_cost.residual_norms.begin(),same_norm);
            if(!same)out.push_back({DiagnosticCode::evidence_mismatch,"history.cost","Compiled backend objective differs from recompiled authored terminal and running costs."});
        }
    }
    return out;
}

namespace detail {
std::optional<Diagnostic> check_history_initialization(const HistoryOptimizationRequest& r,
    const ExecutionContext& context) {
    const auto *supplied = std::get_if<SuppliedStart>(&r.start);
    if (!supplied)
        return std::nullopt;
    Diagnostic error{DiagnosticCode::invalid_input,"history.domain",""};
    const double violation =
        domain_violation(r.feasible_histories.relation, supplied->history, error);
    if(!error.explanation.empty())return error;
    if (violation >
        tolerance(context, domain_scale(r.feasible_histories.relation, supplied->history)))
        return invalid("history.initial",
                       "Supplied start history is outside the full feasible-history domain.");
    return std::nullopt;
}

HistoryOptimizationOutcome check_history_optimization_result(const HistoryOptimizationRequest& r,
    RawHistorySolve raw,const ExecutionContext& context) {
    const auto request_diagnostics=check_history_optimization_request(r);
    if(!request_diagnostics.empty())return request_diagnostics.front();
    const auto size=history_size(r.feasible_histories.coordinates);
    if (raw.history.size() != size || !finite(raw.history) ||
        !std::isfinite(raw.reported_objective))
        return invalid("history.backend.result",
                       "Backend returned malformed history or objective.");
    HistoryInitializationReceipt initialization;
    if (const auto *supplied = std::get_if<SuppliedStart>(&r.start)) {
        const auto *evidence = std::get_if<SuppliedReadbacks>(&raw.initialization);
        if (!evidence || evidence->supplied_history != supplied->history ||
            evidence->primal_readback != supplied->history ||
            evidence->dual_readback.size() != evidence->supplied_duals.size() ||
            !finite(evidence->supplied_duals) ||
            evidence->dual_readback != evidence->supplied_duals ||
            std::any_of(evidence->supplied_duals.begin(), evidence->supplied_duals.end(),
                        [](double v) { return v != 0; }))
            return invalid(
                "history.backend.readback",
                "Backend returned malformed supplied-start or actual primal/zero-dual readback evidence.");
        initialization =
            VerifiedSuppliedStart{evidence->supplied_history, evidence->primal_readback,
                                  evidence->supplied_duals, evidence->dual_readback};
    } else {
        const auto *evidence = std::get_if<BackendColdStartEvidence>(&raw.initialization);
        if (!evidence || evidence->backend_identity.empty() || evidence->start_policy.empty() ||
            evidence->readback_unavailable_reason.empty())
            return invalid(
                "history.backend.cold_start",
                "Backend cold-start evidence must identify its backend, policy, and unavailable readback reason.");
        initialization = *evidence;
    }
    if(const auto diagnostic=check_history_initialization(r,context))return *diagnostic;
    Diagnostic error{DiagnosticCode::invalid_input,"history.domain",""};
    const double violation=domain_violation(r.feasible_histories.relation,raw.history,error);
    if(!error.explanation.empty())return error;
    if(violation>tolerance(context,domain_scale(r.feasible_histories.relation,raw.history)))return invalid("history.backend.feasibility","Backend history violates the full feasible-history relation.");
    const auto [states,controls]=unpack(r.feasible_histories.coordinates,raw.history);
    auto cost=evaluate_history_cost(r.source_cost,states,controls);
    if(const auto* d=std::get_if<Diagnostics>(&cost))return d->front();
    if(const auto* stopped=std::get_if<OperationStopped>(&cost))return *stopped;
    const auto evaluation=std::get<HistoryCostEvaluation>(cost);
    if(std::abs(evaluation.total-raw.reported_objective)>tolerance(context,std::max(std::abs(evaluation.total),std::abs(raw.reported_objective))))
        return Diagnostic{DiagnosticCode::evidence_mismatch,"history.backend.objective","Backend objective does not match re-evaluation of the authored source cost."};
    return HistoryOptimizationResult{r.identity,
                                     std::move(raw.history),
                                     evaluation,
                                     raw.reported_objective,
                                     violation,
                                     std::move(initialization),
                                     std::move(raw.diagnostics)};
}
} // namespace detail
} // namespace csl::optimization

namespace csl::registry {
optimization::HistoryOptimizationOutcome HistoryOptimizerPort::run(Workspace& workspace,const Request& request,
    const ExecutionContext& context) {
    const auto invalid=optimization::check_history_optimization_request(request);
    if(!invalid.empty())return invalid.front();
    if(const auto diagnostic=optimization::detail::check_history_initialization(request,context))return *diagnostic;
    if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"History optimization cancelled before backend call"};
    if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
        return OperationStopped{StopReason::deadline_expired,"History optimization deadline expired before backend call"};
    auto raw=workspace.solve_candidate(request,context);
    if(const auto* stopped=std::get_if<OperationStopped>(&raw))return *stopped;
    if(const auto* diagnostic=std::get_if<Diagnostic>(&raw))return *diagnostic;
    if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"History optimization cancelled during backend call"};
    if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
        return OperationStopped{StopReason::deadline_expired,"History optimization deadline expired during backend call"};
    return optimization::detail::check_history_optimization_result(request,
        std::get<optimization::RawHistorySolve>(std::move(raw)),context);
}
} // namespace csl::registry
