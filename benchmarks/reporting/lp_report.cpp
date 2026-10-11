#include "lp_report.hpp"
#include "ReportBuildInfo.hpp"
#include <csl/adapters/lp/highs.hpp>
#include <algorithm>
#include <bit>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>

namespace csl::reporting {
namespace {
constexpr std::array<const char*,6> phases{"input_publication","registration_preparation","workspace_creation","public_run","independent_verification","end_to_end"};
Clock::rep now() { return Clock::now().time_since_epoch().count(); }
std::string diagnostic_text(const Diagnostics& diagnostics) {
    std::string out;
    for(const auto& d:diagnostics) out+=d.field+": "+d.explanation+"\n";
    return out;
}
struct Rejected : std::runtime_error {
    Diagnostics diagnostics;
    explicit Rejected(Diagnostics d):std::runtime_error(diagnostic_text(d)),diagnostics(std::move(d)) {}
};
template<class F> auto timed(Interval& span, F&& action) {
    span.available=true; span.start=now();
    try { auto value=action(); span.end=now(); return value; }
    catch (...) { span.end=now(); throw; }
}
template<class T, class... Rest> T accepted(std::variant<T,Rest...> value) {
    if (auto* result=std::get_if<T>(&value)) return std::move(*result);
    auto diagnostics=std::visit([](const auto& alternative)->Diagnostics {
        if constexpr(std::is_same_v<std::decay_t<decltype(alternative)>,Diagnostics>) return alternative;
        else if constexpr(requires {alternative.diagnostics;}) return alternative.diagnostics;
        else return {};
    },value);
    throw Rejected(std::move(diagnostics));
}
bool close(double a, double b) { return std::isfinite(a) && std::isfinite(b) && std::abs(a-b)<=1e-8+1e-8*std::max(std::abs(a),std::abs(b)); }
bool passes(const ResidualMeasure& m, const ResidualContext& c) {
    return std::isfinite(m.violation) && std::isfinite(m.scale) && m.violation>=0 && m.scale>=0 &&
        m.violation<=c.absolute_tolerance+c.relative_tolerance*m.scale;
}
void check(TrialRecord& r, bool condition, const char* error) { if (!condition) r.errors.emplace_back(error); }
void observe(std::uint64_t& token, std::uint64_t value) { token ^= value; token *= UINT64_C(1099511628211); }
std::uint64_t observe(const ProgramOutcome& outcome) {
    std::uint64_t token=UINT64_C(14695981039346656037);
    observe(token,outcome.index());
    if (const auto* r=std::get_if<ProgramResult>(&outcome)) {
        observe(token,static_cast<std::uint64_t>(r->termination));
        observe(token,static_cast<std::uint64_t>(r->outcome.value));
        if (r->primal) for (double x:*r->primal) observe(token,std::bit_cast<std::uint64_t>(x));
        observe(token,r->residuals.primal.has_value()); observe(token,r->residuals.dual.has_value());
        observe(token,r->raw_diagnostics.size());
    }
    return token;
}
void verify(const Fixture& f, TrialRecord& r) {
    if (!r.result) { r.errors.emplace_back("no returned ProgramResult"); return; }
    const auto& result=*r.result;
    check(r,result.termination==Termination::completed,"termination differs from completed reference");
    check(r,result.outcome.value==f.expected,"outcome differs from analytic reference");
    check(r,result.outcome.subject==f.input.identity,"outcome subject mismatch");
    check(r,std::holds_alternative<Unestablished>(result.outcome.support),"unexpected evidence support");
    check(r,!result.objective.lower && !result.objective.upper,"unexpected bound claim");
    check(r,optimization::check_program_result(result,*r.program,Assurance::numerical).empty(),"canonical result check failed");
    check(r,r.attempt && r.attempt->stamp.attempt()==1 && r.attempt->state==SolveAttemptState::returned_result && r.attempt->stamp.program().identity()==f.input.identity,"authoritative current attempt mismatch");
    const auto prefix=result.raw_diagnostics.substr(0,result.raw_diagnostics.find("\nnative.log:"));
    check(r,prefix.find("\nnative_run=true")!=std::string::npos,"native run not observed");
    check(r,prefix.find("\nmodel.reused=false")!=std::string::npos,"fresh workspace not observed");
    if (result.primal) {
        const auto evaluation=optimization::evaluate_primal(*r.program,*result.primal,{1e-8,1e-8},{{"html01.canonical-cross-check"},"1"});
        if (const auto* value=std::get_if<optimization::PrimalEvaluation>(&evaluation)) r.objective=value->objective;
    }
    if (f.expected!=MathematicalOutcome::optimal) return;
    check(r,result.primal && result.primal->size()==f.input.objective.size(),"missing or malformed optimal witness");
    if (!result.primal || result.primal->size()!=f.input.objective.size()) return;
    const auto& x=*result.primal;
    double cost=f.input.offset;
    for (std::size_t i=0;i<x.size();++i) {
        cost+=f.input.objective[i]*x[i];
        check(r,close(x[i],(*f.point)[i]),"coordinate differs from unique literal minimizer");
        const auto bound=f.input.variables[i];
        check(r,(!bound.lower || x[i]>=*bound.lower || close(x[i],*bound.lower)) &&
            (!bound.upper || x[i]<=*bound.upper || close(x[i],*bound.upper)),"independent variable violation");
    }
    check(r,close(cost,*f.objective),"independent literal objective mismatch");
    check(r,r.objective && close(*r.objective,cost),"canonical objective cross-check mismatch");
    const auto& a=f.input.constraints;
    for (std::size_t i=0;i<a.rows;++i) {
        double activity=0;
        for (std::size_t j=a.row_offsets[i];j<a.row_offsets[i+1];++j) activity+=a.values[j]*x[a.column_indices[j]];
        const auto bound=f.input.rows[i];
        check(r,(!bound.lower || activity>=*bound.lower || close(activity,*bound.lower)) &&
            (!bound.upper || activity<=*bound.upper || close(activity,*bound.upper)),"independent row violation");
    }
    check(r,result.residuals.primal.has_value(),"primal residuals unavailable");
    if (result.residuals.primal) {
        const auto& p=*result.residuals.primal;
        check(r,p.context.subject==f.input.identity && passes(p.rows,p.context) && passes(p.variables,p.context),"primal residual check failed");
    }
    check(r,result.residuals.dual.has_value(),"dual residuals unavailable");
    if (result.residuals.dual) {
        const auto& d=*result.residuals.dual;
        check(r,d.context.subject==f.input.identity && d.stationarity && d.signs && passes(*d.stationarity,d.context) && passes(*d.signs,d.context),"stationarity/sign residual check failed");
    }
}
const char* outcome_name(MathematicalOutcome value) {
    switch(value) {
    case MathematicalOutcome::optimal:return "optimal";
    case MathematicalOutcome::infeasible:return "infeasible";
    case MathematicalOutcome::unbounded:return "unbounded";
    case MathematicalOutcome::infimum_not_attained:return "infimum_not_attained";
    case MathematicalOutcome::undetermined:return "undetermined";
    }
    throw std::logic_error("unknown outcome");
}
const char* termination_name(Termination value) {
    switch(value) {
    case Termination::completed:return "completed";
    case Termination::cancelled:return "cancelled";
    case Termination::resource_limit:return "resource_limit";
    case Termination::numerical_failure:return "numerical_failure";
    }
    throw std::logic_error("unknown termination");
}
std::string identity_json(const ProgramIdentity& id) { return "{\"problem\":"+json_string(id.problem.value)+",\"program\":"+json_string(id.program.value)+"}"; }
template<class Range, class F> std::string array(const Range& values,F f) {
    std::string out="["; bool first=true;
    for (const auto& value:values) { if (!first) out+=','; first=false; out+=f(value); }
    return out+"]";
}
std::string numbers(const Vector& values) { return array(values,[](double x){return json_number(x);}); }
std::string optional_number(const std::optional<double>& value) { return value ? json_number(*value) : "null"; }
std::string measure(const ResidualMeasure& value) { return "{\"violation\":"+json_number(value.violation)+",\"scale\":"+json_number(value.scale)+"}"; }
std::string context(const ResidualContext& c) { return "{\"subject\":"+identity_json(c.subject)+",\"verifier\":{\"id\":"+json_string(c.verifier.id.value)+",\"version\":"+json_string(c.verifier.version)+"},\"absolute_tolerance\":"+json_number(c.absolute_tolerance)+",\"relative_tolerance\":"+json_number(c.relative_tolerance)+"}"; }
std::string primal_json(const std::optional<PrimalResiduals>& p) {
    return p ? "{\"context\":"+context(p->context)+",\"rows\":"+measure(p->rows)+",\"variables\":"+measure(p->variables)+"}" : "null";
}
std::string dual_json(const std::optional<DualResiduals>& d) {
    if (!d) return "null";
    const auto optional=[](const std::optional<ResidualMeasure>& m){return m ? measure(*m) : "null";};
    return "{\"context\":"+context(d->context)+",\"stationarity\":"+optional(d->stationarity)+",\"signs\":"+optional(d->signs)+",\"complementarity\":"+optional(d->complementarity)+"}";
}
}

std::int64_t Interval::nanoseconds() const { return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::duration(end-start)).count(); }

const std::vector<Fixture>& catalogue() {
    static const std::vector<Fixture> values{
        {"offset-triangle",{{{"html01-literals"},{"offset-triangle"}},{-1,-2},7,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}},MathematicalOutcome::optimal,Vector{0,1},5,"x+2y <= 2(x+y) <= 2; value5 attained at(0,1)."},
        {"scalar-positive",{{{"html01-literals"},{"scalar-positive"}},{3},2,{0,1,{0},{},{}},{{-1,4}},{}},MathematicalOutcome::optimal,Vector{-1},-1,"Positive slope selects lower endpoint-1."},
        {"scalar-negative",{{{"html01-literals"},{"scalar-negative"}},{-2},2,{0,1,{0},{},{}},{{-1,4}},{}},MathematicalOutcome::optimal,Vector{4},-6,"Negative slope selects upper endpoint4."},
        {"contradictory-rows",{{{"html01-literals"},{"contradictory-rows"}},{0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{{},0},{1,{}}}},MathematicalOutcome::infeasible,{},{},"x<=0 and x>=1 contradict."},
        {"free-unbounded",{{{"html01-literals"},{"free-unbounded"}},{-1},0,{0,1,{0},{},{}},{{{},{}}},{}},MathematicalOutcome::unbounded,{},{},"-x tends to minus infinity as x grows."}
    };
    return values;
}

TrialRecord run_trial(const Fixture& f,std::stop_token cancellation) {
    using namespace registry;
    TrialRecord record;
    record.timings[5].available=true; record.timings[5].start=now();
    try {
        record.program=timed(record.timings[0],[&]{ const auto input=f.input; return accepted<LinearProgram>(optimization::make_linear_program(input)); });
        const auto plan=timed(record.timings[1],[&]{
            Registry<LPPort> registry;
            auto entry=accepted<Registration<LPPort>>(adapters::lp::make_highs_registration());
            record.actual_version=entry.identity.version;
            if (auto rejected=registry.add(std::move(entry))) throw Rejected(rejected->diagnostics);
            Requirements requirements; requirements.output.representation={"csl.program-result.v1"};
            return accepted<PreparedPipeline<LPPort>>(prepare_pipeline(select(registry,{{"csl.lp.highs"},{}},*record.program,requirements)));
        });
        record.actual_version=plan.provenance()[0].actual->version;
        auto workers=timed(record.timings[2],[&]{return plan.create();});
        auto& worker=std::get<0>(workers);
        ExecutionContext execution{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),cancellation,{}, {1e-8,1e-8},"html01"};
        auto outcome=timed(record.timings[3],[&]{ auto result=worker->run(execution); record.observation=observe(result); return result; });
        record.attempt=worker->last_attempt();
        if (auto* result=std::get_if<ProgramResult>(&outcome)) { record.result=std::move(*result); record.harness_status="returned"; }
        else { record.harness_status="unsupported"; record.diagnostics=std::get<Unsupported>(outcome).diagnostics; record.error=diagnostic_text(record.diagnostics); }
        timed(record.timings[4],[&]{verify(f,record);return true;});
        record.timings[5].end=now(); // Before workspace/plan destruction.
    } catch (const Rejected& error) {
        record.diagnostics=error.diagnostics;
        record.harness_status=std::any_of(record.diagnostics.begin(),record.diagnostics.end(),[](const auto& d){return d.code==DiagnosticCode::unsupported;})?"unsupported":"exception";
        record.error=error.what();record.errors.push_back(record.error);record.timings[5].end=now();
    } catch (const std::exception& error) {
        record.error=error.what(); record.errors.push_back(record.error); record.timings[5].end=now();
    } catch (...) {
        record.error="non-standard exception"; record.errors.push_back(record.error); record.timings[5].end=now();
    }
    return record;
}

std::string json_string(const std::string& text) {
    constexpr char hex[]="0123456789abcdef";
    std::string out="\"";
    for (unsigned char c:text) {
        switch(c) {
        case '"':out+="\\\"";break; case '\\':out+="\\\\";break;
        case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;
        default:if(c<32) {out+="\\u00";out+=hex[c>>4];out+=hex[c&15];} else out+=static_cast<char>(c);
        }
    }
    return out+'"';
}
std::string json_number(double value) {
    if (!std::isfinite(value)) throw std::invalid_argument("cannot serialize nonfinite binary64");
    std::ostringstream out;out.imbue(std::locale::classic());out<<std::setprecision(std::numeric_limits<double>::max_digits10)<<value;
    auto text=out.str(); if (text.find_first_of(".eE")==std::string::npos) text+=".0";return text;
}
std::string catalogue_json() {
    return array(catalogue(),[](const Fixture& f){
        const auto& a=f.input.constraints;
        const auto bounds=[](const auto& values){return array(values,[](const csl::Interval& x){return "["+optional_number(x.lower)+","+optional_number(x.upper)+"]";});};
        const auto indices=[](const auto& values){return array(values,[](auto x){return std::to_string(x);});};
        return "{\"case_id\":"+json_string(f.id)+",\"identity\":"+identity_json(f.input.identity)+",\"input\":{\"linear\":"+numbers(f.input.objective)+",\"offset\":"+json_number(f.input.offset)+",\"constraints\":{\"rows\":"+std::to_string(a.rows)+",\"cols\":"+std::to_string(a.cols)+",\"starts\":"+indices(a.row_offsets)+",\"indices\":"+indices(a.column_indices)+",\"values\":"+numbers(a.values)+"},\"variables\":"+bounds(f.input.variables)+",\"rows\":"+bounds(f.input.rows)+"},\"reference\":{\"outcome\":"+json_string(outcome_name(f.expected))+",\"point\":"+(f.point?numbers(*f.point):"null")+",\"objective\":"+optional_number(f.objective)+",\"derivation\":"+json_string(f.derivation)+"},\"assumptions\":[\"continuous variables\",\"minimization\",\"binary64 numerical output; outcome support unestablished\"]}";
    });
}
std::string trial_json(const Fixture& f,const TrialRecord& r,std::size_t round,std::size_t sequence,const std::string& purpose) {
    std::string result="null";
    if (r.result) {
        const auto& value=*r.result;
        result="{\"termination\":"+json_string(termination_name(value.termination))+",\"outcome\":"+json_string(outcome_name(value.outcome.value))+",\"support\":{\"kind\":"+json_string(std::holds_alternative<Unestablished>(value.outcome.support)?"unestablished":"unsupported-projection")+"},\"primal\":"+(value.primal?numbers(*value.primal):"null")+",\"original_objective\":"+optional_number(r.objective)+",\"objective_unavailable_reason\":"+(r.objective?"null":json_string("no finite evaluated objective"))+",\"bounds\":{\"lower\":null,\"upper\":null},\"family\":{\"available\":false,\"reason\":\"point only\"},\"primal_residuals\":"+primal_json(value.residuals.primal)+",\"dual_residuals\":"+dual_json(value.residuals.dual)+",\"raw_diagnostics\":"+json_string(value.raw_diagnostics)+"}";
    }
    std::string timings="{";
    for (std::size_t i=0;i<phases.size();++i) {
        if(i) timings+=',';
        timings+=json_string(phases[i])+":";
        const auto& t=r.timings[i];
        timings+=t.available?"{\"available\":true,\"start_tick\":"+json_string(std::to_string(t.start))+",\"end_tick\":"+json_string(std::to_string(t.end))+",\"duration_ns\":"+std::to_string(t.nanoseconds())+",\"unit\":\"ns\",\"scope\":"+json_string(phases[i])+"}":"{\"available\":false,\"reason\":\"phase not reached\"}";
    }
    timings+='}';
    const auto actual=r.actual_version.empty()?"null":"{\"id\":\"csl.lp.highs\",\"version\":"+json_string(r.actual_version)+"}";
    std::string attempt="null";
    if(r.attempt) attempt="{\"number\":"+std::to_string(r.attempt->stamp.attempt())+",\"state\":"+json_string(r.attempt->state==SolveAttemptState::returned_result?"returned_result":r.attempt->state==SolveAttemptState::unsupported?"unsupported":r.attempt->state==SolveAttemptState::exception?"exception":"running")+",\"workspace_reuse\":false}";
    const auto diagnostics=array(r.diagnostics,[](const auto& d){return "{\"code\":"+std::to_string(static_cast<int>(d.code))+",\"field\":"+json_string(d.field)+",\"explanation\":"+json_string(d.explanation)+"}";});
    return "{\"case_id\":"+json_string(f.id)+",\"round\":"+std::to_string(round)+",\"sequence\":"+std::to_string(sequence)+",\"purpose\":"+json_string(purpose)+",\"identity\":"+identity_json(f.input.identity)+",\"registry\":{\"requested\":\"csl.lp.highs\",\"actual\":"+actual+"},\"attempt\":"+attempt+",\"timings\":"+timings+",\"observation_token\":"+json_string(std::to_string(r.observation))+",\"harness\":{\"status\":"+json_string(r.harness_status)+",\"error\":"+(r.error.empty()?"null":json_string(r.error))+",\"diagnostics\":"+diagnostics+"},\"result\":"+result+",\"validation\":{\"passed\":"+(r.passed()?"true":"false")+",\"errors\":"+array(r.errors,[](const auto& x){return json_string(x);})+"}}";
}
std::string build_info_json() {
#ifdef NDEBUG
    constexpr bool ndebug=true;
#else
    constexpr bool ndebug=false;
#endif
    return "{\"source_commit\":"+json_string(build::source_commit)+",\"compiler\":"+json_string(build::compiler)+",\"compiler_version\":"+json_string(build::compiler_version)+",\"generator\":"+json_string(build::generator)+",\"architecture\":"+json_string(build::architecture)+",\"configuration\":"+json_string(CSL_REPORT_CONFIG)+",\"cxx_standard\":20,\"ndebug\":"+(ndebug?"true":"false")+",\"configured_flags\":"+json_string(build::configured_flags)+",\"release_flags\":"+json_string(build::release_flags)+"}";
}
} // namespace csl::reporting
