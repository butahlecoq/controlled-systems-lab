#include <csl/reachability/finite_feedback_port.hpp>
#include <charconv>
#include <chrono>
#include <iostream>
#include <string>
#include <string_view>
#include <vector>

using namespace csl;
using namespace csl::reachability::finite_feedback;
using namespace csl::registry;

namespace {
struct Fixture {
    std::string name;
    Request request;
    std::vector<std::vector<bool>> expected_winning;
    std::vector<ActionIndex> expected_initial_actions;
    std::string expected_branch_actions;
};

std::vector<Fixture> fixtures() {
    return {
        {"clipping",{{"finite-report"},{"clipping"},
            Game{3,{Stage{{true,true,true},1,2,{
                {{StateIndex{1},StateIndex{2}}},
                {{StateIndex{1},StateIndex{1}}},
                {{StateIndex{1},StateIndex{1}}}
            }}},{true,true,true},{false,true,false}}},
            {{false,true,true},{false,true,false}}, {},""},
        {"branching",{{"finite-report"},{"branching"},
            Game{4,{
                Stage{{true,true,true,true},1,2,{
                    {{StateIndex{1},StateIndex{2}}},{{StateIndex{3},StateIndex{3}}},
                    {{StateIndex{3},StateIndex{3}}},{{StateIndex{3},StateIndex{3}}}
                }},
                Stage{{true,true,true,true},2,1,{
                    {{StateIndex{0}},{StateIndex{0}}},
                    {{StateIndex{3}},{StateIndex{0}}},
                    {{StateIndex{0}},{StateIndex{3}}},
                    {{StateIndex{0}},{StateIndex{0}}}
                }}
            },{true,true,true,true},{false,false,false,true}}},
            {{true,false,false,false},{false,true,true,false},{false,false,false,true}},
            {ActionIndex{0}},"1:0|2:1"},
        {"empty-action",{{"finite-report"},{"empty-action"},
            Game{2,{Stage{{true,true},0,1,{{},{}}}},{true,true},{false,true}}},
            {{false,false},{false,true}}, {},""},
        {"nominal",{{"finite-report"},{"nominal"},
            Game{2,{Stage{{true,true},1,1,{
                {{StateIndex{1}}},{{StateIndex{1}}}
            }}},{true,true},{false,true}}},
            {{true,true},{false,true}}, {ActionIndex{0}},""}
    };
}

std::string actions(const std::vector<ActionIndex>& values) {
    std::string result;
    for(const auto value:values) {
        if(!result.empty())result+='|';
        result+=std::to_string(value.value);
    }
    return result;
}

std::string branch_actions(const Policy& policy,const std::string& name) {
    if(name!="branching")return {};
    std::string result;
    for(const auto state:{1U,2U}) {
        if(!result.empty())result+='|';
        result+=std::to_string(state)+':';
        result+=actions(policy.admissible_actions[1][state]);
    }
    return result;
}

std::string diagnostic_code(DiagnosticCode code) {
    switch(code) {
    case DiagnosticCode::invalid_input:return "invalid_input";
    case DiagnosticCode::unsupported:return "unsupported";
    case DiagnosticCode::evidence_mismatch:return "evidence_mismatch";
    case DiagnosticCode::invalid_claim:return "invalid_claim";
    }
    return "unknown";
}

std::string stop_reason(StopReason reason) {
    switch(reason) {
    case StopReason::cancelled:return "cancelled";
    case StopReason::deadline_expired:return "deadline_expired";
    case StopReason::resource_limit:return "resource_limit";
    case StopReason::numerical_failure:return "numerical_failure";
    }
    return "unknown";
}

bool run_case(const Fixture& fixture,std::string_view purpose,std::size_t repetition) {
    const auto started=std::chrono::steady_clock::now();
    Registry<FiniteFeedbackPort> registry;
    const auto registration=registry.add(make_registration());
    RegisteredOutcome result=registration
        ? RegisteredFailure{fixture.request.problem,fixture.request.request,
            registration->provenance,registration->diagnostics}
        : run_registered(registry,
            {{"csl.reachability.finite-feedback-table"},"1.0.0"},
            fixture.request,finite_table_requirements(),{});
    bool matched=false;
    std::string initial_winning,initial_actions,branches,provider_id,provider_version,detail;
    if(const auto* completed=std::get_if<RegisteredPolicy>(&result)) {
        if(completed->provider.actual) {
            provider_id=completed->provider.actual->id.value;
            provider_version=completed->provider.actual->version;
        }
        const auto& policy=completed->policy;
        initial_winning=policy.winning[0][0]?"1":"0";
        initial_actions=actions(policy.admissible_actions[0][0]);
        branches=branch_actions(policy,fixture.name);
        matched=completed->problem==fixture.request.problem &&
            completed->request==fixture.request.request &&
            provider_id=="csl.reachability.finite-feedback-table" &&
            provider_version=="1.0.0" &&
            policy.winning==fixture.expected_winning &&
            policy.admissible_actions[0][0]==fixture.expected_initial_actions &&
            branches==fixture.expected_branch_actions;
    } else if(const auto* failure=std::get_if<RegisteredFailure>(&result)) {
        if(failure->provider.actual) {
            provider_id=failure->provider.actual->id.value;
            provider_version=failure->provider.actual->version;
        }
        for(const auto& diagnostic:failure->diagnostics) {
            if(!detail.empty())detail+='|';
            detail+=diagnostic_code(diagnostic.code)+":"+diagnostic.field;
        }
    } else if(const auto* stopped=std::get_if<RegisteredStopped>(&result)) {
        if(stopped->provider.actual) {
            provider_id=stopped->provider.actual->id.value;
            provider_version=stopped->provider.actual->version;
        }
        detail="stopped:"+stop_reason(stopped->stop.reason);
    }
    if(!matched && detail.empty())detail="oracle_mismatch";
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now()-started).count();
    std::cout<<purpose<<','<<fixture.name<<','<<repetition<<','
        <<(matched?"passed":"failed")<<','<<initial_winning<<','
        <<initial_actions<<','<<branches<<','<<elapsed<<','
        <<provider_id<<','<<provider_version<<','<<detail<<'\n';
    return matched;
}

int run(std::string_view mode,std::size_t repetitions) {
    const auto cases=fixtures();
    std::cout<<"purpose,scenario,repetition,status,initial_winning,initial_actions,"
        "branch_actions,elapsed_ns,provider_id,provider_version,detail\n";
    bool passed=true;
    if(mode=="--smoke") {
        for(const auto& fixture:cases)passed=run_case(fixture,"smoke",0)&&passed;
    } else {
        for(const auto& fixture:cases)passed=run_case(fixture,"warmup",0)&&passed;
        for(std::size_t repetition=0;repetition<repetitions;++repetition)
            for(std::size_t index=0;index<cases.size();++index)
                passed=run_case(cases[(index+repetition)%cases.size()],"trial",repetition)&&passed;
    }
    return passed?0:1;
}
}

int main(int argc,char** argv) {
    if(argc==2 && std::string_view(argv[1])=="--smoke")return run("--smoke",1);
    if(argc==3 && std::string_view(argv[1])=="--measure") {
        std::size_t repetitions=0;
        const std::string_view value(argv[2]);
        const auto parsed=std::from_chars(value.data(),value.data()+value.size(),repetitions);
        if(parsed.ec==std::errc{} && parsed.ptr==value.data()+value.size() &&
                repetitions>=5 && repetitions<=1000)
            return run("--measure",repetitions);
    }
    std::cerr<<"usage: csl_finite_feedback_report --smoke | --measure REPETITIONS(5..1000)\n";
    return 2;
}
