#include "convex_report.hpp"
#include <cmath>
namespace csl::reporting::convex {
namespace {
void check(TrialRecord& r,bool ok,const char* message) {if(!ok) r.errors.emplace_back(message);}
std::string bounds(const std::vector<csl::Interval>& b) {return array(b,[](const auto& x){return "["+optional_number(x.lower)+","+optional_number(x.upper)+"]";});}
std::string matrix(const Matrix& m) {return "{\"rows\":"+std::to_string(m.rows)+",\"cols\":"+std::to_string(m.cols)+",\"values\":"+numbers(m.values)+"}";}
std::string objective_json(const TerminalObjective& objective) {
    return std::visit([](const auto& o)->std::string {
        using T=std::decay_t<decltype(o)>;
        if constexpr(std::is_same_v<T,LinearTerminal>) return "{\"kind\":\"linear\",\"coefficients\":"+numbers(o.coefficients)+",\"offset\":"+json_number(o.offset)+"}";
        else if constexpr(std::is_same_v<T,QuadraticTerminal>) return "{\"kind\":\"quadratic\",\"Q\":"+matrix(o.Q)+",\"linear\":"+numbers(o.linear)+",\"offset\":"+json_number(o.offset)+"}";
        else return "{\"kind\":\"residual_norm\",\"L\":"+matrix(o.map)+",\"target\":"+numbers(o.target)+"}";
    },objective);
}
TerminalObjective solver_snapshot(const ConvexProgram& p) {
    const auto q=std::get<optimization::QuadraticCoefficients>(p.quadratic_program().objective().coefficients());
    Matrix m{q.Q.rows(),q.Q.cols(),{}};
    for(std::size_t i=0;i<m.rows;++i) for(std::size_t j=0;j<m.cols;++j) m.values.push_back(q.Q(i,j));
    return QuadraticTerminal{std::move(m),Vector(q.linear.values().begin(),q.linear.values().end()),q.offset};
}
void verify(const Fixture& f,TrialRecord& r) {
    if(!r.result) {r.errors.emplace_back("no returned ProgramResult");return;}
    const auto& value=*r.result;
    check(r,value.termination==Termination::completed,"termination differs from completed reference");
    check(r,value.outcome.value==f.expected,"outcome differs from independent reference");
    check(r,value.outcome.subject==f.input.identity,"original subject differs");
    check(r,std::holds_alternative<Unestablished>(value.outcome.support),"unexpected assurance");
    check(r,!value.objective.lower && !value.objective.upper,"unexpected bound");
    check(r,optimization::check_program_result(value,*r.program,Assurance::numerical).empty(),"canonical result check failed");
    check(r,r.attempt && r.attempt->state==SolveAttemptState::returned_result && r.attempt->stamp.attempt()==1 && r.attempt->stamp.program().identity()==f.input.identity,"authoritative attempt mismatch");
    if(value.primal) {
        const auto evaluated=optimization::evaluate_primal(*r.program,*value.primal,{1e-8,1e-8},{{"convex-report.canonical-cross-check"},"1"});
        if(const auto* e=std::get_if<optimization::ConvexPrimalEvaluation>(&evaluated)) {r.objective=e->original_objective;r.solver_objective=e->solver_objective;}
    }
    if(f.expected!=MathematicalOutcome::optimal) return;
    check(r,value.primal && value.primal->size()==f.input.variables.size(),"optimal candidate dimension");
    if(!value.primal || value.primal->size()!=f.input.variables.size()) return;
    const auto& x=*value.primal;
    const auto in=[](double v,const csl::Interval& b){return (!b.lower || v>=*b.lower || close(v,*b.lower)) && (!b.upper || v<=*b.upper || close(v,*b.upper));};
    for(std::size_t i=0;i<x.size();++i) {
        check(r,in(x[i],f.input.variables[i]),"independent variable violation");
        if(f.point) check(r,close(x[i],(*f.point)[i]),"literal point differs");
        if(!f.coordinate_constraints.empty()) check(r,in(x[i],f.coordinate_constraints[i]),"analytic minimizer family predicate differs");
    }
    const auto& a=f.input.constraints;
    for(std::size_t i=0;i<a.rows;++i) {
        double activity=0;for(std::size_t j=a.row_offsets[i];j<a.row_offsets[i+1];++j) activity+=a.values[j]*x[a.column_indices[j]];
        check(r,in(activity,f.input.rows[i]),"independent row violation");
    }
    check(r,r.objective && f.objective && close(*r.objective,*f.objective),"literal original cost differs");
    check(r,r.solver_objective && f.solver_objective && close(*r.solver_objective,*f.solver_objective),"literal solver cost differs");
    // Independent case formulas, not a second general objective engine.
    double direct=0, squared=0;
    if(f.id=="quadratic-boundary" || f.id=="quadratic-zero-row" || f.id=="norm-zero") direct=squared=(x[0]-3)*(x[0]-3);
    else if(f.id=="quadratic-equality") direct=squared=2*x[0]*x[0]+2*x[0]*x[1]+2*x[1]*x[1]-8*x[0]-10*x[1]+17;
    else if(f.id=="norm-positive") {squared=(x[0]-3)*(x[0]-3)+16;direct=std::sqrt(squared);}
    else if(f.id=="norm-constant") {direct=5;squared=25;}
    else if(f.id=="quadratic-face") direct=squared=(x[0]-1)*(x[0]-1);
    else if(x.empty()) direct=squared=*f.objective;
    else {r.errors.emplace_back("missing independent formula");return;}
    if(f.id=="norm-zero") direct=std::abs(x[0]-3);
    check(r,r.objective && close(direct,*r.objective) && r.solver_objective && close(squared,*r.solver_objective),"independent direct formula differs");
    check(r,value.residuals.primal.has_value() && value.residuals.dual.has_value(),"original residuals unavailable");
    if(value.residuals.primal) {
        const auto& p=*value.residuals.primal;check(r,p.context.subject==f.input.identity && passes(p.rows,p.context) && passes(p.variables,p.context),"primal residuals failed");
    }
    if(value.residuals.dual) {
        const auto& d=*value.residuals.dual;check(r,d.context.subject==f.input.identity && d.stationarity && d.signs && d.complementarity && passes(*d.stationarity,d.context) && passes(*d.signs,d.context) && passes(*d.complementarity,d.context),"dual residuals failed");
    }
}
}
const std::vector<Fixture>& catalogue() {
    static const std::vector<Fixture> cases{
        {"quadratic-boundary",{{{"convex-report-literals"},{"quadratic-boundary"}},QuadraticTerminal{{1,1,{2}},{-6},9},{0,1,{0},{},{}},{{0,2}},{},{}},MathematicalOutcome::optimal,Vector{2},{},1,1,"(x-3)^2 decreases on [0,2]; minimum1 at2."},
        {"quadratic-equality",{{{"convex-report-literals"},{"quadratic-equality"}},QuadraticTerminal{{2,2,{4,2,2,4}},{-8,-10},17},{1,2,{0,2},{0,1},{1,1}},{{{},{}},{{},{}}},{{2,2}},{}},MathematicalOutcome::optimal,Vector{.5,1.5},{},4.5,4.5,"Substitute y=2-x: 2x^2-2x+5; minimum4.5 at(.5,1.5)."},
        {"norm-positive",{{{"convex-report-literals"},{"norm-positive"}},ResidualNormTerminal{{2,1,{1,0}},{3,-4}},{0,1,{0},{},{}},{{0,2}},{},ProgramId{"norm-positive-squared"}},MathematicalOutcome::optimal,Vector{2},{},std::sqrt(17.0),17,"sqrt((x-3)^2+16) minimizes at2; original sqrt17, squared17."},
        {"norm-zero",{{{"convex-report-literals"},{"norm-zero"}},ResidualNormTerminal{{1,1,{1}},{3}},{0,1,{0},{},{}},{{0,5}},{},ProgramId{"norm-zero-squared"}},MathematicalOutcome::optimal,Vector{3},{},0,0,"Absolute residual |x-3| has minimum0 at3."},
        {"norm-constant",{{{"convex-report-literals"},{"norm-constant"}},ResidualNormTerminal{{2,1,{0,0}},{3,4}},{0,1,{0},{},{}},{{0,1}},{},ProgramId{"norm-constant-squared"}},MathematicalOutcome::optimal,{},{{0,1}},5,25,"Every x in [0,1] minimizes the constant norm5; square25."},
        {"quadratic-face",{{{"convex-report-literals"},{"quadratic-face"}},QuadraticTerminal{{2,2,{2,0,0,0}},{-2,0},1},{0,2,{0},{},{}},{{0,2},{0,1}},{},{}},MathematicalOutcome::optimal,{},{{1,1},{0,1}},0,0,"(x-1)^2 has minimum0 on the complete segment (1,t), t in [0,1]."},
        {"quadratic-zero-row",{{{"convex-report-literals"},{"quadratic-zero-row"}},QuadraticTerminal{{1,1,{2}},{-6},9},{1,1,{0,0},{},{}},{{1,5}},{{0,0}},{}},MathematicalOutcome::optimal,Vector{3},{},0,0,"Authored zero equality is redundant; (x-3)^2 minimizes at3."},
        {"quadratic-zero-contradiction",{{{"convex-report-literals"},{"quadratic-zero-contradiction"}},QuadraticTerminal{{1,1,{2}},{-6},9},{1,1,{0,0},{},{}},{{1,5}},{{1,1}},{}},MathematicalOutcome::infeasible,{},{},{},{},"Authored row 0=1 is contradictory regardless of x."},
        {"quadratic-unbounded",{{{"convex-report-literals"},{"quadratic-unbounded"}},QuadraticTerminal{{2,2,{2,0,0,0}},{0,-1},0},{0,2,{0},{},{}},{{{},{}},{0,{}}},{},{}},MathematicalOutcome::unbounded,{},{},{},{},"Along (0,t), t>=0, x^2-y=-t tends to minus infinity."}
    };return cases;
}
TrialRecord run_trial(const Fixture& f,std::stop_token cancellation,adapters::convex::HighsConvexOptions options) {
    using namespace registry;
    TrialRecord record;record.timings[5].available=true;record.timings[5].start=now();
    try {
        record_failure_unwind(record.timings[5],[&] {
            record.program=timed(record.timings[0],[&]{const auto input=f.input;return accepted<ConvexProgram>(optimization::make_convex_program(input));});
            const auto plan=timed(record.timings[1],[&]{
                Registry<ConvexPort> registry;
                auto entry=accepted<Registration<ConvexPort>>(adapters::convex::make_highs_registration(options));
                record.actual_version=entry.identity.version;
                if(auto rejected=registry.add(std::move(entry))) throw Rejected(rejected->diagnostics);
                Requirements requirements;requirements.output.representation={"csl.program-result.v1"};
                return accepted<PreparedPipeline<ConvexPort>>(prepare_pipeline(select(registry,{{"csl.convex.highs"},{}},*record.program,requirements)));
            });
            auto workers=timed(record.timings[2],[&]{return plan.create();});auto& worker=std::get<0>(workers);
            ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),cancellation,{},{1e-8,1e-8},"convex-report"};
            ProgramOutcome outcome=Unsupported{};
            try {outcome=timed(record.timings[3],[&]{auto r=worker->run(context);record.observation=observe(r);return r;});}
            catch(...) {record.attempt=worker->last_attempt();throw;}
            record.attempt=worker->last_attempt();
            if(auto* r=std::get_if<ProgramResult>(&outcome)) {record.result=std::move(*r);record.harness_status="returned";}
            else {record.harness_status="unsupported";record.diagnostics=std::get<Unsupported>(outcome).diagnostics;record.error=diagnostic_text(record.diagnostics);}
            timed(record.timings[4],[&]{verify(f,record);return true;});
            record.timings[5].end=now();
        });
    } catch(const Rejected& e) {
        record.diagnostics=e.diagnostics;record.harness_status=std::any_of(e.diagnostics.begin(),e.diagnostics.end(),[](const auto& d){return d.code==DiagnosticCode::unsupported;})?"unsupported":"exception";
        record.error=e.what();record.errors.push_back(record.error);
    } catch(const std::exception& e) {record.error=e.what();record.errors.push_back(record.error);}
      catch(...) {record.error="non-standard exception";record.errors.push_back(record.error);}
    return record;
}
std::string catalogue_json() {
    return array(catalogue(),[](const Fixture& f){
        const auto p=accepted<ConvexProgram>(optimization::make_convex_program(f.input));
        const auto& a=f.input.constraints;
        const auto indices=[](const auto& values){return array(values,[](auto x){return std::to_string(x);});};
        return "{\"case_id\":"+json_string(f.id)+",\"identity\":"+identity_json(f.input.identity)+",\"input\":{\"objective\":"+objective_json(f.input.objective)+",\"constraints\":{\"rows\":"+std::to_string(a.rows)+",\"cols\":"+std::to_string(a.cols)+",\"starts\":"+indices(a.row_offsets)+",\"indices\":"+indices(a.column_indices)+",\"values\":"+numbers(a.values)+"},\"variables\":"+bounds(f.input.variables)+",\"rows\":"+bounds(f.input.rows)+"},\"solver\":{\"identity\":"+identity_json(p.quadratic_program().identity())+",\"objective\":"+objective_json(solver_snapshot(p))+",\"transformation\":"+(p.reformulation()?json_string("residual_norm_squared"):"null")+"},\"reference\":{\"outcome\":"+json_string(outcome_name(f.expected))+",\"point\":"+(f.point?numbers(*f.point):"null")+",\"coordinate_constraints\":"+bounds(f.coordinate_constraints)+",\"objective\":"+optional_number(f.objective)+",\"solver_objective\":"+optional_number(f.solver_objective)+",\"derivation\":"+json_string(f.derivation)+"},\"assumptions\":[\"continuous variables\",\"minimization\",\"binary64 numerical output; outcome support unestablished\"]}";
    });
}
std::string trial_json(const Fixture& f,const TrialRecord& r,std::size_t round,std::size_t sequence,const std::string& purpose) {
    std::string result="null";
    if(r.result) {
        const auto& v=*r.result;
        result="{\"termination\":"+json_string(termination_name(v.termination))+",\"outcome\":"+json_string(outcome_name(v.outcome.value))+",\"support\":{\"kind\":"+json_string(std::holds_alternative<Unestablished>(v.outcome.support)?"unestablished":"unsupported-projection")+"},\"primal\":"+(v.primal?numbers(*v.primal):"null")+",\"original_objective\":"+optional_number(r.objective)+",\"solver_objective\":"+optional_number(r.solver_objective)+",\"objective_unavailable_reason\":"+(r.objective?"null":json_string("no finite evaluated objective"))+",\"bounds\":{\"lower\":null,\"upper\":null},\"family\":{\"available\":false,\"reason\":\"point only\"},\"primal_residuals\":"+primal_json(v.residuals.primal)+",\"dual_residuals\":"+dual_json(v.residuals.dual)+",\"raw_diagnostics\":"+json_string(v.raw_diagnostics)+"}";
    }
    auto out=trial_envelope(f.id,f.input.identity,"csl.convex.highs",r,result,round,sequence,purpose);
    out.pop_back();return out+",\"public_run_entered\":"+(r.timings[3].available?"true":"false")+"}";
}
} // namespace csl::reporting::convex
