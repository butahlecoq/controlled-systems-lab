#include <csl/reachability/finite_feedback.hpp>
#include <string>
#include <utility>

namespace csl::reachability::finite_feedback {
namespace {
Diagnostic invalid(std::string field,std::string explanation) {
    return {DiagnosticCode::invalid_input,std::move(field),std::move(explanation)};
}
}

Result solve(const Game& game) {
    const auto n=game.state_count;
    if(n==0)return invalid("feedback.state_count","At least one state is required.");
    if(game.terminal_safe.size()!=n || game.terminal_target.size()!=n)
        return invalid("feedback.terminal","Terminal safe and target masks must cover every state.");
    for(const auto& stage:game.stages) {
        if(stage.safe_states.size()!=n || stage.next_state.size()!=n)
            return invalid("feedback.stage","Every stage must cover every state.");
        if(stage.disturbance_count==0)
            return invalid("feedback.disturbances","The disturbance domain must be nonempty.");
        for(const auto& actions:stage.next_state) {
            if(actions.size()!=stage.action_count)
                return invalid("feedback.actions","Every state must use the same ordered action catalogue.");
            for(const auto& successors:actions) {
                if(successors.size()!=stage.disturbance_count)
                    return invalid("feedback.disturbances","Every action needs one successor per disturbance.");
                for(const auto successor:successors)
                    if(successor.value>=n)
                        return invalid("feedback.successor","Successor state index is out of range.");
            }
        }
    }
    Policy result;
    const auto horizon=game.stages.size();
    result.winning.resize(horizon+1,std::vector<bool>(n));
    result.admissible_actions.resize(horizon,std::vector<std::vector<ActionIndex>>(n));
    for(std::size_t state=0;state<n;++state)
        result.winning[horizon][state]=game.terminal_safe[state] && game.terminal_target[state];
    for(std::size_t t=horizon;t>0;--t) {
        const auto& stage=game.stages[t-1];
        for(std::size_t state=0;state<n;++state) {
            if(!stage.safe_states[state])continue;
            auto& actions=result.admissible_actions[t-1][state];
            for(std::size_t action=0;action<stage.action_count;++action) {
                bool feasible=true;
                for(const auto next:stage.next_state[state][action]) {
                    if(!result.winning[t][next.value]) { feasible=false; break; }
                }
                if(feasible)actions.push_back(ActionIndex{action});
            }
            result.winning[t-1][state]=!actions.empty();
        }
    }
    return result;
}

} // namespace csl::reachability::finite_feedback
