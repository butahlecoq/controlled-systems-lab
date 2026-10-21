#include <csl/synthesis/hybrid_path_program.hpp>

int main() {
    csl::synthesis::ProjectedStateHybridReachabilityAdapter adapter{64};
    const auto capabilities=adapter.capabilities();
    return capabilities.retains_branch_labelled_joint_relation &&
        capabilities.assurance==csl::Assurance::numerical ? 0 : 1;
}
