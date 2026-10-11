#include <csl/execution/executor.hpp>
#include <atomic>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;
namespace reg=csl::registry;
namespace ex=csl::execution;
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
struct Answer { double x,value; int calls; };
struct Workspace:ExclusiveWorkspace { int calls{}; };
struct IntervalPort {
    using Request=double;using Workspace=::Workspace;
    static constexpr const char* name="installed-interval";
    static double snapshot(double coefficient){return coefficient;}
    static Answer run(Workspace& workspace,double coefficient,const ExecutionContext&) {
        const double x=coefficient<0?4:-1;
        return {x,std::fma(coefficient,x,2),++workspace.calls};
    }
};
using Task=ex::Task<IntervalPort>;
Task prepare(std::string id,double coefficient) {
    reg::Registry<IntervalPort> registry;
    require(!registry.add({{{"interval"},"1"},[](double,const reg::Requirements&)->reg::Capability{return reg::Offer{};},
        [](double){return std::make_unique<Workspace>();}}),"registration failed");
    auto prepared=std::get<reg::PreparedPipeline<IntervalPort>>(reg::prepare_pipeline(reg::select(registry,{{"interval"},{}},coefficient)));
    auto task=std::get<Task>(ex::make_task(ex::TaskId{std::move(id)},prepared,{1,"one caller lane",0,ex::CallStopSupport::noninterruptible}));
    coefficient=900;
    return task;
}
}
int main() try {
    auto executor=std::get<std::unique_ptr<ex::Executor>>(ex::make_executor({2,2,1,{}}));
    std::vector<Task> tasks{prepare("positive",3),prepare("negative",-2)};
    ExecutionContext context{executor->resources(),{},{},{1e-12,1e-12},"installed-execution"};
    for(auto mode:{ex::Mode::sequential,ex::Mode::bounded_parallel}) {
        auto batch=std::get<ex::BatchResult<IntervalPort>>(executor->run<IntervalPort>(tasks,context,mode));
        require(batch.tasks.size()==2,"lost tasks");
        require(batch.tasks[0].id.value=="positive"&&batch.tasks[1].id.value=="negative","unstable task order");
        auto positive=std::get<ex::Returned<IntervalPort>>(batch.tasks[0].outcome).value;
        auto negative=std::get<ex::Returned<IntervalPort>>(batch.tasks[1].outcome).value;
        require(positive.x==-1&&positive.value==-1&&negative.x==4&&negative.value==-6,"literal interval optimum mismatch");
        require(positive.calls==1&&negative.calls==1,"workspace was reused across tasks or batches");
        require(batch.tasks[0].provenance[0].actual->version=="1","lost retained provenance");
        require(batch.enforcement.native_threads==ex::NativeThreadEnforcement::declared_only,"native enforcement claim changed");
        require(batch.timing.workers_joined_at<=batch.timing.completed_at,"returned before cleanup");
    }
    std::cout<<"Installed execution client: retained analytic tasks, isolated modes and literal outcomes passed\n";
    return 0;
} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
