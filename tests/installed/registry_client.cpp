#include <csl/registry/registry.hpp>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;
using namespace csl::registry;
void require(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}
class Workspace : public ExclusiveWorkspace {
public: virtual int evaluate(int) = 0;
};
struct FixturePort {
    using Request = int;
    using Workspace = ::Workspace;
    static constexpr const char* name = "installed-fixture";
    static int snapshot(int r) { return r; }
    static int run(Workspace& w,int r,const ExecutionContext&) { return w.evaluate(r); }
};
class Fixture final : public Workspace {
    int calls_{};
public: int evaluate(int r) override { return r + ++calls_; }
};
}
int main() try {
    auto plan = [] {
        Registry<FixturePort> registry;
        require(!registry.add({{{"fixture"},"1"},[](int,const Requirements&) -> Capability { return Offer{}; },
            [](int) { return std::make_unique<Fixture>(); }}),"registration failed");
        int request = 41;
        Requirements invalid; invalid.scalar = Scalar::exact;
        auto rejected = prepare_pipeline(select(registry,Method{{"fixture"},{}},request,invalid));
        require(std::holds_alternative<Rejection>(rejected),"exact scalar must reject");
        require(std::get<Rejection>(rejected).provenance.actual->version == "1","resolved version missing");
        auto result = prepare_pipeline(select(registry,Method{{"fixture"},{}},request));
        require(std::holds_alternative<PreparedPipeline<FixturePort>>(result),"preparation failed");
        request = 900;
        return std::get<PreparedPipeline<FixturePort>>(std::move(result));
    }();
    auto first = plan.create(), second = plan.create();
    const ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"installed"};
    require(std::get<0>(first)->run(context)==42,"snapshot source lifetime failed");
    require(std::get<0>(first)->run(context)==43,"workspace mutation failed");
    require(std::get<0>(second)->run(context)==42,"workspaces share mutable state");
    std::cout << "Installed registry client: retained custom-port fixture and exclusive workspaces passed\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
}
