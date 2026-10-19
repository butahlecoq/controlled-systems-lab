#include <csl/model/discretization.hpp>
#include <csl/model/linear_system.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::model;

constexpr double tolerance=1e-11;

void near(double actual,double expected) {
    if(!std::isfinite(actual) || std::abs(actual-expected)>tolerance)
        throw std::runtime_error("Independent double-integrator literal differs");
}

struct Observation {
    double a01,b0,b1,x1_position,x1_velocity,x2_position,x2_velocity;
    std::size_t accepted,rejected;
    double local_estimate;
};

Observation run_once() {
    const ContinuousAffineModel continuous{{2,1,0},{0,1,3},
        HoldConvention::zero_order_hold,
        LinearStage{{2,2,{0,1,0,0}},{2,1,{0,1}},{2,0,{}},{0,0}}};
    const auto converted=discretize(continuous);
    if(!std::holds_alternative<DiscretizedModel>(converted))
        throw std::runtime_error("Public discretizer did not return a model");
    const auto& result=std::get<DiscretizedModel>(converted);
    if(result.receipt.source_domain!=TimeDomain::continuous ||
       result.receipt.output_domain!=TimeDomain::discrete ||
       result.receipt.variation!=CoefficientVariation::constant_lti ||
       result.receipt.hold!=HoldConvention::zero_order_hold ||
       result.receipt.stages.size()!=2)
        throw std::runtime_error("Time-domain receipt differs");
    const auto& stages=std::get<std::vector<LinearStage>>(result.model.dynamics.stages);
    if(stages.size()!=2)throw std::runtime_error("Expected two stages");
    near(stages[0].A.values.at(1),1);
    near(stages[1].A.values.at(1),2);
    near(stages[0].B.values.at(0),0.5);
    near(stages[0].B.values.at(1),1);
    near(stages[1].B.values.at(0),2);
    near(stages[1].B.values.at(1),2);
    const auto model=snapshot(result.model,result.times);
    if(!std::holds_alternative<LinearSystem>(model))
        throw std::runtime_error("Discrete snapshot failed");
    const auto& discrete=std::get<LinearSystem>(model);
    const auto first=discrete.step({0},Vector{0,0},Vector{2},{});
    if(!std::holds_alternative<Vector>(first))throw std::runtime_error("First step failed");
    const auto& x1=std::get<Vector>(first);
    const auto second=discrete.step({1},x1,Vector{-1},{});
    if(!std::holds_alternative<Vector>(second))throw std::runtime_error("Second step failed");
    const auto& x2=std::get<Vector>(second);
    near(x1.at(0),1);near(x1.at(1),2);
    near(x2.at(0),3);near(x2.at(1),0);
    return {stages[1].A.values[1],stages[1].B.values[0],
        stages[1].B.values[1],x1[0],x1[1],x2[0],x2[1],
        result.receipt.stages[0].accepted_steps+result.receipt.stages[1].accepted_steps,
        result.receipt.stages[0].rejected_steps+result.receipt.stages[1].rejected_steps,
        std::max(result.receipt.stages[0].max_local_error_estimate,
                 result.receipt.stages[1].max_local_error_estimate)};
}

void row(std::string_view phase,std::size_t repetition,std::size_t calls) {
    const auto start=std::chrono::steady_clock::now();
    Observation result{};
    for(std::size_t i=0;i<calls;++i)result=run_once();
    const auto end=std::chrono::steady_clock::now();
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start).count();
    if(elapsed<=0)throw std::runtime_error("Measurement clock did not advance");
    std::cout << phase << ",double-integrator," << repetition << ',' << calls
              << ",success,true," << elapsed << ',' << result.a01 << ','
              << result.b0 << ',' << result.b1 << ',' << result.x1_position << ','
              << result.x1_velocity << ',' << result.x2_position << ','
              << result.x2_velocity << ',' << result.accepted << ','
              << result.rejected << ',' << result.local_estimate << '\n';
}
}

int main(int argc,char** argv) try {
    if(argc!=2)throw std::runtime_error("Expected smoke or measure mode");
    const std::string_view mode{argv[1]};
    std::cout << "phase,case,repetition,calls,status,verified,elapsed_ns,a01,b0,b1,"
                 "x1_position,x1_velocity,x2_position,x2_velocity,accepted,rejected,local_estimate\n";
    if(mode=="smoke")row("smoke",0,1);
    else if(mode=="measure") {
        row("warmup",0,100);
        for(std::size_t repetition=0;repetition<7;++repetition)
            row("trial",repetition,100);
    } else throw std::runtime_error("Expected smoke or measure mode");
    return 0;
} catch(const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
