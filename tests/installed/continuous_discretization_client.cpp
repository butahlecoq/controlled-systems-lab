#include <csl/input/continuous_model.hpp>
#include <csl/model/linear_system.hpp>

#include <cmath>
#include <iostream>
#include <stdexcept>

int main() try {
    using namespace csl;
    constexpr std::string_view text=R"({"schema":"csl.continuous-model/1","dimensions":{"state":2,"control":1,"external":0},"times":[0,1,3],"hold":"zero_order_hold","coefficients":{"kind":"continuous_lti","A":[[0,1],[0,0]],"B":[[0],[1]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]},"integration":{"absolute_tolerance":1e-10,"relative_tolerance":1e-10,"max_attempts_per_stage":100000}})";
    auto input=input::load_continuous_model(std::as_bytes(std::span(text.data(),text.size())));
    if(!std::holds_alternative<input::ContinuousModelInput>(input))
        throw std::runtime_error("Continuous document rejected");
    auto loaded=std::get<input::ContinuousModelInput>(std::move(input));
    auto conversion=model::discretize(loaded.model,loaded.integration);
    if(!std::holds_alternative<model::DiscretizedModel>(conversion))
        throw std::runtime_error("Continuous discretization failed");
    auto result=std::get<model::DiscretizedModel>(std::move(conversion));
    if(result.receipt.source_domain!=TimeDomain::continuous ||
       result.receipt.output_domain!=TimeDomain::discrete ||
       result.receipt.variation!=model::CoefficientVariation::constant_lti ||
       result.receipt.stages.size()!=2)
        throw std::runtime_error("Time-domain provenance differs");
    auto snapshot=model::snapshot(result.model,result.times);
    if(!std::holds_alternative<model::LinearSystem>(snapshot))
        throw std::runtime_error("Discrete snapshot failed");
    auto system=std::get<model::LinearSystem>(std::move(snapshot));
    auto first=system.step({0},Vector{0,0},Vector{2},{});
    if(!std::holds_alternative<Vector>(first))
        throw std::runtime_error("First transition failed");
    auto second=system.step({1},std::get<Vector>(first),Vector{-1},{});
    if(!std::holds_alternative<Vector>(second) ||
       std::abs(std::get<Vector>(second)[0]-3)>1e-11 ||
       std::abs(std::get<Vector>(second)[1])>1e-11)
        throw std::runtime_error("Literal ZOH trajectory differs");
    std::cout << "Installed continuous adapter: two physical intervals and source receipt passed\n";
    return 0;
} catch(const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
