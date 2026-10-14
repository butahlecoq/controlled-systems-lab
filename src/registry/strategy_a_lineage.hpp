#pragma once

#include <csl/contracts.hpp>

namespace csl::synthesis::strategy_a::detail {

inline std::string forward_child(const ProblemId& problem,const RequestId& request,
    std::size_t stage,const std::string& suffix) {
    const auto field=[](const std::string& value){return std::to_string(value.size())+":"+value;};
    return "nominal-forward/"+field(problem.value)+field(request.value)+std::to_string(stage)+suffix;
}
inline std::string recovery_output(const ProblemId& problem,const SetId& terminal) {
    const auto field=[](const std::string& value){return std::to_string(value.size())+":"+value;};
    return "recovery/joint-history/"+field(problem.value)+field(terminal.value);
}
inline std::vector<TransformStepIdentity> expected_ts01_lineage(const ProblemId& problem) {
    const ModuleId strategy{"csl.synthesis.reach-back"};
    const std::string version="1";
    const RequestId forward{"strategy-a/forward"};
    std::vector<TransformStepIdentity> lineage;
    std::vector<SetId> reachable;
    reachable.reserve(3);
    for(std::size_t stage=0;stage<=2;++stage) {
        const SetId output{forward_child(problem,forward,stage,"/project/output")};
        const SetId input=stage==0?SetId{forward_child(problem,forward,0,"/initial")}:reachable.back();
        lineage.push_back({{forward_child(problem,forward,stage,"/stage")},input,output,strategy,version});
        reachable.push_back(output);
    }
    const auto& final_slice=reachable.back();
    const SetId feasible_history{recovery_output(problem,final_slice)};
    const RequestId terminal_request{"syn02-terminal:"+final_slice.value};
    const SetId terminal_relation{final_slice.value+":terminal-candidate"};
    const SetId optimal_history{recovery_output(problem,terminal_relation)};
    lineage.push_back({{"strategy-a/feasible-preimage"},final_slice,feasible_history,{"csl.synthesis.control-recovery"},"1"});
    lineage.push_back({terminal_request,final_slice,terminal_relation,{"csl.synthesis.terminal-minimizers"},"1"});
    lineage.push_back({{"strategy-a/terminal-preimage"},terminal_relation,optimal_history,{"csl.synthesis.control-recovery"},"1"});
    return lineage;
}
inline std::vector<TransformStepIdentity> expected_ts02_lineage(const ProblemId& problem) {
    // T-S02 currently executes the same six deterministic reach-back steps as
    // T-S01. The immutable FamilyRequest profile/objective distinguishes the
    // proof authority; only this expected-lineage name is profile-specific.
    return expected_ts01_lineage(problem);
}

} // namespace csl::synthesis::strategy_a::detail
