#include <csl/verification/trajectory.hpp>
#include <iostream>
#include <stdexcept>
using namespace csl;
template<class T,class... Rest> T accepted(std::variant<T,Rest...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("publication failed");
    return std::get<T>(std::move(value));
}
int main() try {
    Problem p{{"installed"},std::make_shared<const SystemModel>(SystemModel{{{1,0,0},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,0,{}},{1,0,{}},{7}}},{}}),{0,1},KnownInitial{{2}},
        ContinuousDomain{{UniversalSet{0}}},{UniversalSet{1},Singleton{{7}}},{},{},
        InformationPattern::nominal_open_loop,ResidualNormTerminal{{1,1,{2}},{3}}};
    const auto original=accepted(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    verification::TrajectoryRequest request;request.witness={original.identity(),{{2},{7}},{{}},11};
    auto report=verification::verify_trajectory(original,request);
    if(report.feasibility!=verification::CheckStatus::numerical_pass ||
        report.objective!=verification::CheckStatus::numerical_pass || report.recomputed_objective!=11 ||
        report.completeness!=verification::CheckStatus::unsupported)
        throw std::runtime_error("original trajectory verification failed");
    request.witness.states[1][0]=8;
    report=verification::verify_trajectory(original,request);
    if(report.feasibility!=verification::CheckStatus::violation || report.objective!=verification::CheckStatus::violation)
        throw std::runtime_error("literal injected errors escaped verification");
    std::cout<<"Installed independent trajectory verification passed\n";return 0;
} catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
