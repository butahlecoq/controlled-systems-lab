#include <csl/reachability/fixed_tail_policy.hpp>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace csl;
using namespace csl::reachability;
namespace {
void require(bool value,const char* reason) {if(!value)throw std::runtime_error(reason);}
Matrix identity(std::size_t n) {Matrix out{n,n,Vector(n*n,0)};for(std::size_t j=0;j<n;++j)out.values[j*n+j]=1;return out;}
FixedTailHRows empty(std::size_t n) {return {{0,n,{}},{},{0,n,{}},{}};}
optimization::HistoryCostProgram cost() {
    Matrix Q{3,3,Vector(9,0)};Q.values[4]=2;
    return {{{1,1,0},1},{3,Q,{0,-2,0},1},{},QuadraticTerminal{{1,1,{2}},{-2},1},
        {"validation-J",1,{}},0};
}
FixedTailSolveRequest request() {
    return {{{"validation-problem"},{"validation-solve"}},empty(3),cost(),
        {{{1,1,0},1},identity(3),Vector(3,0)},{},Vector(3,0),true,{}};
}
FixedTailModel model() {
    FixedTailHRows control{{2,1,{1,-1}},{0,0},{0,1,{}},{}};
    FixedTailHRows full{{2,3,{0,0,1,0,0,-1}},{0,0},{2,3,{1,0,0,-1,1,-1}},{0,0}};
    return {{"validation-problem"},{{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{0},
        {empty(1),empty(1)},{control},{{Interval{0,0}}},full,cost()};
}
class MalformedWorkspace final:public FixedTailOptimizerWorkspace {
public:
    explicit MalformedWorkspace(bool bad_anchor):bad_anchor_(bad_anchor){}
    FixedTailSolveOutcome solve(const FixedTailSolveRequest& r,const ExecutionContext&) override {
        auto result=FixedTailSolveResult{r.initial_primary,Vector(3,0),0,r.initial_primary,{},r.initial_primary,{},"deliberate malformed-provider fixture"};
        if(bad_anchor_)result.history.clear();
        else if(!r.feasibility_only)result.primary.clear();
        return result;
    }
private:
    bool bad_anchor_;
};
}
int run() {
    FullHistoryLift lift{{{1,1,0},1},{3,1,{0,1,1}},{0,0,0}};
    const Vector current{1};
    auto bad=lift;bad.offset.pop_back();
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(bad,current)),"short lift offset was not rejected");
    bad=lift;bad.map.values.clear();
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(bad,current)),"missing lift matrix storage was not rejected");
    bad=lift;bad.map.rows=std::numeric_limits<std::size_t>::max();
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(bad,current)),"overflowing lift dimensions were not rejected");
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(lift,Vector{std::numeric_limits<double>::quiet_NaN()})),"nonfinite current action was not rejected");
    require(std::get<Vector>(recover_fixed_tail_history(lift,current))==Vector({0,1,1}),"valid public recovery changed");

    const auto valid=request();
    require(check_fixed_tail_solve_request(valid).empty(),"valid native solve request failed validation");
    auto malformed=valid;
    malformed.domain.inequalities={1,3,{}};malformed.domain.upper_bounds={0};
    require(!check_fixed_tail_solve_request(malformed).empty(),"missing H matrix storage was not rejected");
    malformed=valid;malformed.domain.equalities={1,3,{1,0,0}};
    require(!check_fixed_tail_solve_request(malformed).empty(),"missing equality bound was not rejected");
    malformed=valid;malformed.source_cost.quadratic.Q.values.clear();
    require(!check_fixed_tail_solve_request(malformed).empty(),"missing quadratic storage was not rejected");
    malformed=valid;malformed.source_cost.quadratic.linear={0};
    require(!check_fixed_tail_solve_request(malformed).empty(),"short source linear objective was not rejected");
    malformed=valid;malformed.source_cost.residual_norms.push_back({{1,3,{}},{0},{1},1});
    require(!check_fixed_tail_solve_request(malformed).empty(),"missing residual matrix was not rejected");
    malformed=valid;malformed.source_cost.residual_norms.push_back({{1,3,{1,0,0}},{0},{-1},1});
    require(!check_fixed_tail_solve_request(malformed).empty(),"negative norm weight was not rejected");

    for(const bool bad_anchor:{true,false}) {
        registry::Registry<registry::FixedTailOptimizerPort> providers;
        registry::Registration<registry::FixedTailOptimizerPort> entry{{{"test.malformed-provider"},"1"},
            [](const FixedTailSolveRequest&,const registry::Requirements&)->registry::Capability {
                return registry::Offer{{{"csl.fixed-tail-solve.v1"},Assurance::numerical,{},{},{}}};
            },[bad_anchor](const FixedTailSolveRequest&)->std::unique_ptr<FixedTailOptimizerWorkspace> {
                return std::make_unique<MalformedWorkspace>(bad_anchor);
            }};
        const registry::Method method{entry.identity.id,entry.identity.version};
        require(!providers.add(std::move(entry)),"fixture provider registration failed");
        registry::Requirements requirements;requirements.output.representation={"csl.fixed-tail-solve.v1"};
        auto selected=registry::prepare_provider(registry::select_provider(providers,method,requirements));
        require(std::holds_alternative<registry::PreparedProvider<registry::FixedTailOptimizerPort>>(selected),"fixture selection failed");
        const auto result=fixed_tail_policy({model(),{"malformed-result"},FixedTailFamily::box,Vector(3,0),{}},
            std::get<registry::PreparedProvider<registry::FixedTailOptimizerPort>>(selected),{});
        const auto* failure=std::get_if<FixedTailPolicyFailure>(&result);
        require(failure!=nullptr,"malformed provider result was accepted or escaped its typed failure");
        require(failure->phase==(bad_anchor?"feasibility":"reduced-argmin"),"malformed result failed in the wrong phase");
    }
    std::cout<<"Native fixed-tail boundaries: malformed lift, request and provider result rejection passed\n";
    return 0;
}
int main() {
    try{return run();}
    catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
