#include <csl/experiments/batch_runner.hpp>

#include <algorithm>
#include <cmath>
#include <string>

namespace csl::experiments {
namespace {
bool valid_identity(const ScenarioConfigurationId& identity) {
    return !identity.scenario.value.empty() && !identity.configuration.value.empty();
}

bool same_resources(const ResourcePolicy& left, const ResourcePolicy& right) {
    return left.total_threads == right.total_threads && left.outer_workers == right.outer_workers &&
        left.threads_per_worker == right.threads_per_worker && left.memory_bytes == right.memory_bytes;
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

FamilyQueryOutcome run_family_queries(SweepResult&& coarse,
    const registry::PreparedProvider<registry::SelectorPort>& selector,
    const ResourcePolicy& resources, const ExecutionContext& context, execution::Mode mode,
    const execution::ResourceUse& query_resources, execution::AdmissionLimit limit) {
    if (coarse.batch.tasks.size() != coarse.cases.size())
        return Diagnostics{{DiagnosticCode::invalid_input, "family_queries.alignment",
            "Coarse task and case records must have the same size."}};
    if (coarse.batch.run_id != context.run_id)
        return Diagnostics{{DiagnosticCode::invalid_input, "family_queries.run_id",
            "The query context must retain the coarse run ID."}};
    if (!(coarse.batch.numerical == context.numerical))
        return Diagnostics{{DiagnosticCode::invalid_input, "family_queries.numerical",
            "The query context must retain the coarse numerical policy."}};
    if (!coarse.batch.resources || !same_resources(*coarse.batch.resources, resources))
        return Diagnostics{{DiagnosticCode::invalid_input, "family_queries.resources",
            "The query phase must use the coarse run's resource policy."}};

    std::vector<execution::Task<registry::SelectorPort>> tasks;
    std::vector<FamilyQueryRecord> records;
    tasks.reserve(coarse.cases.size());
    records.reserve(coarse.cases.size());

    for (std::size_t index = 0; index < coarse.cases.size(); ++index) {
        const auto& item = coarse.cases[index];
        if (!valid_identity(item.identity))
            return Diagnostics{{DiagnosticCode::invalid_input,
                "family_queries.cases[" + std::to_string(index) + "].identity",
                "Scenario and configuration IDs must be nonempty."}};
        if (!item.selection)
            return Diagnostics{{DiagnosticCode::invalid_input,
                "family_queries.cases[" + std::to_string(index) + "].selection",
                "Selection settings must be retained with every coarse case."}};

        const auto& strategy_outcome = coarse.batch.tasks[index].outcome;
        if (std::holds_alternative<execution::Skipped>(strategy_outcome)) {
            records.push_back({item.identity, FamilyQueryNotRun{QueryNotRunReason::strategy_skipped}});
            continue;
        }
        if (std::holds_alternative<execution::TaskFailure>(strategy_outcome)) {
            records.push_back({item.identity, FamilyQueryNotRun{QueryNotRunReason::strategy_failed}});
            continue;
        }

        const auto& synthesis = std::get<execution::Returned<registry::StrategyPort>>(strategy_outcome).value;
        const auto* result = std::get_if<SynthesisResult>(&synthesis);
        if (!result) {
            records.push_back({item.identity, FamilyQueryNotRun{QueryNotRunReason::strategy_unsupported}});
            continue;
        }
        if (!result->family) {
            records.push_back({item.identity, FamilyQueryNotRun{QueryNotRunReason::family_unavailable}});
            continue;
        }

        const auto& settings = *item.selection;
        registry::SelectorRequest request{*result->family,
            WitnessRequest{settings.count, settings.distinctness_tolerance, settings.directions, settings.seed}};
        auto prepared_result = selector.prepare(request);
        if (const auto* rejection = std::get_if<registry::Rejection>(&prepared_result)) {
            records.push_back({item.identity, FamilyQueryRejected{rejection->diagnostics}});
            continue;
        }

        const auto task_index = tasks.size();
        auto task = execution::make_task(execution::TaskId{"family-query-" + std::to_string(index)},
            std::get<registry::PreparedPipeline<registry::SelectorPort>>(std::move(prepared_result)),
            query_resources);
        if (const auto* diagnostic = std::get_if<Diagnostic>(&task)) return Diagnostics{*diagnostic};
        tasks.push_back(std::get<execution::Task<registry::SelectorPort>>(std::move(task)));
        records.push_back({item.identity, FamilyQueryScheduled{task_index}});
    }

    auto executor_result = execution::make_executor(resources);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&executor_result)) return *diagnostics;
    auto executor = std::get<std::unique_ptr<execution::Executor>>(std::move(executor_result));
    auto effective_context = context;
    effective_context.resources = executor->resources();
    auto query_result = executor->run<registry::SelectorPort>(tasks, effective_context, mode, limit);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&query_result)) return *diagnostics;

    return FamilyQueryResult{std::move(coarse), std::move(records),
        std::get<execution::BatchResult<registry::SelectorPort>>(std::move(query_result))};
}

} // namespace csl::experiments
