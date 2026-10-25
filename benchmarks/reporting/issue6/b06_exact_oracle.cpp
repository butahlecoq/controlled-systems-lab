#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
using nlohmann::json;
using State=std::array<std::int64_t,4>;
using Plan=std::array<int,5>;
using DisturbanceHistory=std::array<int,10>;

constexpr std::array<int,5> action_tenths{10,3,0,-3,-10};
constexpr std::array<std::array<int,2>,4> disturbance_corners{{
    {{-1,-1}},{{-1,1}},{{1,-1}},{{1,1}}}};

std::int64_t objective_numerator(const State& x) {
    const auto z1=x[0]-45000;
    const auto z2=x[1];
    const auto z3=30000-x[2];
    const auto z4=x[3];
    return 4*z1*z1+4*z2*z2+9*z3*z3+9*z4*z4+(2*z2-3*z4)*(2*z2-3*z4);
}

State advance(const State& x,int action_tenth,int disturbance1,int disturbance2) {
    return {x[0]+105*action_tenth+75*disturbance1,
        x[1]-2*x[0],
        x[2]-50*action_tenth-60*disturbance2,
        x[3]-2*x[2]};
}

std::vector<DisturbanceHistory> histories() {
    std::vector<DisturbanceHistory> result(1);
    for(std::size_t stage=0;stage<5;++stage) {
        std::vector<DisturbanceHistory> next;
        next.reserve(result.size()*4);
        for(const auto& prefix:result) for(std::size_t corner=0;corner<4;++corner) {
            auto history=prefix;
            history[2*stage]=disturbance_corners[corner][0];
            history[2*stage+1]=disturbance_corners[corner][1];
            next.push_back(history);
        }
        result=std::move(next);
    }
    return result;
}

std::int64_t worst_numerator(const Plan& plan,const std::vector<DisturbanceHistory>& all) {
    std::int64_t worst=0;
    for(const auto& disturbances:all) {
        State x{43965,302*1500,30531,207*1500};
        for(std::size_t stage=0;stage<5;++stage)
            x=advance(x,action_tenths[static_cast<std::size_t>(plan[stage])],
                disturbances[2*stage],disturbances[2*stage+1]);
        const auto value=objective_numerator(x);
        if(value>worst) worst=value;
    }
    return worst;
}

void enumerate(std::size_t stage,Plan& plan,const std::vector<DisturbanceHistory>& all,
        std::vector<std::int64_t>& values) {
    if(stage==plan.size()) {
        values.push_back(worst_numerator(plan,all));
        return;
    }
    for(std::size_t action=0;action<action_tenths.size();++action) {
        plan[stage]=static_cast<int>(action);
        enumerate(stage+1,plan,all,values);
    }
}
}

int main() {
    try {
        const auto all=histories();
        Plan plan{};
        std::vector<std::int64_t> values;
        values.reserve(3125);
        enumerate(0,plan,all,values);
        if(values.size()!=3125 || all.size()!=1024) throw std::runtime_error("exhaustive domain size mismatch");
        const auto best=*std::min_element(values.begin(),values.end());
        std::vector<std::size_t> minimizing;
        for(std::size_t i=0;i<values.size();++i) if(values[i]==best) minimizing.push_back(i);
        const std::size_t printed_index=3*625+0*125+2*25+2*5+1;
        std::cout<<json{{"schema","csl.issue6-b06-exact-reference/1"},
            {"source_commit",CSL_ISSUE6_SOURCE_COMMIT},
            {"fixture_sha256",CSL_ISSUE6_FIXTURE_SHA256},
            {"oracle_sha256",CSL_ISSUE6_ORACLE_SHA256},
            {"method","integer-scaled exhaustive control and disturbance vertex enumeration"},
            {"state_scale",1500},{"objective_numerator_denominator",9000000},
            {"plan_count",values.size()},{"disturbance_histories_per_plan",all.size()},
            {"evaluated_pairs",values.size()*all.size()},{"minimizing_plan_indices",minimizing},
            {"minimum_objective_squared_numerator",best},{"objective_norm",
                std::sqrt(static_cast<long double>(best)/9000000.0L)},
            {"printed_l09_plan_index",printed_index},{"printed_plan_squared_numerator",values.at(printed_index)},
            {"per_plan_worst_squared_numerators",values}}.dump()<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"B06 exact reference failed: "<<error.what()<<'\n';
        return 2;
    }
}
