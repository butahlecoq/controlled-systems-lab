#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/optimization/linear_program.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

using namespace csl;
namespace {
using Clock = std::chrono::steady_clock;
using namespace csl::registry;
std::shared_ptr<const ResourcePolicy> report_resources() {
    return std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
}
ExecutionContext report_context() { return {report_resources(),{}, {},{1e-8,1e-8},"geo04-report"}; }

template<class T, class... U> T take(std::variant<T,U...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("operation returned diagnostics");
    return std::get<T>(std::move(value));
}
struct Trial {
    std::string scenario;
    std::size_t repetition{};
    std::string status{"failed"}, detail;
    std::uint64_t intersect_ns{}, prepare_ns{}, workspace_ns{}, run_ns{}, lp_workspace_ns{}, reduce_ns{}, total_ns{};
    std::size_t lp_calls{}, lp_results{}, lp_optimal{}, lp_bounds{}, lp_supported_bounds{};
    std::size_t inequalities{}, equalities{}, vertices{}, oracle_checks{};
    std::string reduction_status{"not_applicable"};
    std::string vertices_json{"[]"};
    bool oracle_passed{};
};
struct Timer {
    Clock::time_point start{Clock::now()};
    std::uint64_t elapsed() const {
        return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
    }
};
numeric::MatrixView matrix(std::size_t rows, std::size_t cols, Vector values) {
    return take(numeric::snapshot(Matrix{rows,cols,std::move(values)}));
}
numeric::VectorView vector(Vector values) { return take(numeric::snapshot_vector(values)); }
sets::SetData hset(std::string id, Matrix a, Vector b, Matrix e={0,2,{}}, Vector f={}) {
    return take(sets::make_h({{std::move(id)},2,{"x","y"}},
        {matrix(a.rows,a.cols,std::move(a.values)),vector(std::move(b)),
         matrix(e.rows,e.cols,std::move(e.values)),vector(std::move(f))}));
}
sets::SetData intersect(const sets::SetData& a, const sets::SetData& b, const char* id, Trial& t) {
    Timer timer;
    auto result=geometry::polyhedral::intersect_h(a,b,{{id}});
    t.intersect_ns=timer.elapsed();
    return take(std::move(result));
}
sets::VRepresentation convert(const sets::SetData& input, Trial& t) {
    auto lp=take(adapters::lp::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    Registry<ConversionPort> conversions;
    if (conversions.add(std::move(converter))) throw std::runtime_error("converter registration failed");
    ConversionRequest request{{{"geo04-report"},{t.scenario+"-"+std::to_string(t.repetition)},{"contract-fixture"}},
        input.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    Requirements required;
    required.output={{"csl.polyhedron.v"},Assurance::numerical,SetRelation::equivalent,{},{}};
    Timer prepare;
    auto prepared=prepare_pipeline(select(conversions,{{"csl.conversion.qhull"},{}},request,required));
    t.prepare_ns=prepare.elapsed();
    auto* pipeline=std::get_if<PreparedPipeline<ConversionPort>>(&prepared);
    if (!pipeline) throw std::runtime_error("Qhull conversion provider unavailable");
    Timer create;
    auto [workspace]=pipeline->create();
    t.workspace_ns=create.elapsed();
    Timer run;
    auto result=workspace->run(report_context());
    t.run_ns=run.elapsed();
    auto* operation=std::get_if<OperationResult>(&result);
    if (!operation) throw std::runtime_error("Qhull conversion did not complete");
    auto data=take(sets::from_handle(operation->output));
    const auto representation=data.representation();
    auto* rep=std::get_if<sets::VRepresentation>(&representation);
    if (!rep) throw std::runtime_error("Qhull conversion returned non-V data");
    std::ostringstream vertices;
    vertices<<std::setprecision(17)<<'[';
    for (std::size_t i=0;i<rep->vertices.rows();++i) {
        if (i) vertices<<',';
        vertices<<'['<<rep->vertices(i,0)<<','<<rep->vertices(i,1)<<']';
    }
    vertices<<']';
    t.vertices_json=vertices.str();
    return *rep;
}
bool near(double a,double b) { return std::abs(a-b)<=1e-7; }
bool exact_vertices(const sets::VRepresentation& v,
        const std::vector<std::array<double,2>>& expected, Trial& t) {
    t.vertices=v.vertices.rows();
    if (v.rays.rows()!=0 || v.vertices.cols()!=2 || v.vertices.rows()!=expected.size()) return false;
    std::vector<bool> seen(expected.size());
    for (std::size_t i=0;i<v.vertices.rows();++i) {
        std::size_t count=0,index=0;
        for (std::size_t j=0;j<expected.size();++j)
            if (near(v.vertices(i,0),expected[j][0])&&near(v.vertices(i,1),expected[j][1])) { ++count; index=j; }
        ++t.oracle_checks;
        if (count!=1 || seen[index]) return false;
        seen[index]=true;
        for (std::size_t j=0;j<i;++j) {
            ++t.oracle_checks;
            if (near(v.vertices(i,0),v.vertices(j,0))&&near(v.vertices(i,1),v.vertices(j,1))) return false;
        }
    }
    return std::all_of(seen.begin(),seen.end(),[](bool found){return found;});
}
void run_crossing(Trial& t) {
    auto a=hset("cross-left",{4,2,{1,0,-1,0,0,1,0,-1}},{1,1,1,1});
    auto b=hset("cross-right",{4,2,{1,1,1,-1,-1,1,-1,-1}},{1.5,1.5,1.5,1.5});
    auto result=intersect(a,b,"cross-overlap",t);
    const auto representation=result.representation();
    const auto& h=std::get<sets::HRepresentation>(representation);
    t.inequalities=h.inequalities.rows(); t.equalities=h.equalities.rows();
    auto v=convert(result,t);
    const std::vector<std::array<double,2>> expected{{{1,.5},{1,-.5},{-1,.5},{-1,-.5},{.5,1},{-.5,1},{.5,-1},{-.5,-1}}};
    t.oracle_passed=t.inequalities==8&&t.equalities==0&&exact_vertices(v,expected,t);
    t.status=t.oracle_passed?"passed":"oracle_failed";
}
void run_empty(Trial& t) {
    auto a=hset("empty-left",{1,2,{1,0}},{0});
    auto b=hset("empty-right",{1,2,{-1,0}},{-1});
    auto result=intersect(a,b,"empty-overlap",t);
    const auto representation=result.representation();
    const auto& h=std::get<sets::HRepresentation>(representation);
    t.inequalities=h.inequalities.rows(); t.equalities=h.equalities.rows();
    auto v=convert(result,t);
    t.vertices=v.vertices.rows();
    t.oracle_checks=1;
    t.oracle_passed=t.inequalities==2&&t.vertices==0&&v.rays.rows()==0;
    t.status=t.oracle_passed?"passed":"oracle_failed";
}
void run_affine(Trial& t) {
    auto band=hset("affine-band",{2,2,{1,0,-1,0}},{2,0},{1,2,{0,1}},{1});
    auto result=intersect(band,band,"affine-copy",t);
    const auto representation=result.representation();
    const auto& h=std::get<sets::HRepresentation>(representation);
    t.inequalities=h.inequalities.rows(); t.equalities=h.equalities.rows();
    bool eq=h.equalities.rows()==2&&h.equalities(0,0)==0&&h.equalities(0,1)==1&&h.equality_values[0]==1&&
        h.equalities(1,0)==0&&h.equalities(1,1)==1&&h.equality_values[1]==1;
    ++t.oracle_checks;
    auto v=convert(result,t);
    const std::vector<std::array<double,2>> expected{{{0,1},{2,1}}};
    t.oracle_passed=eq&&exact_vertices(v,expected,t);
    t.status=t.oracle_passed?"passed":"oracle_failed";
}
struct LpEvidence { std::size_t calls{}, results{}, optimal{}, bounds{}, supported_bounds{}; };
class ObservedWorkspace final : public LPWorkspace {
public:
    ObservedWorkspace(std::unique_ptr<LPWorkspace> delegate, LpEvidence& evidence)
        : delegate_(std::move(delegate)), evidence_(evidence) {}
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext& context) override {
        ++evidence_.calls;
        auto result=delegate_->solve(program,context);
        if (const auto* solved=std::get_if<ProgramResult>(&result)) {
            ++evidence_.results;
            if (solved->outcome.value==MathematicalOutcome::optimal) ++evidence_.optimal;
            if (solved->objective.lower) {
                ++evidence_.bounds;
                if (std::holds_alternative<NumericalCheck>(solved->objective.lower->evidence.support))
                    ++evidence_.supported_bounds;
            }
        }
        return result;
    }
private:
    std::unique_ptr<LPWorkspace> delegate_;
    LpEvidence& evidence_;
};
std::unique_ptr<LPWorkspace> highs_workspace(LpEvidence& evidence) {
    auto registration=take(adapters::lp::make_highs_registration());
    auto seed=take(optimization::make_linear_program({{{"geo04-report"},{"factory-seed"}}, Vector(2,0.0),0,
        {0,2,{0},{},{}},std::vector<Interval>(2),{}}));
    return std::make_unique<ObservedWorkspace>(registration.factory(seed),evidence);
}
void run_essential(Trial& t) {
    auto input=hset("essential-rows",{3,2,{1,0,-1,0,0,1}},{1,0,0},{1,2,{0,1}},{0});
    LpEvidence evidence;
    Timer lp_create;
    auto lp=highs_workspace(evidence);
    t.lp_workspace_ns=lp_create.elapsed();
    Timer timer;
    auto result=geometry::polyhedral::remove_redundant_halfspaces(input,{"essential-output"},*lp,report_context());
    t.reduce_ns=timer.elapsed();
    auto* reduction=std::get_if<geometry::polyhedral::HalfspaceReduction>(&result);
    if (!reduction) throw std::runtime_error("halfspace reducer returned diagnostics");
    t.lp_calls=reduction->lp_calls;
    t.lp_results=evidence.results; t.lp_optimal=evidence.optimal;
    t.lp_bounds=evidence.bounds; t.lp_supported_bounds=evidence.supported_bounds;
    t.reduction_status=reduction->status==geometry::polyhedral::HalfspaceReductionStatus::incomplete?"incomplete":"complete";
    const auto representation=reduction->set.representation();
    const auto& h=std::get<sets::HRepresentation>(representation);
    t.inequalities=h.inequalities.rows(); t.equalities=h.equalities.rows();
    // The current HiGHS adapter publishes no supported objective bounds. Keep
    // every row and mark incomplete; this fixture is not a benchmark LP backend.
    t.oracle_checks=4;
    t.oracle_passed=t.reduction_status=="incomplete"&&t.lp_calls==3&&evidence.calls==3&&
        evidence.supported_bounds==0&&evidence.bounds==0&&t.inequalities==3&&
        t.equalities==1&&reduction->removed_inequalities.empty()&&reduction->retained_inequalities==std::vector<std::size_t>{0,1,2};
    t.status=t.oracle_passed?"passed":"oracle_failed";
}
const std::array<const char*,4> scenarios{"crossing_octagon","empty_intersection","affine_equality","essential_rows_highs"};
std::string csv(std::string value) {
    std::string escaped="\"";
    for (const char c : value) {
        if (c=='\"') escaped+="\"\"";
        else if (c=='\r'||c=='\n') escaped+=' ';
        else escaped+=c;
    }
    return escaped+'\"';
}
void emit(const Trial& t) {
    std::cout<<t.scenario<<','<<t.repetition<<','<<t.status<<','<<csv(t.detail)<<','<<t.intersect_ns<<','
        <<t.prepare_ns<<','<<t.workspace_ns<<','<<t.run_ns<<','<<t.lp_workspace_ns<<','<<t.reduce_ns<<','<<t.total_ns<<','<<t.lp_calls<<','
        <<t.lp_results<<','<<t.lp_optimal<<','<<t.lp_bounds<<','<<t.lp_supported_bounds<<','
        <<t.reduction_status<<','<<t.inequalities<<','<<t.equalities<<','<<t.vertices<<','<<t.oracle_checks<<','
        <<csv(t.vertices_json)<<','
        <<(t.oracle_passed?"true":"false")<<'\n';
}
std::size_t count_arg(const char* text) {
    const auto n=std::stoull(text);
    if (!n||n>10000) throw std::runtime_error("counts must be in [1,10000]");
    return static_cast<std::size_t>(n);
}
Trial execute(const char* scenario,std::size_t repetition) {
    Trial t; t.scenario=scenario; t.repetition=repetition;
    Timer total;
    try {
        const std::string id=scenario;
        if (id=="crossing_octagon") run_crossing(t);
        else if (id=="empty_intersection") run_empty(t);
        else if (id=="affine_equality") run_affine(t);
        else run_essential(t);
    } catch (const std::exception& error) { t.status="failed"; t.detail=error.what(); }
    t.total_ns=total.elapsed();
    return t;
}
}
int main(int argc,char** argv) {
    try {
        std::size_t repetitions=7,warmups=1;
        for (int i=1;i<argc;++i) {
            const std::string arg=argv[i];
            if (arg=="--repetitions"&&i+1<argc) repetitions=count_arg(argv[++i]);
            else if (arg=="--warmups"&&i+1<argc) warmups=count_arg(argv[++i]);
            else if (arg=="--smoke") { repetitions=1; warmups=1; }
            else throw std::runtime_error("usage: csl_geo04_intersection_report [--repetitions N --warmups N | --smoke]");
        }
        for (std::size_t r=0;r<warmups;++r) for (const auto* scenario:scenarios) (void)execute(scenario,r);
        std::cout<<"scenario,repetition,status,detail,intersection_ns,prepare_ns,workspace_ns,conversion_run_ns,lp_workspace_ns,reduction_ns,total_ns,lp_calls,lp_results,lp_optimal,lp_bounds,lp_supported_bounds,reduction_status,inequalities,equalities,vertices,oracle_checks,vertices_json,oracle_passed\n";
        for (std::size_t r=0;r<repetitions;++r) for (std::size_t j=0;j<scenarios.size();++j) {
            const auto index=(r%2)?scenarios.size()-1-j:j;
            emit(execute(scenarios[index],r));
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr<<"geo04_report_error="<<error.what()<<'\n'; return 2;
    }
}
