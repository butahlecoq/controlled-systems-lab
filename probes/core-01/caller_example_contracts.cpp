// Isolated CORE-01 probe: exercise only contracts; the product caller resolves
// problems and runs preparation through the linked product modules.
#include <csl/contracts.hpp>
#include <iostream>
#include <stdexcept>

namespace {
class FixtureWorkspace final : public csl::SynthesisWorkspace {
public:
    csl::SynthesisResult solve(const csl::problem::ResolvedProblem&, const csl::FamilyRequest&,
        const csl::ExecutionContext&) override {
        throw std::logic_error("Unsupported contract fixture has no executable solve");
    }
};
}

int main() {
    using namespace csl;
    const LinearStage stage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}};
    const Problem problem{{"core01/contract-probe"},
        std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,stage},{}}),
        {0,1},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1}}},
        {UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,
        LinearTerminal{{1},0}};
    if (!check_nominal_profile(problem,false,Assurance::numerical).empty()) return 1;
    if (!check_resources(ResourcePolicy{2,2,1,{}}).empty()) return 2;
    FixtureWorkspace first,second;
    if (&first==&second) return 3;
    std::cout << "Two exclusive contract workspaces exist; no solve was run.\n";
}
