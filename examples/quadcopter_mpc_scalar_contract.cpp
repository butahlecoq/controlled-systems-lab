#include "quadcopter_mpc_task.hpp"

#include <csl/adapters/convex/highs.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>

int main() try {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    using namespace csl::examples::quadcopter_mpc;
    const NominalProblem problem{
        {1,1,{1}}, {1,1,{1}}, {1,1,{1}}, {1,1,{1}}, {1,1,{1}},
        {0}, {1}, 2, {{-10,10}}, {{-10,10}}};
    Registry<ConvexPort> registry;
    if (registry.add(std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration())))
        throw std::runtime_error("HiGHS registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto solve=[&](const NominalProblem& task) {
        auto made=compile(task);
        if(const auto* errors=std::get_if<Diagnostics>(&made)) {
            for(const auto& error:*errors) std::cerr<<error.field<<": "<<error.explanation<<'\n';
            throw std::runtime_error("scalar tracking QP rejected");
        }
        if(!std::holds_alternative<ConvexProgram>(made)) throw std::runtime_error("scalar tracking QP stopped");
        const auto& program=std::get<ConvexProgram>(made);
        auto preparation=prepare_pipeline(select(registry,{{"csl.convex.highs"},{}},program,requirements));
        if(!std::holds_alternative<PreparedPipeline<ConvexPort>>(preparation)) throw std::runtime_error("HiGHS selection failed");
        auto [workspace]=std::get<PreparedPipeline<ConvexPort>>(preparation).create();
        auto outcome=workspace->run({std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"scalar-mpc"});
        const auto* result=std::get_if<ProgramResult>(&outcome);
        if(!result || result->termination!=Termination::completed || result->outcome.value!=MathematicalOutcome::optimal || !result->primal)
            throw std::runtime_error("scalar MPC did not solve to numerical optimality");
        return *result->primal;
    };
    const auto primal=solve(problem);
    if(primal.size()!=5 || std::abs(primal[0])>1e-7 || std::abs(primal[1]-.6)>1e-7 ||
       std::abs(primal[2]-.8)>1e-7 || std::abs(primal[3]-.6)>1e-7 || std::abs(primal[4]-.2)>1e-7)
        throw std::runtime_error("running-state/control tracking optimum was not u=(0.6,0.2)");
    auto observed_problem=problem;
    observed_problem.initial[0]=.25;
    const auto observed_primal=solve(observed_problem);
    if(std::abs(observed_primal[0]-.25)>1e-7 || std::abs(observed_primal[3]-.45)>1e-7 ||
       std::abs(observed_primal[4]-.15)>1e-7)
        throw std::runtime_error("MPC initial equality did not follow the observed state");
    std::cout << "scalar running-state MPC: u=(0.6,0.2); observed-state equality preserved\n";
} catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
