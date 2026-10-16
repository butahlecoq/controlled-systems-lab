#include <csl/reachability/finite_feedback_port.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::reachability::finite_feedback;
    using namespace csl::registry;
    Registry<FiniteFeedbackPort> registry;
    if(registry.add(make_registration()))return 1;
    const Request request{{"installed-finite"},{"winning"},
        Game{2,{Stage{{true,true},1,1,{
            {{StateIndex{1}}},{{StateIndex{1}}}
        }}},{true,true},{false,true}}};
    const auto result=run_registered(registry,
        {{"csl.reachability.finite-feedback-table"},"1.0.0"},
        request,finite_table_requirements(),{});
    if(!std::holds_alternative<RegisteredPolicy>(result))return 2;
    const auto& completed=std::get<RegisteredPolicy>(result);
    if(completed.problem!=ProblemId{"installed-finite"} ||
            completed.request!=RequestId{"winning"} ||
            !completed.provider.actual ||
            completed.provider.actual->version!="1.0.0" ||
            completed.policy.winning[0]!=std::vector<bool>{true,true} ||
            completed.policy.admissible_actions[0][0]!=std::vector<ActionIndex>{ActionIndex{0}})
        return 3;
    std::cout<<"Installed finite feedback client: registered winning action passed\n";
}
