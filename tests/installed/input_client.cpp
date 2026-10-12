#include <csl/input/scenario_loader.hpp>
#include <iostream>
#include <stdexcept>
int main() try {
    using namespace csl;
    const auto problem=[] {
        std::string text=R"({"schema":"csl.scenario/1","horizon":1,"model":{"kind":"linear_discrete","A":[[0]],"B":[[1]]},"initial_state":[2],"controls":{"kind":"singleton","point":[3]},"objective":{"kind":"linear","coefficients":[1]}})";
        auto outcome=input::load_scenario(std::as_bytes(std::span(text.data(),text.size())));
        if(!std::holds_alternative<input::LoadedScenario>(outcome)) throw std::runtime_error("input rejected");
        return std::get<input::LoadedScenario>(outcome).problem();
    }();
    if(problem.identity().value!="csl.problem.v1.sha256:167962d4127c26ae199032551dceb32e8a04bfed653cfd44e90ad6cc89a36cb4" || problem.canonical_bytes().size()!=260)
        throw std::runtime_error("literal identity differs");
    const auto result=problem.model().step({0},Vector{2},Vector{3},{});
    if(!std::holds_alternative<Vector>(result) || std::get<Vector>(result)!=Vector{3}) throw std::runtime_error("literal transition differs");
    if(std::get<double>(optimization::evaluate(problem.objective(),Vector{3}))!=3) throw std::runtime_error("original cost differs");
    std::cout << "Installed input client: owning scenario, literal identity and original cost passed\n";
} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
