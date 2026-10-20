#include <csl/synthesis/hybrid_path_program.hpp>

int main() {
    csl::synthesis::ProjectedStateHybridReachabilityAdapter adapter{64};
    csl::synthesis::GeneralProjectedStateHybridReachabilityAdapter general_adapter{128};
    const auto capabilities=adapter.capabilities();
    const auto general_capabilities=general_adapter.capabilities();
    return capabilities.retains_branch_labelled_joint_relation &&
        capabilities.assurance==csl::Assurance::numerical &&
        general_capabilities.retains_branch_labelled_joint_relation &&
        general_capabilities.assurance==csl::Assurance::numerical ? 0 : 1;
}
