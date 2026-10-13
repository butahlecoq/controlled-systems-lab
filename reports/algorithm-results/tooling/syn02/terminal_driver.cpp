#include <csl/synthesis/terminal_minimizers.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/optimization/objectives.hpp>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <variant>
#include <vector>

using namespace csl;
namespace {
using Clock = std::chrono::steady_clock;
struct Fixture { const char* id; TerminalObjective objective; MathematicalOutcome expected; const char* expected_termination; bool relation; double value; const char* provider; };
std::vector<Fixture> fixtures() {
    return {
        {"linear-face", LinearTerminal{{1,0},7}, MathematicalOutcome::optimal, "completed", true, 7, "csl.lp.highs"},
        {"constant-linear", LinearTerminal{{0,0},3}, MathematicalOutcome::optimal, "completed", true, 3, "csl.lp.highs"},
        {"psd-null-direction", QuadraticTerminal{{2,2,{2,0,0,0}},{0,0},0}, MathematicalOutcome::optimal, "completed", true, 0, "csl.convex.highs"},
        {"rectangular-residual", ResidualNormTerminal{{1,2,{1,0}},{0}}, MathematicalOutcome::optimal, "completed", true, 0, "csl.convex.highs"},
        {"shifted-residual-degenerate", ResidualNormTerminal{{1,2,{1,0}},{0.5}}, MathematicalOutcome::undetermined, "numerical_failure", false, 0, "csl.convex.highs"}
    };
}
template<class T, class... U> T take(std::variant<T,U...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("fixture construction rejected");
    return std::get<T>(std::move(value));
}
numeric::MatrixView matrix(Matrix value) { return take(numeric::snapshot(std::move(value))); }
numeric::VectorView vector(Vector value) { return take(numeric::snapshot_vector(std::move(value))); }
problem::ResolvedProblem resolved(TerminalObjective objective) {
    Problem p{{"syn02-report-problem"},
      std::make_shared<const SystemModel>(SystemModel{{{2,1,0},TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}},{2,1,{0,0}},{2,0,{}},{0,0}}},{}}),
      {0,1},KnownInitial{{0,0}},ContinuousDomain{{Singleton{{0}}}},
      {UniversalSet{2},UniversalSet{2}},{},{},InformationPattern::nominal_open_loop,std::move(objective)};
    return take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
sets::SetData unit_box() {
    return take(sets::make_h({{"syn02-report-unit-box"},2,{"x","y"}},
       {matrix({4,2,{1,0,-1,0,0,1,0,-1}}),vector({1,0,1,0}),matrix({0,2,{}}),vector({})}));
}
registry::PreparedProvider<registry::LPPort> lp_provider() {
    auto registration=take(adapters::lp::make_highs_registration());
    registry::Registry<registry::LPPort> registry; auto id=registration.identity.id;
    if(registry.add(std::move(registration))) throw std::runtime_error("LP registration failed");
    registry::Requirements requirements;requirements.output.representation={"csl.program-result.v1"};
    return take(registry::prepare_provider(registry::select_provider(registry,registry::Method{id,{}},requirements)));
}
registry::PreparedProvider<registry::ConvexPort> convex_provider() {
    auto registration=take(adapters::convex::make_highs_registration());
    registry::Registry<registry::ConvexPort> registry; auto id=registration.identity.id;
    if(registry.add(std::move(registration))) throw std::runtime_error("convex registration failed");
    registry::Requirements requirements;requirements.output.representation={"csl.program-result.v1"};
    return take(registry::prepare_provider(registry::select_provider(registry,registry::Method{id,{}},requirements)));
}
std::string quoted(const std::string& text) {
    std::ostringstream out;out<<'"';
    for(unsigned char c:text){if(c=='"'||c=='\\')out<<'\\'<<static_cast<char>(c);else if(c=='\n')out<<"\\n";else if(c=='\r')out<<"\\r";else if(c<0x20)out<<" ";else out<<static_cast<char>(c);}out<<'"';return out.str();
}
const char* outcome(MathematicalOutcome v) {
    switch(v){case MathematicalOutcome::optimal:return "optimal";case MathematicalOutcome::infeasible:return "infeasible";case MathematicalOutcome::unbounded:return "unbounded";case MathematicalOutcome::infimum_not_attained:return "infimum_not_attained";default:return "undetermined";}
}
const char* termination(Termination v) {
    switch(v){case Termination::completed:return "completed";case Termination::cancelled:return "cancelled";case Termination::resource_limit:return "resource_limit";case Termination::operation_rejected:return "operation_rejected";case Termination::contract_rejected:return "contract_rejected";case Termination::numerical_failure:return "numerical_failure";default:return "unknown";}
}
const char* support(const EvidenceSupport& v) {
    if(std::holds_alternative<Unestablished>(v))return "unestablished";
    if(std::holds_alternative<SymbolicArgument>(v))return "symbolic_argument";
    if(std::holds_alternative<NumericalCheck>(v))return "numerical_check";
    return "other";
}
void vector_json(std::ostream& o, numeric::VectorView v) { o<<'[';for(std::size_t i=0;i<v.size();++i){if(i)o<<',';o<<std::setprecision(17)<<v[i];}o<<']'; }
void matrix_json(std::ostream& o, numeric::MatrixView m) { o<<'[';for(std::size_t i=0;i<m.rows();++i){if(i)o<<',';o<<'[';for(std::size_t j=0;j<m.cols();++j){if(j)o<<',';o<<std::setprecision(17)<<m(i,j);}o<<']';}o<<']'; }
struct Trial { std::string status{"failed"}, outcome{"undetermined"}, termination{"unknown"}, provider, diagnostic, raw_diagnostics, relation_support{"unestablished"}, optimum_support{"unestablished"}, lower_support{"unavailable"}, upper_support{"unavailable"}, program_outcome_support{"unavailable"}, program_lower_support{"unavailable"}, program_upper_support{"unavailable"}, characterization; std::vector<std::string> assumptions; bool relation{}, optimization{}, optimum{}, oracle{}; std::optional<double> primal_value, lower, upper; std::uint64_t prepare_ns{}, solve_ns{}, oracle_ns{}, execute_ns{}; std::optional<sets::SetData> result; };
Trial execute(const Fixture& fixture) {
    Trial t; const auto begin=Clock::now();
    try {
      auto problem=resolved(fixture.objective);
      FamilyRequest request;request.objective=problem.identity();request.profile="nominal-polyhedral";request.representation={"polyhedral-h"};
      auto box=unit_box();
      auto lp=lp_provider();auto convex=convex_provider();
      synthesis::TerminalOptimizer optimizer(std::move(lp),std::move(convex));
      ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
      t.prepare_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin).count();
      const auto solve_begin=Clock::now();
      auto result=optimizer.solve(problem,request,{problem.identity(),std::move(box)},context);
      t.solve_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-solve_begin).count();
      const auto oracle_begin=Clock::now();
      t.outcome=outcome(result.outcome);t.termination=termination(result.termination);
      t.relation=result.relation.has_value();t.optimization=result.optimization.has_value();t.optimum=result.optimum.has_value();
      if(result.provider)t.provider=result.provider->actual->id.value;
      if(!result.diagnostics.empty())t.diagnostic=result.diagnostics.front().explanation;
      t.relation_support=support(result.construction.support);
      t.characterization=result.construction.characterization;t.assumptions=result.construction.assumptions;
      if(result.optimization){t.raw_diagnostics=result.optimization->raw_diagnostics;t.program_outcome_support=support(result.optimization->outcome.support);if(result.optimization->primal){auto value=optimization::evaluate(problem.objective(),*result.optimization->primal);if(std::holds_alternative<double>(value))t.primal_value=std::get<double>(value);}if(result.optimization->objective.lower){t.lower=result.optimization->objective.lower->value;t.program_lower_support=support(result.optimization->objective.lower->evidence.support);}if(result.optimization->objective.upper){t.upper=result.optimization->objective.upper->value;t.program_upper_support=support(result.optimization->objective.upper->evidence.support);}}
      if(result.optimum)t.optimum_support=support(result.optimum->optimum.support);
      if(result.optimum&&result.optimum->bounds.lower)t.lower_support=support(result.optimum->bounds.lower->evidence.support);
      if(result.optimum&&result.optimum->bounds.upper)t.upper_support=support(result.optimum->bounds.upper->evidence.support);
      t.oracle=(t.outcome==outcome(fixture.expected)&&t.relation==fixture.relation&&t.termination==fixture.expected_termination&&t.optimization&&t.optimum&&t.provider==fixture.provider);
      if(fixture.expected==MathematicalOutcome::undetermined)t.oracle=(t.outcome=="undetermined"&&!t.relation&&t.optimization&&t.optimum&&t.termination==fixture.expected_termination&&t.provider==fixture.provider&&!t.raw_diagnostics.empty());
      if(fixture.expected==MathematicalOutcome::optimal&&t.primal_value)t.oracle=t.oracle&&std::abs(*t.primal_value-fixture.value)<=1e-7;
      if(result.relation){t.result=*result.relation;const auto rep=t.result->representation();if(!std::holds_alternative<sets::HRepresentation>(rep))t.oracle=false;}
      t.oracle_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-oracle_begin).count();
      t.status=t.oracle?"passed":"oracle_failed";
    } catch(const std::exception& e) {t.diagnostic=e.what();t.status="failed";}
    t.execute_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-begin).count();return t;
}
void emit(const Fixture& f,std::size_t repetition,bool warmup,const Trial& t) {
    std::cout<<"{\"schema\":\"csl.syn02-terminal-trial/1\",\"scenario\":"<<quoted(f.id)<<",\"repetition\":"<<repetition<<",\"warmup\":"<<(warmup?"true":"false")<<",\"status\":"<<quoted(t.status)<<",\"expected_outcome\":"<<quoted(outcome(f.expected))<<",\"outcome\":"<<quoted(t.outcome)<<",\"termination\":"<<quoted(t.termination)<<",\"relation\":"<<(t.relation?"true":"false")<<",\"optimization_present\":"<<(t.optimization?"true":"false")<<",\"optimum_present\":"<<(t.optimum?"true":"false")<<",\"provider\":"<<quoted(t.provider)<<",\"diagnostic\":"<<quoted(t.diagnostic)<<",\"primal_value\":";
    if(t.primal_value)std::cout<<std::setprecision(17)<<*t.primal_value;else std::cout<<"null";
    std::cout<<",\"expected_termination\":"<<quoted(f.expected_termination)<<",\"expected_provider\":"<<quoted(f.provider)<<",\"relation_support\":"<<quoted(t.relation_support)<<",\"optimum_support\":"<<quoted(t.optimum_support)<<",\"program_outcome_support\":"<<quoted(t.program_outcome_support)<<",\"program_lower_bound_support\":"<<quoted(t.program_lower_support)<<",\"program_upper_bound_support\":"<<quoted(t.program_upper_support)<<",\"lower_bound_support\":"<<quoted(t.lower_support)<<",\"upper_bound_support\":"<<quoted(t.upper_support)<<",\"characterization\":"<<quoted(t.characterization)<<",\"assumptions\":[";for(std::size_t i=0;i<t.assumptions.size();++i){if(i)std::cout<<',';std::cout<<quoted(t.assumptions[i]);}std::cout<<"],\"raw_diagnostics\":"<<quoted(t.raw_diagnostics)<<",\"lower_bound\":";if(t.lower)std::cout<<std::setprecision(17)<<*t.lower;else std::cout<<"null";
    std::cout<<",\"upper_bound\":";if(t.upper)std::cout<<std::setprecision(17)<<*t.upper;else std::cout<<"null";
    std::cout<<",\"prepare_ns\":"<<t.prepare_ns<<",\"solve_ns\":"<<t.solve_ns<<",\"oracle_ns\":"<<t.oracle_ns<<",\"execute_ns\":"<<t.execute_ns<<",\"inequalities\":";
    if(t.relation){auto rep=std::get<sets::HRepresentation>(t.result->representation());matrix_json(std::cout,rep.inequalities);std::cout<<",\"upper_bounds\":";vector_json(std::cout,rep.upper_bounds);std::cout<<",\"equalities\":";matrix_json(std::cout,rep.equalities);std::cout<<",\"equality_values\":";vector_json(std::cout,rep.equality_values);}else std::cout<<"[],\"upper_bounds\":[],\"equalities\":[],\"equality_values\":[]";
    std::cout<<"}\n";
}
}
int main(int argc,char** argv) {
    if(argc!=3){std::cerr<<"usage: csl_syn02_terminal_report <repetitions> <warmups>\n";return 2;}
    const auto repetitions=static_cast<std::size_t>(std::stoul(argv[1]));const auto warmups=static_cast<std::size_t>(std::stoul(argv[2]));
    if(repetitions==0||warmups==0){std::cerr<<"repetitions and warmups must be positive\n";return 2;}
    std::cout<<"{\"schema\":\"csl.syn02-terminal-run/1\",\"source_commit\":\""<<CSL_SYN02_SOURCE_COMMIT<<"\",\"harness_commit\":\""<<CSL_SYN02_HARNESS_COMMIT<<"\"}\n";
    const auto cases=fixtures();std::size_t failed=0;
    // Each repetition alternates forward/reverse fixture order to reduce drift bias.
    for(std::size_t round=0;round<warmups+repetitions;++round){for(std::size_t pos=0;pos<cases.size();++pos){const bool reverse=(round%2)!=0;const auto index=reverse?cases.size()-1-pos:pos;auto trial=execute(cases[index]);const bool warm=round<warmups;if(!warm&&trial.status!="passed")++failed;emit(cases[index],round,warm,trial);}}
    return failed?1:0;
}
