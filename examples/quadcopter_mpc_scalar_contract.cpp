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
    auto sample_task=problem;
    sample_task.initial={0.25};
    const Vector sample_states{0.25,0.65,0.45};
    const Vector sample_controls{0.4,-0.2};
    if(!source_history_feasible(sample_task,sample_states,sample_controls))
        throw std::runtime_error("Independent source feasibility check rejected a hand-built history");
    auto sample_program=compile_nominal_quadratic_history(make_task(sample_task));
    if(!std::holds_alternative<ConvexProgram>(sample_program))
        throw std::runtime_error("History compiler rejected the source21-shaped sample task");
    const Vector sample_history{0.25,0.65,0.45,0.4,-0.2};
    auto compiled_evaluation=evaluate_primal(std::get<ConvexProgram>(sample_program),sample_history,
        {1e-9,1e-9},{{"source21-literal-cost-and-constraint-cross-check"},"1"});
    if(!std::holds_alternative<ConvexPrimalEvaluation>(compiled_evaluation) ||
       std::abs(std::get<ConvexPrimalEvaluation>(compiled_evaluation).original_objective-
           evaluate_source_cost(sample_task,sample_states,sample_controls))>1e-9 ||
       std::get<ConvexPrimalEvaluation>(compiled_evaluation).residuals.rows.violation>1e-9)
        throw std::runtime_error("Compiled cost/constraints disagreed on an arbitrary source21-shaped history");
    auto invalid_states=sample_states;
    invalid_states[2]+=0.1;
    if(source_history_feasible(sample_task,invalid_states,sample_controls))
        throw std::runtime_error("Independent source feasibility check accepted a changed dynamics state");
    Registry<ConvexPort> registry;
    if (registry.add(std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration())))
        throw std::runtime_error("HiGHS registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto solve=[&](const NominalProblem& task) {
        auto made=compile_nominal_quadratic_history(make_task(task));
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
