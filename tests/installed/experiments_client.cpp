#include <csl/experiments/batch_runner.hpp>

#include <iostream>
#include <stdexcept>

int main() {
    const csl::ResourcePolicy resources{1,1,1,std::nullopt};
    csl::ExecutionContext context;
    context.run_id="installed-empty-sweep";
    const auto outcome=csl::experiments::run_sweep({},resources,context,
        csl::execution::Mode::sequential);
    const auto* result=std::get_if<csl::experiments::SweepResult>(&outcome);
    if(!result||!result->batch.tasks.empty()||!result->cases.empty())
        throw std::runtime_error("Installed sweep API did not retain an empty plan");
    std::cout<<"Installed experiments client: public batch runner passed\n";
}
