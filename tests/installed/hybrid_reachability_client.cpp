#include <csl/synthesis/hybrid_path_program.hpp>

#include <variant>
#include <vector>

int main() {
    csl::synthesis::ProjectedStateHybridReachabilityAdapter adapter{64};
    csl::synthesis::GeneralProjectedStateHybridReachabilityAdapter general_adapter{128};
    const auto capabilities=adapter.capabilities();
    const auto general_capabilities=general_adapter.capabilities();
    if(!(capabilities.retains_branch_labelled_joint_relation &&
        capabilities.assurance==csl::Assurance::numerical &&
        general_capabilities.retains_branch_labelled_joint_relation &&
        general_capabilities.assurance==csl::Assurance::numerical)) return 1;

    const csl::model::HybridMode terminal{{"terminal"},1,0,{"x"},{},
        csl::LinearStage{csl::Matrix{1,1,{1}},csl::Matrix{1,0,{}},
            csl::Matrix{1,0,{}},csl::Vector{0}}, {}, {csl::UniversalSet{1}}};
    const csl::model::HybridSystem system{0,{terminal},{}};
    const csl::model::HybridRequest request{{{"terminal"},{2}},{{"terminal"}},
        {{{"terminal"},csl::LinearTerminal{{0},0},"constant","units"}}};
    csl::synthesis::JointHReachabilityAdapter joint_adapter;
    const auto reachability=csl::synthesis::compute_hybrid_reachability_portfolio(
        joint_adapter,system,request,{0,1},{1,4,16});
    const auto* portfolio=std::get_if<csl::synthesis::HybridReachabilityPortfolio>(&reachability);
    if(!portfolio || portfolio->branches.size()!=1 ||
       portfolio->branches.front().path.modes!=std::vector<csl::model::HybridModeId>{{"terminal"}} ||
       portfolio->branches.front().joint_relation.metadata()->set.dimension!=1 ||
       portfolio->operation_resources.empty()) return 2;
    return 0;
}
