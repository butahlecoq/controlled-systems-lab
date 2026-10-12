#include <csl/registry/provider.hpp>
#include <csl/optimization/linear_program.hpp>
#include <iostream>

namespace {
using namespace csl;
using namespace csl::registry;
class IntervalWorkspace final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
        const double x=p.objective()[0]<0?*p.variables()[0].upper:*p.variables()[0].lower;
        return ProgramResult{Termination::completed,{p.identity(),MathematicalOutcome::optimal,
            SymbolicArgument{"affine interval endpoint","finite interval"},{}},Vector{x},{},{}};
    }
};
PreparedProvider<LPPort> make_provider() {
    Registry<LPPort> registry;
    const auto offset=std::make_shared<const double>(0.0);
    registry.add({{{"installed-interval"},"1"},[](const LinearProgram& p,const Requirements&)->Capability{
        if(p.objective().size()!=1||p.constraints().rows()!=0||!p.variables()[0].lower||!p.variables()[0].upper)
            return Diagnostics{{DiagnosticCode::unsupported,"domain","finite interval required"}};
        return Offer{};
    },[offset](const LinearProgram&){(void)offset;return std::make_unique<IntervalWorkspace>();}});
    return std::get<PreparedProvider<LPPort>>(prepare_provider(select_provider(registry,Method{{"installed-interval"},"1"})));
}
}
int main() {
    auto provider=make_provider();
    csl::ExecutionContext context{std::make_shared<const csl::ResourcePolicy>(csl::ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"installed-provider"};
    for(double coefficient:{1.0,-1.0}) {
        auto plan=[&]{
            csl::LinearProgramInput input{{{"problem"},{"generated"}},{coefficient},0,{0,1,{0},{},{}},{{-2,3}},{}};
            const auto program=std::get<csl::LinearProgram>(csl::optimization::make_linear_program(input));
            return std::get<csl::registry::PreparedPipeline<csl::registry::LPPort>>(provider.prepare(program));
        }();
        const auto workers=plan.create();
        const auto answer=std::get<csl::ProgramResult>(std::get<0>(workers)->run(context));
        if(answer.primal!=std::optional<csl::Vector>{{coefficient>0?-2.0:3.0}})return 1;
        if(plan.provenance()[0].actual->id.value!="installed-interval")return 2;
    }
    std::cout<<"Installed provider client: frozen method and changing owned requests passed\n";
}
