#include <csl/controllers/observed_replay.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {
using namespace csl;
using namespace csl::model;
using namespace csl::controllers;
using nlohmann::json;
using Clock=std::chrono::steady_clock;

constexpr std::string_view source_commit="c23aaf13c1c1e5480cc22dd5bac5cd3e79562609";
constexpr std::string_view schema="csl.ext04-replay-trial/1";
constexpr std::string_view timed_scope=
    "batch of fresh public LinearSystem snapshots and replay_observed_policy calls, "
    "estimator/controller callbacks, full literal state/history/release/input oracle checks, "
    "and per-call result JSON construction and assignment/replacement; excludes process startup, JSONL serialization, "
    "Python saved-row validation, persistence and rendering";
constexpr std::array<std::string_view,3> fixtures{
    "partial_noisy_delayed","post_feedthrough","no_channel"};

void require(bool condition,const char* explanation) {
    if (!condition) throw std::runtime_error(explanation);
}
ObservationPoint pre(std::size_t stage) {return {{stage},ObservationTiming::before_decision};}
ObservationPoint post(std::size_t stage) {return {{stage},ObservationTiming::after_decision};}
std::string event(ObservationPoint point) {
    return std::string(point.timing==ObservationTiming::before_decision?"before(":"after(")+
        std::to_string(point.stage.value)+")";
}

struct Fixture {
    SystemModel authored;
    Vector times;
    ReplayInputs inputs;
    Estimator estimator;
    Controller controller;
};

Fixture partial_noisy_delayed() {
    SystemModel system{{{2,1,0},TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}},{2,1,{1,0}},{2,0,{}},{0,0}}},
        {{ObservationStage{{1,2,{1,0}},{1,1,{0}},{1,0,{}},{1,1,{1}},{0}},
            {{{0},pre(0),pre(0),std::nullopt}}},
         {ObservationStage{{1,2,{0,1}},{1,1,{0}},{1,0,{}},{1,0,{}},{0}},
            {{{1},post(0),pre(1),std::nullopt}}}}};
    return {std::move(system),{0,1,2},{{1,7},{{},{}},{{{3}},{{}}}},
        [](StageIndex,std::span<const ReleasedObservation> history) {
            return Vector{history.empty()?0.0:history.back().value.values[0],0};
        },
        [](StageIndex stage,std::span<const ReleasedObservation>,std::span<const double> estimate) {
            return Vector{stage.value==0?estimate[0]-3:estimate[0]};
        }};
}

Fixture post_feedthrough() {
    SystemModel system{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},
        {{ObservationStage{{1,1,{1}},{1,1,{2}},{1,0,{}},{1,1,{1}},{0}},
            {{{0},post(0),post(0),StageIndex{0}}}}}};
    return {std::move(system),{0,1,2},{{2},{{},{}},{{{3}}}},
        [](StageIndex,std::span<const ReleasedObservation> history) {
            return Vector{history.empty()?0.0:history.back().value.values[0]};
        },
        [](StageIndex stage,std::span<const ReleasedObservation>,std::span<const double> estimate) {
            return Vector{stage.value==0?1.0:estimate[0]};
        }};
}

Fixture no_channel() {
    SystemModel system{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}};
    return {std::move(system),{0,1},{{5},{{}},{}},
        [](StageIndex,std::span<const ReleasedObservation>) {return Vector{0};},
        [](StageIndex,std::span<const ReleasedObservation>,std::span<const double>) {return Vector{2};}};
}

using Builder=Fixture (*)();
constexpr std::array<Builder,3> builders{partial_noisy_delayed,post_feedthrough,no_channel};

json expected(std::size_t fixture) {
    if (fixture==0) return {
        {"status","passed"},{"states",{{1,7},{2,7},{9,7}}},
        {"observed_values",{{4},{7}}},{"observed_channels",{0,1}},
        {"measurement_events",{"before(0)","after(0)"}},
        {"release_events",{"before(0)","before(1)"}},
        {"actions",{{1},{7}}},{"estimates",{{4,0},{7,0}}},
        {"available_values",{{{4}},{{4},{7}}}},{"available_counts",{1,2}},
        {"decision_stages",{0,1}},
        {"released",{
            {{"released_index",0},{"channel",0},{"sample",0},{"measured_at","before(0)"},
             {"available_at","before(0)"},{"released_at","before(0)"},{"values",{4}}},
            {{"released_index",1},{"channel",1},{"sample",0},{"measured_at","after(0)"},
             {"available_at","before(1)"},{"released_at","before(1)"},{"values",{7}}}}},
        {"available",{
            {{{"released_index",0},{"channel",0},{"sample",0},{"measured_at","before(0)"},
              {"available_at","before(0)"},{"released_at","before(0)"},{"values",{4}}}},
            {{{"released_index",0},{"channel",0},{"sample",0},{"measured_at","before(0)"},
              {"available_at","before(0)"},{"released_at","before(0)"},{"values",{4}}},
             {{"released_index",1},{"channel",1},{"sample",0},{"measured_at","after(0)"},
              {"available_at","before(1)"},{"released_at","before(1)"},{"values",{7}}}}}}};
    if (fixture==1) return {
        {"status","passed"},{"states",{{2},{3},{10}}},
        {"observed_values",{{7}}},{"observed_channels",{0}},
        {"measurement_events",{"after(0)"}},{"release_events",{"after(0)"}},
        {"actions",{{1},{7}}},{"estimates",{{0},{7}}},
        {"available_values",{json::array(),json::array({json::array({7})})}},
        {"available_counts",{0,1}},{"decision_stages",{0,1}},
        {"released",{{{"released_index",0},{"channel",0},{"sample",0},{"measured_at","after(0)"},
                      {"available_at","after(0)"},{"released_at","after(0)"},{"values",{7}}}}},
        {"available",{json::array(),
                      {{{"released_index",0},{"channel",0},{"sample",0},{"measured_at","after(0)"},
                        {"available_at","after(0)"},{"released_at","after(0)"},{"values",{7}}}}}}};
    return {{"status","passed"},{"states",{{5},{7}}},
        {"observed_values",json::array()},{"observed_channels",json::array()},
        {"measurement_events",json::array()},{"release_events",json::array()},
        {"actions",{{2}}},{"estimates",{{0}}},
        {"available_values",{json::array()}},{"available_counts",{0}},
        {"decision_stages",{0}},{"released",json::array()},
        {"available",{json::array()}}};
}

json identity(const ReleasedObservation& item,std::size_t released_index) {
    return {{"released_index",released_index},{"channel",item.channel.value},
        {"sample",item.sample.value},
        {"measured_at",event(item.value.metadata.sample.measured_at)},
        {"available_at",event(item.value.metadata.sample.available_at)},
        {"released_at",event(item.released_at)},{"values",item.value.values}};
}

json observed(const ReplayRecord& record) {
    json value={{"status","passed"},{"states",record.states},
        {"observed_values",json::array()},{"observed_channels",json::array()},
        {"measurement_events",json::array()},{"release_events",json::array()},
        {"actions",json::array()},{"estimates",json::array()},
        {"available_values",json::array()},{"available_counts",json::array()},
        {"decision_stages",json::array()},{"released",json::array()},
        {"available",json::array()}};
    for (std::size_t index=0;index<record.released.size();++index) {
        const auto& item=record.released[index];
        value["released"].push_back(identity(item,index));
        value["observed_values"].push_back(item.value.values);
        value["observed_channels"].push_back(item.channel.value);
        value["measurement_events"].push_back(event(item.value.metadata.sample.measured_at));
        value["release_events"].push_back(event(item.released_at));
        require(event(item.value.metadata.sample.available_at)==event(item.released_at),
            "release event differs from validated metadata");
    }
    for (const auto& decision:record.decisions) {
        value["decision_stages"].push_back(decision.stage.value);
        value["actions"].push_back(decision.action);
        value["estimates"].push_back(decision.estimate);
        value["available_counts"].push_back(decision.available.size());
        json available=json::array();
        json available_events=json::array();
        for (const auto& item:decision.available) {
            available.push_back(item.value.values);
            std::size_t index=0;
            while (index<record.released.size() &&
                !(record.released[index].channel.value==item.channel.value &&
                  record.released[index].sample.value==item.sample.value)) ++index;
            require(index<record.released.size(),"decision history has unknown observation");
            auto event_identity=identity(item,index);
            require(event_identity==value["released"][index],
                "decision history differs from released observation");
            available_events.push_back(std::move(event_identity));
        }
        value["available_values"].push_back(std::move(available));
        value["available"].push_back(std::move(available_events));
    }
    return value;
}

json checked_call(std::size_t index) {
    auto fixture=builders[index]();
    auto system=model::snapshot(fixture.authored,fixture.times);
    require(std::holds_alternative<LinearSystem>(system),"authored model rejected");
    auto replay=replay_observed_policy(std::get<LinearSystem>(system),fixture.inputs,
                                       fixture.estimator,fixture.controller);
    require(std::holds_alternative<ReplayRecord>(replay),"public replay rejected or stopped");
    const auto& record=std::get<ReplayRecord>(replay);
    require(record.inputs.initial_state==fixture.inputs.initial_state &&
        record.inputs.external==fixture.inputs.external &&
        record.inputs.measurement_errors==fixture.inputs.measurement_errors,
        "replay inputs were not retained");
    auto result=observed(record);
    require(result==expected(index),"independent literal replay oracle differs");
    return result;
}

json input_catalogue() {
    const json partial={{"dimensions",{2,1,0}},{"horizon",2},{"A",{1,0,0,1}},
        {"B",{1,0}},{"E",json::array()},{"offset",{0,0}},{"times",{0,1,2}},
        {"initial",{1,7}},{"external",{json::array(),json::array()}},
        {"errors",{{{3}},{json::array()}}},
        {"channels",{
            {{"C",{1,0}},{"Du",{0}},{"Dw",json::array()},{"F",{1}},
             {"offset",{0}},{"state_stage",0},{"input_stage",nullptr},
             {"measured_at","before(0)"},{"available_at","before(0)"}},
            {{"C",{0,1}},{"Du",{0}},{"Dw",json::array()},{"F",json::array()},
             {"offset",{0}},{"state_stage",1},{"input_stage",nullptr},
             {"measured_at","after(0)"},{"available_at","before(1)"}}}},
        {"estimator","last output in first coordinate, other coordinate zero"},
        {"controller","u0=estimate[0]-3; u1=estimate[0]"}};
    const json post_case={{"dimensions",{1,1,0}},{"horizon",2},{"A",{1}},
        {"B",{1}},{"E",json::array()},{"offset",{0}},{"times",{0,1,2}},
        {"initial",{2}},{"external",{json::array(),json::array()}},
        {"errors",{{{3}}}},
        {"channels",{
            {{"C",{1}},{"Du",{2}},{"Dw",json::array()},{"F",{1}},
             {"offset",{0}},{"state_stage",0},{"input_stage",0},
             {"measured_at","after(0)"},{"available_at","after(0)"}}}},
        {"estimator","last output, or zero before any output"},
        {"controller","u0=1; u1=estimate[0]"}};
    const json absent={{"dimensions",{1,1,0}},{"horizon",1},{"A",{1}},
        {"B",{1}},{"E",json::array()},{"offset",{0}},{"times",{0,1}},
        {"initial",{5}},{"external",{json::array()}},
        {"errors",json::array()},{"channels",json::array()},
        {"estimator","zero with empty history"},{"controller","constant u=2"}};
    return {{"partial_noisy_delayed",partial},{"post_feedthrough",post_case},
            {"no_channel",absent}};
}

int positive(const char* raw,int minimum,int maximum) {
    const auto value=std::stoi(raw);
    if (value<minimum || value>maximum || std::to_string(value)!=raw)
        throw std::invalid_argument("invalid positive integer");
    return value;
}

bool run(std::size_t index,int round,bool warmup,int batch) {
    int checked=0;
    json result;
    std::string error;
    const auto start=Clock::now();
    for (int call=0;call<batch;++call) {
        try {result=checked_call(index);++checked;}
        catch (const std::exception& exception) {error=exception.what();break;}
    }
    const auto stop=Clock::now();
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count();
    std::cout<<json{{"schema",schema},{"fixture",fixtures[index]},{"round",round},
        {"warmup",warmup},{"batch",batch},{"checked_calls",checked},
        {"elapsed_ns",elapsed},{"status",error.empty()?"passed":"oracle_failed"},
        {"error",error.empty()?json(nullptr):json(error)},{"result",result}}.dump()<<'\n';
    std::cout.flush();
    return error.empty();
}
} // namespace

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string(argv[1])=="--describe") {
            std::cout<<json{{"schema","csl.ext04-replay-driver/1"},{"source_commit",source_commit},
                {"module","CSL::controllers"},{"scalar","binary64"},
                {"fixtures",fixtures},{"timed_scope",timed_scope},
                {"inputs",input_catalogue()}}.dump()<<'\n';
            return 0;
        }
        const bool smoke=argc==2 && std::string(argv[1])=="--smoke";
        const bool measure=argc==5 && std::string(argv[1])=="--measure";
        if (!smoke && !measure)
            throw std::invalid_argument("usage: --describe | --smoke | --measure REPETITIONS WARMUPS BATCH");
        const int repetitions=smoke?1:positive(argv[2],7,100);
        const int warmups=smoke?0:positive(argv[3],1,1);
        const int batch=smoke?1:positive(argv[4],1,100000);
        bool passed=true;
        for (int warmup=0;warmup<warmups;++warmup)
            for (std::size_t index=0;index<fixtures.size();++index)
                passed=run(index,warmup,true,batch) && passed;
        for (int round=0;round<repetitions;++round) {
            if (round%2==0)
                for (std::size_t index=0;index<fixtures.size();++index)
                    passed=run(index,round,false,batch) && passed;
            else
                for (std::size_t index=fixtures.size();index>0;--index)
                    passed=run(index-1,round,false,batch) && passed;
        }
        return passed?0:2;
    } catch (const std::exception& exception) {
        std::cerr<<exception.what()<<'\n';return 2;
    }
}
