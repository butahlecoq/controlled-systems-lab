#include <csl/optimization/validated_finite_action_minimax.hpp>
#include "detail/outward_interval.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <limits>

namespace csl::optimization {
ValidatedMinimaxBounds::ValidatedMinimaxBounds(ProblemId problem, RequestId request,
        double lower, double upper, std::vector<ValidatedPlanEvidence> plans)
    : problem_(std::move(problem)), request_(std::move(request)), lower_(lower),
      upper_(upper), plans_(std::move(plans)) {}
struct ValidatedMinimaxBuilder {
    static ValidatedMinimaxBounds make(const ProblemId& p, const RequestId& r,
            double lo, double hi, std::vector<ValidatedPlanEvidence> plans) {
        return {p,r,lo,hi,std::move(plans)};
    }
    static ValidatedMinimaxInfeasible infeasible(const ProblemId& problem,
            const RequestId& request, std::vector<ValidatedPlanEvidence> plans) {
        return ValidatedMinimaxInfeasible{problem,request,std::move(plans)};
    }
    static ValidatedMinimaxUnresolved unresolved(const ProblemId& problem,
            const RequestId& request, std::vector<ValidatedPlanEvidence> plans) {
        return ValidatedMinimaxUnresolved{problem,request,std::move(plans)};
    }
};
namespace {
using detail::Interval;
using detail::add;
using detail::multiply;
using detail::square;
using detail::square_root;
using Points = std::vector<Vector>;
Unsupported reject(std::string f,std::string e,DiagnosticCode c=DiagnosticCode::unsupported) {
    return {{{c,std::move(f),std::move(e)}}};
}
bool should_stop(const ExecutionContext& c) {
    return c.cancellation.stop_requested() || (c.deadline && std::chrono::steady_clock::now()>=*c.deadline);
}
OperationStopped stopped(const ExecutionContext& c) {
    if(c.cancellation.stop_requested())return {StopReason::cancelled,"Validated minimax cancelled."};
    return {StopReason::deadline_expired,"Validated minimax deadline expired."};
}
std::variant<Points,Unsupported> extract_points(const sets::SetData& set) {
    const auto rep=set.representation(); const auto n=set.metadata()->set.dimension;
    Points out;
    if(const auto* s=std::get_if<sets::SingletonRepresentation>(&rep))
        out.emplace_back(s->point.values().begin(),s->point.values().end());
    else if(const auto* v=std::get_if<sets::VRepresentation>(&rep)) {
        if(v->rays.rows())return reject("validated.set.rays","Unbounded V sets are unsupported.");
        for(std::size_t i=0;i<v->vertices.rows();++i){Vector p(n);for(std::size_t j=0;j<n;++j)p[j]=v->vertices(i,j);out.push_back(std::move(p));}
    } else if(!std::holds_alternative<sets::EmptyRepresentation>(rep))
        return reject("validated.set.representation","Expected complete bounded native V, singleton, or empty set.");
    for(const auto& p:out)for(double x:p)if(!std::isfinite(x))
        return reject("validated.set.finite","Set coordinates must be finite.",DiagnosticCode::invalid_input);
    return out;
}
bool product(std::size_t& x,std::size_t y) {
    if(y&&x>std::numeric_limits<std::size_t>::max()/y)return false;
    x*=y;
    return true;
}
struct Meter {
    std::size_t used{},limit{};
    const ExecutionContext* context{};
    bool exhausted{},stopped{};
    bool op(){
        if(context&&should_stop(*context)){stopped=true;return false;}
        if(used>=limit){exhausted=true;return false;}
        ++used;return true;
    }
};
struct Check { bool violation{},overlap{}; std::size_t row{};ConstraintKind kind{};Interval residual{}; };
std::vector<Check> check_safe(const sets::SetData& set,const std::vector<Interval>& x,Meter& m,
        const ExecutionContext& context) {
    const auto rep=set.representation();std::vector<Check> out;
    if(std::holds_alternative<sets::UniversalRepresentation>(rep))return out;
    if(std::holds_alternative<sets::EmptyRepresentation>(rep))return {{true,false,0,ConstraintKind::empty_set,{0,0}}};
    auto rows=[&](const numeric::MatrixView& a,const numeric::VectorView& b,bool equality){
        for(std::size_t r=0;r<a.rows();++r){if(should_stop(context))return false;Interval v{-b[r],-b[r]};for(std::size_t c=0;c<x.size();++c){if(!m.op()||!m.op())return false;v=add(v,multiply({a(r,c),a(r,c)},x[c]));}
            const auto kind=equality?ConstraintKind::equality:ConstraintKind::inequality;
            if(equality){if(v.lower==0&&v.upper==0)out.push_back({false,false,r,kind,v});else if(v.upper<0||v.lower>0)out.push_back({true,false,r,kind,v});else out.push_back({false,true,r,kind,v});}
            else if(v.upper<=0)out.push_back({false,false,r,kind,v});else if(v.lower>0)out.push_back({true,false,r,kind,v});else out.push_back({false,true,r,kind,v});
        }return true;};
    if(const auto* h=std::get_if<sets::HRepresentation>(&rep)){if(!rows(h->inequalities,h->upper_bounds,false)||!rows(h->equalities,h->equality_values,true))out.push_back({false,true,0,ConstraintKind::inequality,detail::whole()});}
    else {const auto* s=std::get_if<sets::SingletonRepresentation>(&rep);for(std::size_t i=0;i<x.size();++i){if(should_stop(context)||!m.op())break;auto v=add(x[i],{-s->point[i],-s->point[i]});if(v.lower==0&&v.upper==0)out.push_back({false,false,i,ConstraintKind::singleton_coordinate,v});else if(v.upper<0||v.lower>0)out.push_back({true,false,i,ConstraintKind::singleton_coordinate,v});else out.push_back({false,true,i,ConstraintKind::singleton_coordinate,v});}}
    return out;
}
Interval evaluate(const ObjectiveCoefficients& o,const std::vector<Interval>& x,Meter& m) {
    return std::visit([&](const auto& c)->Interval{using T=std::decay_t<decltype(c)>;
        if constexpr(std::is_same_v<T,LinearCoefficients>){Interval y{c.offset,c.offset};for(std::size_t i=0;i<x.size();++i){if(!m.op()||!m.op())return detail::whole();y=add(y,multiply({c.coefficients[i],c.coefficients[i]},x[i]));}return y;}
        else if constexpr(std::is_same_v<T,ResidualCoefficients>){Interval q{0,0};for(std::size_t r=0;r<c.map.rows();++r){Interval v{-c.target[r],-c.target[r]};for(std::size_t j=0;j<x.size();++j){if(!m.op()||!m.op())return detail::whole();v=add(v,multiply({c.map(r,j),c.map(r,j)},x[j]));}if(!m.op()||!m.op())return detail::whole();q=add(q,square(v));}if(!m.op())return detail::whole();return square_root(q);}
        else return {detail::negative_infinity,detail::positive_infinity};},o);
}
}

ValidatedFiniteActionMinimaxOutcome validated_finite_action_minimax(
        const ValidatedFiniteActionMinimaxRequest& q,ValidatedFiniteActionMinimaxLimits limits,
        const ExecutionContext& context) {
    if(!detail::supported_rounding_mode())return OperationStopped{StopReason::numerical_failure,"Validated intervals require FE_TONEAREST."};
    const auto dims=q.system.dimensions();const auto T=q.system.horizon();
    if(q.problem.value.empty()||q.request.value.empty())return reject("validated.identity","Problem and request IDs must be nonempty.",DiagnosticCode::invalid_input);
    if(q.actions.dimension!=dims.control||q.initial.metadata()->set.dimension!=dims.state||q.disturbances.size()!=T||q.safe_sets.size()!=T+1||q.objective.dimension()!=dims.state)
        return reject("validated.dimensions","Request dimensions differ from the model.",DiagnosticCode::invalid_input);
    if(q.objective.policy().assurance!=Assurance::numerical)return reject("validated.objective.assurance","Only stored binary64 objective coefficients are admitted.");
    const auto objective=q.objective.coefficients();
    if(std::holds_alternative<QuadraticCoefficients>(objective))return reject("validated.objective.quadratic","Quadratic objectives are unsupported without validated PSD evidence.");
    for(const auto& a:q.actions.catalogue){if(a.size()!=dims.control)return reject("validated.action.dimension","Action dimension mismatch.",DiagnosticCode::invalid_input);for(double x:a)if(!std::isfinite(x))return reject("validated.action.finite","Actions must be finite.",DiagnosticCode::invalid_input);}
    for(const auto& s:q.safe_sets){if(s.metadata()->set.dimension!=dims.state)return reject("validated.safe.dimension","Safe-set dimension mismatch.",DiagnosticCode::invalid_input);const auto& labels=s.metadata()->coordinate_labels;const auto& state_labels=q.initial.metadata()->coordinate_labels;if(!labels.empty()&&!state_labels.empty()&&labels!=state_labels)return reject("validated.safe.coordinates","Safe-set coordinate labels differ from initial-state labels.",DiagnosticCode::invalid_input);auto r=s.representation();if(!std::holds_alternative<sets::HRepresentation>(r)&&!std::holds_alternative<sets::SingletonRepresentation>(r)&&!std::holds_alternative<sets::EmptyRepresentation>(r)&&!std::holds_alternative<sets::UniversalRepresentation>(r))return reject("validated.safe.representation","Safe sets require H, singleton, empty or universal representations.");}
    auto initial_result=extract_points(q.initial);if(auto* e=std::get_if<Unsupported>(&initial_result))return *e;
    auto initial=std::get<Points>(std::move(initial_result));
    std::vector<Points> disturbances;for(const auto& d:q.disturbances){if(d.metadata()->set.dimension!=dims.external)return reject("validated.disturbance.dimension","Disturbance dimension mismatch.",DiagnosticCode::invalid_input);auto p=extract_points(d);if(auto* e=std::get_if<Unsupported>(&p))return *e;disturbances.push_back(std::get<Points>(std::move(p)));}
    std::size_t histories=initial.size();for(const auto& d:disturbances)if(!product(histories,d.size()))return reject("validated.histories.overflow","History count overflows size_t.");
    if(histories==0)return ValidatedMinimaxNoScenarios{};
    if(T&&q.actions.catalogue.empty())return ValidatedMinimaxEmptyCatalogue{};
    std::size_t plans=1;for(std::size_t i=0;i<T;++i)if(!product(plans,q.actions.catalogue.size()))return reject("validated.plans.overflow","Plan count overflows size_t.");
    if(plans>limits.max_plans)return reject("validated.plans.limit","Plan count exceeds caller limit.");
    if(histories>limits.max_histories_per_plan)return reject("validated.histories.limit","Histories exceed caller limit.");
    std::vector<ValidatedPlanEvidence> ledger;ledger.reserve(plans);std::vector<std::size_t> choices(T);
    double lower=detail::positive_infinity,upper=detail::positive_infinity;bool any_feasible=false,any_overlap=false;std::size_t total_operations=0;
    for(std::size_t pi=0;pi<plans;++pi){if(should_stop(context))return stopped(context);Meter meter{total_operations,limits.max_interval_operations,&context};
        std::vector<Interval> terminal_box(dims.state,{detail::positive_infinity,detail::negative_infinity});double plan_lower=detail::negative_infinity;std::size_t examined=0;
        std::optional<ValidatedPlanInfeasible> violation;std::optional<SafetyOverlap> overlap;std::vector<SafetyMargin> margins;std::optional<Unsupported> failure;bool arithmetic_failure=false;
        std::function<void(std::size_t,const std::vector<Interval>&,HistoryPath)> walk;
        walk=[&](std::size_t stage,const std::vector<Interval>& x,HistoryPath path){
            if(violation||failure||arithmetic_failure||should_stop(context)||meter.exhausted||meter.stopped)return;
            const auto checks=check_safe(q.safe_sets[stage],x,meter,context);if(should_stop(context)||meter.exhausted||meter.stopped)return;for(const auto& c:checks){
                if(!std::isfinite(c.residual.lower)||!std::isfinite(c.residual.upper)){arithmetic_failure=true;return;}
                if(c.violation){violation=ValidatedPlanInfeasible{choices,{stage,path,c.row,c.kind,{c.residual.lower,c.residual.upper}}};return;}
                if(c.overlap&&!overlap)overlap=SafetyOverlap{stage,path,c.row,c.kind,{c.residual.lower,c.residual.upper}};
                auto it=std::find_if(margins.begin(),margins.end(),[&](const SafetyMargin& a){return a.stage==stage&&a.row==c.row&&a.kind==c.kind;});
                if(it==margins.end())margins.push_back({stage,c.row,c.kind,{c.residual.lower,c.residual.upper}});else{it->residual_hull.lower=std::min(it->residual_hull.lower,c.residual.lower);it->residual_hull.upper=std::max(it->residual_hull.upper,c.residual.upper);}
            }
            if(stage==T){++examined;auto v=evaluate(objective,x,meter);if(!std::isfinite(v.lower)||!std::isfinite(v.upper)){arithmetic_failure=true;return;}plan_lower=std::max(plan_lower,v.lower);for(std::size_t j=0;j<x.size();++j){terminal_box[j].lower=std::min(terminal_box[j].lower,x[j].lower);terminal_box[j].upper=std::max(terminal_box[j].upper,x[j].upper);}return;}
            auto ds=q.system.stage({stage});if(!std::holds_alternative<model::DynamicsStage>(ds)){failure=reject("validated.dynamics.stage","Could not access affine dynamics stage.");return;}const auto& d=std::get<model::DynamicsStage>(ds);
            for(std::size_t wi=0;wi<disturbances[stage].size();++wi){std::vector<Interval> y(dims.state);for(std::size_t r=0;r<dims.state;++r){Interval v{d.offset[r],d.offset[r]};for(std::size_t c=0;c<dims.state;++c){if(!meter.op()||!meter.op())return;v=add(v,multiply({d.A(r,c),d.A(r,c)},x[c]));}for(std::size_t c=0;c<dims.control;++c){if(!meter.op()||!meter.op())return;v=add(v,multiply({d.B(r,c),d.B(r,c)},{q.actions.catalogue[choices[stage]][c],q.actions.catalogue[choices[stage]][c]}));}for(std::size_t c=0;c<dims.external;++c){if(!meter.op()||!meter.op())return;v=add(v,multiply({d.E(r,c),d.E(r,c)},{disturbances[stage][wi][c],disturbances[stage][wi][c]}));}y[r]=v;}
                for(const auto& z:y)if(!std::isfinite(z.lower)||!std::isfinite(z.upper)){arithmetic_failure=true;return;}
                auto p=path;p.disturbance_vertices.push_back(wi);walk(stage+1,y,std::move(p));if(violation||failure||arithmetic_failure||should_stop(context)||meter.exhausted||meter.stopped)return;}
        };
        for(std::size_t iv=0;iv<initial.size();++iv){std::vector<Interval> x;for(double z:initial[iv])x.push_back({z,z});walk(0,x,HistoryPath{iv,{}});if(violation||failure||arithmetic_failure||should_stop(context)||meter.exhausted||meter.stopped)break;}
        if(should_stop(context))return stopped(context);
        if(meter.stopped)return stopped(context);
        if(meter.exhausted)return OperationStopped{StopReason::resource_limit,"Validated interval-operation limit exceeded."};
        if(arithmetic_failure)return OperationStopped{StopReason::numerical_failure,"Outward interval arithmetic could not produce finite bounds."};
        total_operations=meter.used;
        if(failure)return *failure;
        if(violation)ledger.emplace_back(std::move(*violation));else {auto u=evaluate(objective,terminal_box,meter);if(meter.stopped)return stopped(context);if(meter.exhausted)return OperationStopped{StopReason::resource_limit,"Validated interval-operation limit exceeded."};if(!std::isfinite(u.lower)||!std::isfinite(u.upper))return OperationStopped{StopReason::numerical_failure,"Objective interval could not produce finite bounds."};total_operations=meter.used;
            if(overlap){any_overlap=true;lower=std::min(lower,plan_lower);ledger.emplace_back(ValidatedPlanUnresolved{choices,{plan_lower,u.upper},examined,*overlap});}
            else{any_feasible=true;lower=std::min(lower,plan_lower);upper=std::min(upper,u.upper);ledger.emplace_back(ValidatedPlanFeasible{choices,{plan_lower,u.upper},examined,std::move(margins)});}}
        for(std::size_t i=T;i>0;--i){if(++choices[i-1]<q.actions.catalogue.size())break;choices[i-1]=0;}
    }
    if(any_feasible)return ValidatedMinimaxBuilder::make(q.problem,q.request,lower,upper,std::move(ledger));
    if(any_overlap)return ValidatedMinimaxBuilder::unresolved(q.problem,q.request,std::move(ledger));
    return ValidatedMinimaxBuilder::infeasible(q.problem,q.request,std::move(ledger));
}
} // namespace csl::optimization
