#include <csl/adapters/convex/highs.hpp>
#include <csl/registry/provider.hpp>
#include <csl/geometry/approximation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <stdexcept>

using namespace csl;
using namespace csl::registry;
using Clock=std::chrono::steady_clock;
template<class T,class... R> T take(std::variant<T,R...> result) {
    if(auto* value=std::get_if<T>(&result))return std::move(*value);
    throw std::runtime_error("public CSL request rejected");
}
long long ns(Clock::time_point start) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count();
}
void approximations() {
    const auto start=Clock::now();
    const auto points=take(numeric::snapshot(Matrix{4,2,{-0.125,0,-0.125,0.25,0.125,-0.25,0.125,0}}));
    const auto rays=take(numeric::snapshot(Matrix{0,2,{}}));
    const auto source=take(sets::make_v({{"mpc06-exact-Z"},2,{"e1","e2"}},{points,rays}));
    Registry<ApproximationPort> registry;
    const Method method{{"mpc06.app04.st"},"1"};
    if(registry.add(geometry::approximation::make_directional_ellipsoid_registration(method,
        {"mpc06-app04-Z"},{2,2,{1,0,1,1}})))throw std::runtime_error("approximation registration rejected");
    const ApproximationRequest request{{{"mpc06-online"},{"error-enclosure"},{"mpc06-exact-Z"}},
        source.as_handle(),{"csl.ellipsoid.directional2d"},SetRelation::outer,1,Assurance::numerical};
    const auto result=geometry::approximation::run_registered(registry,method,request,ExecutionContext{});
    const auto* enclosure=std::get_if<geometry::approximation::EnclosedApproximation>(&result);
    if(!enclosure)throw std::runtime_error("APP-04 enclosure rejected");
    const auto ellipse=take(geometry::ellipsoidal::from_ellipsoid_handle(enclosure->result.output));
    std::cout<<"{\"schema\":\"csl.mpc06-online-approximation/1\",\"method\":\"mpc06.app04.st\",\"direction\":\"outer\",\"radii\":["
        <<ellipse.radii()[0]<<','<<ellipse.radii()[1]<<"],\"center\":["<<ellipse.center()[0]<<','<<ellipse.center()[1]
        <<"],\"orientation\":[[1,0],[1,1]],\"construction_ns\":"<<ns(start)<<"}\n";
}
int main() try {
    std::cout.imbue(std::locale::classic());
    std::cout<<std::setprecision(std::numeric_limits<double>::max_digits10);
    approximations();
    std::cout.flush();
    Registry<ConvexPort> providers;
    auto registration=take(adapters::convex::make_highs_registration());
    const auto backend=registration.identity;
    if(providers.add(std::move(registration)))throw std::runtime_error("convex registration rejected");
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.numerical={1e-8,1e-8};
    std::size_t index=0;double quadratic,linear,offset,lower,upper;
    while(std::cin>>quadratic>>linear>>offset>>lower>>upper) {
        const auto begin=Clock::now();
        const auto program=take(optimization::make_convex_program({
            {{"mpc06-online"},{"nominal-qp/"+std::to_string(index++)}},
            QuadraticTerminal{{1,1,{2*quadratic}},{linear},offset},
            {0,1,{0},{},{}},{{lower,upper}},{},{}}));
        Requirements requirements;requirements.output.representation={"csl.program-result.v1"};
        auto prepared=take(prepare_pipeline(select(providers,Method{backend.id,backend.version},program,requirements)));
        const auto prepare_ns=ns(begin);const auto setup=Clock::now();auto [workspace]=prepared.create();
        const auto setup_ns=ns(setup);context.deadline=Clock::now()+std::chrono::seconds(10);
        const auto solve=Clock::now();auto result=workspace->run(context);const auto solve_ns=ns(solve);
        const auto* answer=std::get_if<ProgramResult>(&result);
        if(!answer||answer->termination!=Termination::completed||answer->outcome.value!=MathematicalOutcome::optimal||
           !answer->primal||answer->primal->size()!=1||answer->outcome.subject!=program.identity()) {
            std::cout<<"{\"schema\":\"csl.mpc06-online-qp/1\",\"status\":\"inconclusive\",\"prepare_ns\":"<<prepare_ns<<",\"setup_ns\":"<<setup_ns<<",\"solve_ns\":"<<solve_ns<<"}\n";
            std::cout.flush();
            continue;
        }
        const auto checked=optimization::check_program_result(*answer,program,Assurance::numerical);
        const auto evaluated=take(optimization::evaluate_primal(program,*answer->primal,context.numerical,{{"mpc06-online-replay"},"1"}));
        std::cout<<"{\"schema\":\"csl.mpc06-online-qp/1\",\"status\":\""<<(checked.empty()?"completed":"contract_rejected")
            <<"\",\"backend\":\""<<backend.id.value<<"\",\"backend_version\":\""<<backend.version
            <<"\",\"program\":\""<<program.identity().program.value<<"\",\"a\":"<<(*answer->primal)[0]
            <<",\"objective\":"<<evaluated.original_objective<<",\"prepare_ns\":"<<prepare_ns
            <<",\"setup_ns\":"<<setup_ns<<",\"solve_ns\":"<<solve_ns
            <<",\"evidence\":\"numerical; independent exact reference required\",\"requested_threads\":1}\n";
        std::cout.flush();
    }
    return std::cin.eof()?0:1;
} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
