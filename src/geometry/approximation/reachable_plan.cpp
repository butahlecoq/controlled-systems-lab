#include <csl/geometry/reachable_plan.hpp>
#include <csl/sets/data.hpp>
#include "../exact_dyadic.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>

namespace csl::geometry::approximation {
namespace {
using verification::CheckStatus;

void diagnose(PlanCheck& report,DiagnosticCode code,const char* field,const char* message) {
    report.diagnostics.push_back({code,field,message});
}

bool boundary(PlanCheck& report,const ExecutionContext& context) {
    if(context.cancellation.stop_requested()) {
        report.termination=Termination::cancelled;
        diagnose(report,DiagnosticCode::unsupported,"reachable_plan","cancellation observed");
        return false;
    }
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline) {
        report.termination=Termination::resource_limit;
        diagnose(report,DiagnosticCode::unsupported,"reachable_plan","deadline observed");
        return false;
    }
    return true;
}

bool exact_h_rows(const numeric::MatrixView& rows,const numeric::VectorView& values,
                  std::span<const double> point,bool equality,PlanCheck& report,
                  const ExecutionContext& context) {
    using namespace detail::exact_detail;
    for(std::size_t row=0;row<rows.rows();++row) {
        if(!boundary(report,context))return false;
        Integer difference;
        for(std::size_t col=0;col<rows.cols();++col) {
            if(!add_product(difference,decode(rows(row,col)),decode(point[col]))) {
                report.membership=CheckStatus::unsupported;
                diagnose(report,DiagnosticCode::unsupported,"reachable_plan.membership",
                    "exact native H membership arithmetic exceeded its checked range");
                return false;
            }
        }
        auto bound=decode(values[row]);bound.negative=!bound.negative;
        if(!add_dyadic(difference,bound)) {
            report.membership=CheckStatus::unsupported;
            diagnose(report,DiagnosticCode::unsupported,"reachable_plan.membership",
                "exact native H membership arithmetic exceeded its checked range");
            return false;
        }
        if(equality?!is_zero(difference):(!difference.negative&&!is_zero(difference))) {
            report.membership=CheckStatus::violation;
            diagnose(report,DiagnosticCode::invalid_claim,"reachable_plan.membership",
                "selected stage state is outside the admitted inner set");
            return false;
        }
    }
    return true;
}

CheckStatus native_membership(const SetHandle& handle,std::span<const double> point,
                              PlanCheck& report,const ExecutionContext& context) {
    if(!std::all_of(point.begin(),point.end(),[](double value){return std::isfinite(value);})) {
        diagnose(report,DiagnosticCode::invalid_input,"reachable_plan.state","stage state has nonfinite coordinates");
        return CheckStatus::invalid_input;
    }
    const auto native=sets::from_handle(handle);
    const auto* data=std::get_if<sets::SetData>(&native);
    if(!data) {
        diagnose(report,DiagnosticCode::unsupported,"reachable_plan.membership","inner output is not native set data");
        return CheckStatus::unsupported;
    }
    const auto representation=data->representation();
    if(std::holds_alternative<sets::UniversalRepresentation>(representation))return CheckStatus::numerical_pass;
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(std::holds_alternative<sets::EmptyRepresentation>(representation) ||
       (v && v->vertices.rows()==0)) {
        diagnose(report,DiagnosticCode::invalid_claim,"reachable_plan.membership","empty inner set has no member");
        return CheckStatus::violation;
    }
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        for(std::size_t i=0;i<point.size();++i)
            if(point[i]!=singleton->point[i]) {
                diagnose(report,DiagnosticCode::invalid_claim,"reachable_plan.membership",
                    "selected stage state differs from inner singleton");
                return CheckStatus::violation;
            }
        return CheckStatus::numerical_pass;
    }
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation)) {
        if(!exact_h_rows(h->inequalities,h->upper_bounds,point,false,report,context) ||
           !exact_h_rows(h->equalities,h->equality_values,point,true,report,context))
            return report.membership;
        return CheckStatus::numerical_pass;
    }
    diagnose(report,DiagnosticCode::unsupported,"reachable_plan.membership",
        "no independent native membership check for the inner representation");
    return CheckStatus::unsupported;
}

bool same_set(const SetHandle& a,const SetHandle& b) {
    return a.id==b.id && a.payload==b.payload &&
        a.metadata.dimension==b.metadata.dimension &&
        a.metadata.representation==b.metadata.representation &&
        a.metadata.convex==b.metadata.convex &&
        a.metadata.polyhedral==b.metadata.polyhedral &&
        a.metadata.bounded==b.metadata.bounded;
}

bool supported_profile(const problem::ResolvedProblem& original) {
    const auto& authored=*original.description();
    if(authored.information!=InformationPattern::nominal_open_loop ||
       !std::holds_alternative<KnownInitial>(authored.initial))return false;
    return !authored.external || std::holds_alternative<KnownExternalSequence>(*authored.external);
}
}

PlanCheck check_inner_state_plan(const problem::ResolvedProblem& original,const StageSetReference& reference,
    const registry::Registry<registry::ApproximationPort>& methods,registry::Method method,
    const ApproximationRequest& request,const Witness& witness,const ExecutionContext& context) {
    PlanCheck report;
    const auto model=original.model();
    const auto dimension=model.dimensions().state;
    bool coordinates_match=reference.state_coordinates.size()==dimension;
    for(std::size_t i=0;coordinates_match && i<dimension;++i)
        coordinates_match=reference.state_coordinates[i]==i;
    if(reference.problem!=original.identity() || request.identity.problem!=original.identity() ||
       reference.reference_id.value.empty() || reference.reference_id!=request.identity.ideal_output ||
       !same_set(reference.set,request.input) || reference.set.metadata.dimension!=dimension ||
       reference.stage.value>model.horizon() || !coordinates_match ||
       request.direction!=SetRelation::inner || request.assurance!=Assurance::numerical) {
        report.membership=CheckStatus::invalid_input;
        diagnose(report,DiagnosticCode::evidence_mismatch,"reachable_plan.reference",
            "stage, problem, source set, coordinate map or inner numerical request differs from the resolved reference");
        return report;
    }
    if(!supported_profile(original)) {
        report.membership=CheckStatus::unsupported;
        diagnose(report,DiagnosticCode::unsupported,"reachable_plan.profile",
            "requires nominal open-loop, known initial state and absent or known external sequence");
        return report;
    }
    if(!boundary(report,context))return report;
    report.approximation=run_registered(methods,std::move(method),request,context);
    const auto* enclosed=std::get_if<EnclosedApproximation>(&*report.approximation);
    if(!enclosed) {
        if(const auto* stopped=std::get_if<OperationStopped>(&*report.approximation)) {
            switch(stopped->reason) {
            case StopReason::cancelled: report.termination=Termination::cancelled;break;
            case StopReason::deadline_expired:
            case StopReason::resource_limit: report.termination=Termination::resource_limit;break;
            case StopReason::numerical_failure: report.termination=Termination::numerical_failure;break;
            }
        } else if(std::holds_alternative<registry::Rejection>(*report.approximation))
            report.termination=Termination::operation_rejected;
        else report.termination=Termination::contract_rejected;
        report.membership=CheckStatus::unsupported;
        diagnose(report,DiagnosticCode::unsupported,"reachable_plan.approximation",
            "requested inner set was not independently admitted");
        return report;
    }
    if(witness.states.size()<=reference.stage.value ||
       witness.states[reference.stage.value].size()!=dimension) {
        report.membership=CheckStatus::invalid_input;
        diagnose(report,DiagnosticCode::invalid_input,"reachable_plan.state","missing or malformed selected stage state");
        return report;
    }
    if(!boundary(report,context))return report;
    report.membership=native_membership(enclosed->result.output,witness.states[reference.stage.value],report,context);
    if(report.membership!=CheckStatus::numerical_pass || report.termination!=Termination::completed)return report;
    verification::TrajectoryRequest trajectory_request;trajectory_request.witness=witness;
    report.trajectory=verification::verify_trajectory(original,trajectory_request,context);
    report.termination=report.trajectory->termination;
    if(report.termination==Termination::completed &&
       report.trajectory->bindings==CheckStatus::numerical_pass &&
       report.trajectory->feasibility==CheckStatus::numerical_pass &&
       report.trajectory->objective==CheckStatus::numerical_pass &&
       report.trajectory->recomputed_objective &&
       std::isfinite(*report.trajectory->recomputed_objective))
        report.numerical_achievable_value=*report.trajectory->recomputed_objective;
    return report;
}

} // namespace csl::geometry::approximation
