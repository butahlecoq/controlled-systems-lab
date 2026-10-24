#include <csl/experiments/batch_runner.hpp>

#include <algorithm>
#include <cmath>
#include <string>

namespace csl::experiments {
namespace {
bool valid_identity(const ScenarioConfigurationId& identity) {
    return !identity.scenario.empty() && !identity.configuration.value.empty();
}

bool valid_selection(const SelectionSettings& settings) {
    return settings.count > 0 && std::isfinite(settings.distinctness_tolerance) &&
        settings.distinctness_tolerance >= 0.0 &&
        std::all_of(settings.directions.begin(), settings.directions.end(), [](const Vector& direction) {
            return std::all_of(direction.begin(), direction.end(), [](double value) {
                return std::isfinite(value);
            });
        });
}
}

SweepOutcome run_sweep(std::span<const ScenarioSweepCase> cases, const ResourcePolicy& resources,
    const ExecutionContext& context, execution::Mode mode, execution::AdmissionLimit limit) {
    std::vector<execution::Task<registry::StrategyPort>> tasks;
    std::vector<SweepCaseRecord> records;
    tasks.reserve(cases.size());
    records.reserve(cases.size());

    for (std::size_t index = 0; index < cases.size(); ++index) {
        const auto& item = cases[index];
        if (!valid_identity(item.identity))
            return Diagnostics{{DiagnosticCode::invalid_input, "sweep.cases[" + std::to_string(index) + "].identity",
                "Scenario and configuration IDs must be nonempty."}};
        if (!valid_selection(item.selection))
            return Diagnostics{{DiagnosticCode::invalid_input, "sweep.cases[" + std::to_string(index) + "].selection",
                "Witness count must be positive and selection values must be finite and nonnegative."}};

        auto task = execution::make_task(execution::TaskId{"sweep-" + std::to_string(index)},
            item.strategy, item.resources);
        if (auto* diagnostic = std::get_if<Diagnostic>(&task)) return Diagnostics{*diagnostic};
        tasks.push_back(std::get<execution::Task<registry::StrategyPort>>(std::move(task)));
        records.push_back({item.identity, std::make_shared<const SelectionSettings>(item.selection)});
    }

    auto executor = execution::make_executor(resources);
    if (auto* diagnostics = std::get_if<Diagnostics>(&executor)) return *diagnostics;
    auto owned_executor=std::get<std::unique_ptr<execution::Executor>>(std::move(executor));
    auto effective_context=context;
    // Executor requires every worker to retain its own immutable policy owner.
    // Bind it here so callers cannot accidentally supply a parallel policy copy.
    effective_context.resources=owned_executor->resources();
    auto outcome=owned_executor->run<registry::StrategyPort>(tasks,effective_context,mode,limit);
    if (auto* diagnostics = std::get_if<Diagnostics>(&outcome)) return *diagnostics;
    return SweepResult{std::get<execution::BatchResult<registry::StrategyPort>>(std::move(outcome)),
        std::move(records)};
}

} // namespace csl::experiments
