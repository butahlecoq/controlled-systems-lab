#include <csl/synthesis/hybrid_admission.hpp>
#include <type_traits>

int main() {
    static_assert(!std::is_copy_constructible_v<csl::synthesis::HybridAdmissionToken>);
    csl::synthesis::ProjectedStateHybridReachabilityAdapter adapter{64};
    const auto capabilities=adapter.capabilities();
    if(!capabilities.retains_branch_labelled_joint_relation ||
       capabilities.assurance!=csl::Assurance::numerical || !capabilities.projects_terminal_state)
        return 1;

    csl::synthesis::HybridExecutionSelection selection;
    selection.reachability=std::make_shared<csl::synthesis::JointHReachabilityAdapter>();
    const csl::model::HybridSystem system{0,{},{}};
    const csl::model::HybridRequest request{{{"missing"},{}},{{"missing"}},{}};
    const auto admission=csl::synthesis::admit_hybrid_request(system,request,selection,
        {0,1},{1,1,1},{},{});
    return std::holds_alternative<csl::synthesis::HybridAdmissionRefused>(admission)?0:1;
}
