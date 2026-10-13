#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/reachability/nominal_predecessor.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>
#include <utility>

using namespace csl;
namespace {
using Clock = std::chrono::steady_clock;
using namespace csl::registry;
std::shared_ptr<const ResourcePolicy> report_resources() {
    return std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
}
ExecutionContext report_context() {
    return {report_resources(),{}, {},{1e-8,1e-8},"geo05-report"};
}
template<class T, class... E> T take(std::variant<T,E...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("public geometry API returned diagnostics or rejection");
    return std::get<T>(std::move(value));
}
struct Trial {
    std::string purpose{"measurement"}, scenario, status{"failed"}, detail;
    std::size_t repetition{}, input_rows{}, rows{}, vertices{}, rays{};
    std::string result_kind;
    std::string result_encoding;
    std::optional<std::size_t> expected_fm_peak_rows;
    bool oracle_passed{}, work_observed{};
    bool output_observed{};
    std::optional<std::size_t> max_rows{128};
    std::uint64_t setup_ns{}, run_ns{}, verification_ns{}, end_to_end_ns{};
    std::optional<std::uint64_t> workspace_ns{0};
};
std::string json_escape(const std::string& value) {
    std::string escaped;
    for (unsigned char ch:value) {
        if (ch=='"' || ch=='\\') { escaped.push_back('\\'); escaped.push_back(static_cast<char>(ch)); }
        else if (ch=='\n') escaped+="\\n";
        else if (ch=='\r') escaped+="\\r";
        else if (ch=='\t') escaped+="\\t";
        else if (ch<0x20) escaped+=' ';
        else escaped.push_back(static_cast<char>(ch));
    }
    return escaped;
}
struct Timer {
    Clock::time_point start{Clock::now()};
    std::uint64_t elapsed() const { return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count()); }
};
sets::SetData hset(std::string id,std::size_t n,Matrix a,Vector b,Matrix e,Vector f,
        std::vector<std::string> labels={}) {
    auto av=take(numeric::snapshot(std::move(a))); auto bv=take(numeric::snapshot_vector(std::move(b)));
    auto ev=take(numeric::snapshot(std::move(e))); auto fv=take(numeric::snapshot_vector(std::move(f)));
    return take(sets::make_h({{std::move(id)},n,std::move(labels)},{std::move(av),std::move(bv),std::move(ev),std::move(fv)}));
}
sets::SetData interval(std::string id,double lo,double hi,std::string label={}) {
    return hset(std::move(id),1,{2,1,{1,-1}},{hi,-lo},{0,1,{}},{},
        label.empty()?std::vector<std::string>{}:std::vector<std::string>{std::move(label)});
}
template<class Port> PreparedProvider<Port> provider(Registration<Port> entry,std::string representation) {
    Registry<Port> registry; Method method{entry.identity.id,entry.identity.version};
    if (registry.add(std::move(entry))) throw std::runtime_error("provider registration failed");
    Requirements requirements; requirements.output.representation={std::move(representation)};
    requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
reachability::NominalPredecessorResult predecessor(const sets::SetData& x,const sets::SetData& u,
        const sets::SetData& s,Matrix a,Matrix b,Vector offset,std::uint64_t& preparation_ns,
        std::uint64_t& execution_ns) {
    Timer preparation;
    auto selected=provider(geometry::polyhedral::make_projection_registration(
        {geometry::polyhedral::ProjectionOutput::h,128}),"csl.polyhedron.h");
    reachability::NominalPredecessorRequest request{{{"geo05-report"},{"predecessor"},{"predecessor-result"}},
        x.as_handle(),u.as_handle(),s.as_handle(),std::move(a),std::move(b),std::move(offset)};
    auto prepared=take(reachability::prepare_nominal_predecessor(request,selected));
    preparation_ns=preparation.elapsed();
    // run() creates and executes its exclusive workspace internally. The
    // public API exposes no separate workspace-creation boundary.
    Timer execution; auto result=take(prepared.run(report_context())); execution_ns=execution.elapsed();
    return result;
}
sets::HRepresentation hrep(const SetHandle& handle) {
    auto data=take(sets::from_handle(handle)); auto repr=data.representation();
    auto* result=std::get_if<sets::HRepresentation>(&repr);
    if (!result) throw std::runtime_error("expected native H output");
    return *result;
}
bool contains(const SetHandle& handle,const Vector& point) {
    auto data=take(sets::from_handle(handle)); auto repr=data.representation();
    if (std::holds_alternative<sets::EmptyRepresentation>(repr)) return false;
    const auto* h=std::get_if<sets::HRepresentation>(&repr); if (!h) return false;
    for (std::size_t r=0;r<h->inequalities.rows();++r) {
        double sum=0; for (std::size_t c=0;c<point.size();++c) sum+=h->inequalities(r,c)*point[c];
        if (sum>h->upper_bounds[r]+1e-9) return false;
    }
    for (std::size_t r=0;r<h->equalities.rows();++r) {
        double sum=0; for (std::size_t c=0;c<point.size();++c) sum+=h->equalities(r,c)*point[c];
        if (std::abs(sum-h->equality_values[r])>1e-9) return false;
    }
    return true;
}
void run_predecessor(Trial& t) {
    Timer setup;
    auto x=sets::make_universal({{"X"},2,{"x0","x1"}});
    auto u=interval("U",-1,1,"u");
    auto target=hset("S",2,{0,2,{}},{},{2,2,{1,0,0,1}},{2,0},{"x0","x1"});
    t.input_rows=4;
    const auto fixture_setup=setup.elapsed();
    auto result=predecessor(std::get<sets::SetData>(x),u,target,{2,2,{1,0,0,0}},
        {2,1,{1,0}},{0,0},t.setup_ns,t.run_ns);
    t.setup_ns+=fixture_setup; t.workspace_ns.reset();
    auto output=result.result.output; auto rep=hrep(output); t.rows=rep.inequalities.rows()+rep.equalities.rows();
    t.result_kind="h"; t.result_encoding="h_rows";
    t.output_observed=true;
    Timer verify;
    t.oracle_passed=contains(output,{1,-1000})&&contains(output,{3,1000})&&!contains(output,{0.5,0});
    t.verification_ns=verify.elapsed(); t.work_observed=t.rows>0;
    t.status=t.oracle_passed&&t.work_observed?"passed":"oracle_failed";
}
void run_unreachable(Trial& t) {
    Timer setup;
    auto x=take(sets::make_universal({{"X"},2,{}})); auto u=interval("U",-1,1);
    auto target=hset("S",2,{0,2,{}},{},{1,2,{0,1}},{1});
    t.input_rows=3;
    const auto fixture_setup=setup.elapsed();
    auto result=predecessor(x,u,target,{2,2,{1,0,0,0}},{2,1,{1,0}},{0,0},t.setup_ns,t.run_ns);
    t.setup_ns+=fixture_setup; t.workspace_ns.reset();
    Timer verify; auto data=take(sets::from_handle(result.result.output));
    const auto repr=data.representation();
    t.output_observed=true;
    if (std::holds_alternative<sets::EmptyRepresentation>(repr)) { t.result_kind="empty"; t.rows=0; }
    else if (const auto* h=std::get_if<sets::HRepresentation>(&repr)) {
        t.result_kind="h"; t.rows=h->inequalities.rows()+h->equalities.rows();
        bool contradiction=false;
        for(std::size_t r=0;r<h->inequalities.rows();++r) {
            bool zero=true; for(std::size_t c=0;c<h->inequalities.cols();++c) zero=zero&&h->inequalities(r,c)==0.0;
            contradiction=contradiction||(zero&&h->upper_bounds[r]<0.0);
        }
        t.result_encoding=contradiction?"h_contradiction_row":"h_rows";
    } else if (std::holds_alternative<sets::VRepresentation>(repr)) { t.result_kind="v"; }
    else throw std::runtime_error("unreachable fixture returned unexpected representation");
    t.oracle_passed=!contains(result.result.output,{0,0})&&!contains(result.result.output,{100,-100});
    t.verification_ns=verify.elapsed(); t.work_observed=true;
    t.status=t.oracle_passed?"passed":"oracle_failed";
}
void run_integrator(Trial& t) {
    Timer setup; auto x=interval("X",-2,2,"x"); auto u=interval("U",-1,1,"u");
    auto target=interval("S",1,3,"x"); const auto fixture_setup=setup.elapsed();
    t.input_rows=6; t.expected_fm_peak_rows=6;
    auto result=predecessor(x,u,target,{1,1,{1}},{1,1,{1}},{0},t.setup_ns,t.run_ns);
    t.setup_ns+=fixture_setup; t.workspace_ns.reset(); Timer verify;
    t.result_kind="h"; t.result_encoding="h_rows";
    t.output_observed=true;
    t.rows=hrep(result.result.output).inequalities.rows()+hrep(result.result.output).equalities.rows();
    t.oracle_passed=contains(result.result.output,{0})&&contains(result.result.output,{1})&&contains(result.result.output,{2})&&
        !contains(result.result.output,{-0.125})&&!contains(result.result.output,{2.125});
    t.verification_ns=verify.elapsed(); t.work_observed=t.rows>0;
    t.status=t.oracle_passed&&t.work_observed?"passed":"oracle_failed";
}
void run_v(Trial& t) {
    Timer setup;
    auto input=take(sets::make_v({{"V"},2,{"x","y"}},
        {take(numeric::snapshot(Matrix{1,2,{2,3}})),take(numeric::snapshot(Matrix{2,2,{1,0,0,-1}}))}));
    t.input_rows=3;
    auto selected=provider(geometry::polyhedral::make_projection_registration(
        {geometry::polyhedral::ProjectionOutput::v,{}}),"csl.polyhedron.v");
    OperationRequest request{{{"geo05-report"},{"v-projection"},{"v-output"}},
        {"csl.geometry.polyhedral-projection"},Projection{input.as_handle(),{1}},SetRelation::equivalent,Assurance::numerical};
    auto prepared=take(selected.prepare(request)); t.setup_ns=setup.elapsed();
    Timer workspace; auto created=prepared.create(); t.workspace_ns=workspace.elapsed(); Timer run;
    auto outcome=std::get<0>(created)->run(report_context()); t.run_ns=run.elapsed();
    const auto& result=take(std::move(outcome)); auto data=take(sets::from_handle(result.output));
    auto repr=data.representation(); const auto* v=std::get_if<sets::VRepresentation>(&repr);
    if (!v) throw std::runtime_error("projection did not return V output");
    t.result_kind="v"; t.result_encoding="v_generators"; t.vertices=v->vertices.rows(); t.rays=v->rays.rows(); t.rows=t.vertices+t.rays; t.output_observed=true; Timer verify;
    t.oracle_passed=t.vertices==1&&t.rays==2&&v->vertices(0,0)==3&&v->rays(0,0)==0&&v->rays(1,0)==-1;
    t.verification_ns=verify.elapsed(); t.work_observed=t.vertices+t.rays>0;
    t.max_rows.reset(); t.status=t.oracle_passed?"passed":"oracle_failed";
}
Trial execute(const std::string& name,std::size_t repetition,std::string purpose="measurement") {
    Trial t; t.purpose=std::move(purpose); t.scenario=name; t.repetition=repetition; Timer total;
    try {
        if (name=="singular_a") run_predecessor(t);
        else if (name=="unreachable_equality_target") run_unreachable(t);
        else if (name=="integrator_predecessor") run_integrator(t);
        else if (name=="v_projection_preserves_ray") run_v(t);
        else throw std::runtime_error("unknown scenario");
    } catch (const std::exception& e) { t.detail=e.what(); t.status="failed"; }
    t.end_to_end_ns=total.elapsed(); return t;
}
std::vector<std::string> scenarios{"singular_a","unreachable_equality_target","integrator_predecessor","v_projection_preserves_ray"};
std::uint64_t count(const char* value) { auto n=std::stoull(value); if (!n||n>1000) throw std::runtime_error("count must be in [1,1000]"); return n; }
void emit(const Trial& t) {
    std::cout << "{\"purpose\":\""<<json_escape(t.purpose)<<"\",\"scenario\":\""<<json_escape(t.scenario)<<"\",\"repetition\":"<<t.repetition
      <<",\"status\":\""<<json_escape(t.status)<<"\",\"detail\":\""<<json_escape(t.detail)<<"\",\"oracle_scope\":\"numeric_literal_samples\",\"oracle_passed\":"<<(t.oracle_passed?"true":"false")
      <<",\"work_observed\":"<<(t.work_observed?"true":"false")<<",\"max_rows\":";
    if (t.max_rows) std::cout<<*t.max_rows; else std::cout<<"null";
    std::cout<<",\"input_rows\":"<<t.input_rows<<",\"output_rows\":";
    if(t.output_observed) std::cout<<t.rows; else std::cout<<"null";
    std::cout<<",\"result_kind\":";
    if(t.result_kind.empty()) std::cout<<"null"; else std::cout<<"\""<<json_escape(t.result_kind)<<"\"";
    std::cout<<",\"result_encoding\":";
    if(t.result_encoding.empty()) std::cout<<"null"; else std::cout<<"\""<<json_escape(t.result_encoding)<<"\"";
    std::cout<<",\"expected_fm_peak_rows\":";
    if (t.expected_fm_peak_rows) std::cout<<*t.expected_fm_peak_rows; else std::cout<<"null";
    std::cout<<",\"vertices\":"<<t.vertices<<",\"rays\":"<<t.rays
      <<",\"durations_ns\":{\"preparation_ns\":"<<t.setup_ns<<",\"workspace_ns\":";
    if (t.workspace_ns) std::cout<<*t.workspace_ns; else std::cout<<"null";
    std::cout<<",\"run_ns\":"<<t.run_ns<<",\"verification_ns\":"<<t.verification_ns
      <<",\"end_to_end_ns\":"<<t.end_to_end_ns<<"}}\n";
}
}
int main(int argc,char** argv) {
    try {
        bool smoke=false, measure=false; std::size_t repetitions=7,warmups=1;
        for (int i=1;i<argc;++i) {
            std::string arg=argv[i];
            if (arg=="--smoke") smoke=true;
            else if (arg=="--measure") measure=true;
            else if (arg=="--repetitions"&&i+1<argc) repetitions=count(argv[++i]);
            else if (arg=="--warmups"&&i+1<argc) warmups=count(argv[++i]);
            else throw std::runtime_error("usage: csl_geo05_projection_predecessor_report --smoke | --measure --repetitions N --warmups 1");
        }
        if (smoke==measure) throw std::runtime_error("choose exactly one of --smoke or --measure");
        if (measure&&(repetitions<7||warmups!=1)) throw std::runtime_error("measurement requires >=7 repetitions and exactly one warmup");
        const std::size_t reps=smoke?1:repetitions;
        if (!smoke) for (const auto& name:scenarios) emit(execute(name,0,"warmup"));
        for (std::size_t r=0;r<reps;++r) {
            auto order=scenarios; if (r%2) std::reverse(order.begin(),order.end());
            for (const auto& name:order) emit(execute(name,r,smoke?"smoke":"measurement"));
        }
        return 0;
    } catch (const std::exception& e) { std::cerr<<"geo05_report_error="<<e.what()<<'\n'; return 2; }
}
