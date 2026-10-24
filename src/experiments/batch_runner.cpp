#include <csl/experiments/batch_runner.hpp>

#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <unordered_set>

namespace csl::experiments {
namespace {
using Json = nlohmann::json;

bool valid_identity(const ScenarioConfigurationId& identity) {
    return !identity.scenario.value.empty() && !identity.configuration.value.empty();
}

std::string_view termination_name(Termination value) {
    switch (value) {
    case Termination::completed: return "completed";
    case Termination::cancelled: return "cancelled";
    case Termination::resource_limit: return "resource_limit";
    case Termination::numerical_failure: return "numerical_failure";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    }
    return {};
}

std::string_view outcome_name(MathematicalOutcome value) {
    switch (value) {
    case MathematicalOutcome::optimal: return "optimal";
    case MathematicalOutcome::infeasible: return "infeasible";
    case MathematicalOutcome::unbounded: return "unbounded";
    case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
    case MathematicalOutcome::undetermined: return "undetermined";
    }
    return {};
}

std::string_view skip_reason_name(execution::SkipReason value) {
    switch (value) {
    case execution::SkipReason::cancelled: return "cancelled";
    case execution::SkipReason::deadline: return "deadline";
    case execution::SkipReason::task_limit: return "task_limit";
    case execution::SkipReason::reservation_exceeds_budget: return "reservation_exceeds_budget";
    case execution::SkipReason::batch_failed: return "batch_failed";
    }
    return {};
}

std::string_view failure_phase_name(execution::FailureStage value) {
    switch (value) {
    case execution::FailureStage::create: return "create";
    case execution::FailureStage::invoke: return "invoke";
    }
    return {};
}

std::string_view failure_reason_name(execution::FailureKind value) {
    switch (value) {
    case execution::FailureKind::allocation: return "allocation";
    case execution::FailureKind::adapter_exception: return "adapter_exception";
    }
    return {};
}

bool same_bound(const Json& json, const std::optional<ObjectiveBound>& bound) {
    if (!bound) return json.is_null();
    return json.is_object() && json.contains("value") && json.at("value").is_number() &&
        json.at("value").get<double>() == bound->value;
}

bool recorded_run_matches(const artifacts::RecordedRunArtifact& artifact,
    const execution::TaskOutcome<registry::StrategyPort>& actual) {
    try {
        std::string text;
        const auto bytes = artifact.content().bytes();
        text.reserve(bytes.size());
        for (const auto byte : bytes) text.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
        if (std::holds_alternative<artifacts::ArtifactError>(artifacts::decode_recorded_run(text))) return false;
        const auto run = Json::parse(text);
        const auto& final = run.at("final");
        const auto kind = final.at("kind").get<std::string>();
        if (const auto* skipped = std::get_if<execution::Skipped>(&actual))
            return kind == "skipped" && run.at("selection").is_null() &&
                final.at("value").at("reason").get<std::string>() == skip_reason_name(skipped->reason);
        if (const auto* failed = std::get_if<execution::TaskFailure>(&actual))
            return kind == "failed" && run.at("selection").is_null() &&
                final.at("value").at("phase").get<std::string>() == failure_phase_name(failed->stage) &&
                final.at("value").at("reason").get<std::string>() == failure_reason_name(failed->kind);

        const auto& returned = std::get<execution::Returned<registry::StrategyPort>>(actual).value;
        if (std::holds_alternative<Unsupported>(returned)) {
            return kind == "unsupported";
        }
        const auto* synthesis = std::get_if<SynthesisResult>(&returned);
        if (!synthesis || kind != "synthesis") return false;
        const auto& value = final.at("value");
        if (value.at("termination").get<std::string>() != termination_name(synthesis->termination) ||
            value.at("outcome").at("value").get<std::string>() != outcome_name(synthesis->outcome.value) ||
            !same_bound(value.at("objective").at("lower"), synthesis->objective.lower) ||
            !same_bound(value.at("objective").at("upper"), synthesis->objective.upper))
            return false;
        return value.at("family").is_null() == !synthesis->family.has_value();
    } catch (const std::exception&) {
        return false;
    }
}

std::string_view diagnostic_name(DiagnosticCode value) {
    switch (value) {
    case DiagnosticCode::invalid_input: return "invalid_input";
    case DiagnosticCode::unsupported: return "unsupported";
    case DiagnosticCode::evidence_mismatch: return "evidence_mismatch";
    case DiagnosticCode::invalid_claim: return "invalid_claim";
    }
    return {};
}

std::string_view family_target_name(FamilyTarget value) {
    switch (value) {
    case FamilyTarget::exact_optimal_relation: return "exact_optimal_relation";
    case FamilyTarget::candidate_relaxation: return "candidate_relaxation";
    case FamilyTarget::partial_relation: return "partial_relation";
    }
    return {};
}

std::string_view assurance_name(Assurance value) {
    switch (value) {
    case Assurance::numerical: return "numerical";
    case Assurance::validated: return "validated";
    }
    return {};
}

Json family_identity_json(const FamilyIdentity& identity) {
    Json lineage = Json::array();
    for (const auto& step : identity.lineage) {
        lineage.push_back({{"request",step.request.value},{"input",step.input.value},
            {"output",step.output.value},{"module",step.module.value},{"version",step.version}});
    }
    const auto& request = identity.request;
    return {
        {"problem",identity.problem.value},
        {"request",{{"profile",request.profile},{"objective",request.objective.value},
            {"target",family_target_name(request.target)},
            {"numerical",{{"absolute_tolerance",request.numerical.absolute_tolerance},
                {"relative_tolerance",request.numerical.relative_tolerance}}},
            {"assurance",assurance_name(request.assurance)},
            {"representation",request.representation.value},
            {"materialization_limit",request.materialization_limit
                ? Json{std::to_string(*request.materialization_limit)} : Json{nullptr}}}},
        {"coordinates",{{"dimensions",{{"state",std::to_string(identity.coordinates.dimensions.state)},
            {"control",std::to_string(identity.coordinates.dimensions.control)},
            {"external",std::to_string(identity.coordinates.dimensions.external)}}},
            {"horizon",std::to_string(identity.coordinates.horizon)}}},
        {"strategy",identity.strategy.value},{"strategy_version",identity.strategy_version},
        {"lineage",std::move(lineage)}};
}

Json witness_json(const Witness& witness) {
    return {{"problem",witness.problem.value},{"states",witness.states},
        {"controls",witness.controls},{"original_objective",witness.original_objective}};
}

Json selection_json(const WitnessSelection& selection) {
    const auto& batch = selection.batch;
    Json witnesses = Json::array();
    for (const auto& witness : batch.witnesses) witnesses.push_back(witness_json(witness));
    return {{"batch",{{"witnesses",std::move(witnesses)},
        {"requested",std::to_string(batch.requested)},{"selector",batch.selector.value},
        {"seed",batch.seed ? Json{std::to_string(*batch.seed)} : Json{nullptr}},
        {"source_family",batch.source_family ? family_identity_json(*batch.source_family) : Json{nullptr}},
        {"directions",batch.directions},{"distinctness_tolerance",batch.distinctness_tolerance}}},
        {"termination",termination_name(selection.termination)},{"diagnostics",selection.diagnostics}};
}

bool recorded_query_matches(const artifacts::RecordedRunArtifact& artifact,
    const execution::TaskOutcome<registry::SelectorPort>& actual) {
    try {
        std::string text;
        const auto bytes = artifact.content().bytes();
        text.reserve(bytes.size());
        for (const auto byte : bytes) text.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
        if (std::holds_alternative<artifacts::ArtifactError>(artifacts::decode_recorded_run(text))) return false;
        const auto run = Json::parse(text);
        const auto& final = run.at("final");
        const auto kind = final.at("kind").get<std::string>();
        if (const auto* skipped = std::get_if<execution::Skipped>(&actual))
            return kind == "skipped" && run.at("selection").is_null() &&
                final.at("value").at("reason").get<std::string>() == skip_reason_name(skipped->reason);
        if (const auto* failed = std::get_if<execution::TaskFailure>(&actual))
            return kind == "failed" && run.at("selection").is_null() &&
                final.at("value").at("phase").get<std::string>() == failure_phase_name(failed->stage) &&
                final.at("value").at("reason").get<std::string>() == failure_reason_name(failed->kind);

        const auto& returned = std::get<execution::Returned<registry::SelectorPort>>(actual).value;
        if (const auto* unsupported = std::get_if<Unsupported>(&returned)) {
            if (kind != "unsupported" || !run.at("selection").is_null()) return false;
            Json expected = Json::array();
            for (const auto& diagnostic : unsupported->diagnostics)
                expected.push_back({{"code",diagnostic_name(diagnostic.code)},
                    {"field",diagnostic.field},{"explanation",diagnostic.explanation}});
            return final.at("value").at("diagnostics") == expected;
        }
        const auto* selection = std::get_if<WitnessSelection>(&returned);
        return selection && kind == "synthesis" && run.at("selection") == selection_json(*selection);
    } catch (const std::exception&) {
        return false;
    }
}

bool same_resources(const ResourcePolicy& left, const ResourcePolicy& right) {
    return left.total_threads == right.total_threads && left.outer_workers == right.outer_workers &&
        left.threads_per_worker == right.threads_per_worker && left.memory_bytes == right.memory_bytes;
}

bool add_reservation(std::size_t amount, std::size_t& total) {
    if (amount > std::numeric_limits<std::size_t>::max() - total) return false;
    total += amount;
    return true;
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

artifacts::ArtifactError artifact_error(artifacts::ArtifactErrorCode code,
    std::string path, std::string message) {
    return {code, std::move(path), std::move(message)};
}

template<class Port>
std::optional<artifacts::SweepPhaseResources> phase_resources(
    const execution::BatchResult<Port>& batch, const ResourcePolicy& requested,
    std::optional<std::size_t> retained_result_reservations) {
    if (!batch.resources) return {};
    const bool reservations_active = batch.enforcement.memory == execution::MemoryEnforcement::active_reservations_only;
    const auto memory_support = reservations_active
        ? retained_result_reservations
            ? artifacts::SweepMemorySupport::active_and_retained_reservations
            : artifacts::SweepMemorySupport::active_workspace_reservations
        : artifacts::SweepMemorySupport::unlimited_accounting;
    std::optional<std::uint64_t> workspace;
    if (batch.enforcement.peak_workspace_reservation_bytes)
        workspace = static_cast<std::uint64_t>(*batch.enforcement.peak_workspace_reservation_bytes);
    std::optional<std::uint64_t> retained;
    if (retained_result_reservations)
        retained = static_cast<std::uint64_t>(*retained_result_reservations);
    std::optional<std::uint64_t> enforced_memory;
    if (reservations_active && requested.memory_bytes)
        enforced_memory = static_cast<std::uint64_t>(*requested.memory_bytes);
    return artifacts::SweepPhaseResources{requested,
        static_cast<std::uint64_t>(batch.enforcement.outer_worker_threads_started),
        static_cast<std::uint64_t>(batch.enforcement.peak_active_tasks), {}, workspace, retained,
        enforced_memory, {}, memory_support,
        reservations_active ? "executor workspace and declared retained-result reservations" : ""};
}

std::optional<artifacts::SweepNotRunReason> not_run_reason(QueryNotRunReason reason) {
    switch (reason) {
    case QueryNotRunReason::strategy_skipped: return artifacts::SweepNotRunReason::strategy_skipped;
    case QueryNotRunReason::strategy_failed: return artifacts::SweepNotRunReason::strategy_failed;
    case QueryNotRunReason::strategy_unsupported: return artifacts::SweepNotRunReason::strategy_unsupported;
    case QueryNotRunReason::family_unavailable: return artifacts::SweepNotRunReason::family_unavailable;
    }
    return {};
}
}

SweepOutcome run_sweep(std::span<const ScenarioSweepCase> cases, const ResourcePolicy& resources,
    const ExecutionContext& context, execution::Mode mode, execution::AdmissionLimit limit) {
    std::size_t retained_result_reservations = 0;
    bool retained_result_reservations_known = true;
    for (std::size_t index = 0; index < cases.size(); ++index) {
        const auto& reservation = cases[index].resources.retained_result_reservation_bytes;
        if (!reservation) {
            retained_result_reservations_known = false;
            if (resources.memory_bytes)
                return Diagnostics{{DiagnosticCode::unsupported,
                    "sweep.cases[" + std::to_string(index) + "].retained_result_memory",
                    "A finite sweep memory budget requires a retained-result reservation for every case."}};
            continue;
        }
        if (!add_reservation(*reservation, retained_result_reservations))
            return Diagnostics{{DiagnosticCode::invalid_input, "sweep.retained_result_memory",
                "Retained-result reservations overflow the addressable size."}};
    }
    if (resources.memory_bytes && retained_result_reservations > *resources.memory_bytes)
        return Diagnostics{{DiagnosticCode::unsupported, "sweep.retained_result_memory",
            "Retained coarse results exceed the requested memory budget."}};

    auto active_resources = resources;
    if (active_resources.memory_bytes)
        active_resources.memory_bytes = *active_resources.memory_bytes - retained_result_reservations;
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

    auto executor = execution::make_executor(active_resources);
    if (auto* diagnostics = std::get_if<Diagnostics>(&executor)) return *diagnostics;
    auto owned_executor=std::get<std::unique_ptr<execution::Executor>>(std::move(executor));
    auto effective_context=context;
    // Executor requires every worker to retain its own immutable policy owner.
    // Bind it here so callers cannot accidentally supply a parallel policy copy.
    effective_context.resources=owned_executor->resources();
    auto outcome=owned_executor->run<registry::StrategyPort>(tasks,effective_context,mode,limit);
    if (auto* diagnostics = std::get_if<Diagnostics>(&outcome)) return *diagnostics;
    return SweepResult{std::get<execution::BatchResult<registry::StrategyPort>>(std::move(outcome)),
        std::move(records), resources, retained_result_reservations_known ?
            std::optional<std::size_t>{retained_result_reservations} : std::nullopt};
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
    if (!same_resources(coarse.requested_resources, resources))
        return Diagnostics{{DiagnosticCode::invalid_input, "family_queries.resources",
            "The query phase must use the coarse run's resource policy."}};
    if (resources.memory_bytes && !coarse.retained_result_reservation_bytes)
        return Diagnostics{{DiagnosticCode::unsupported, "family_queries.retained_result_memory",
            "A finite query memory budget requires retained coarse-result reservations."}};

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

    std::size_t query_result_reservations = 0;
    std::optional<std::size_t> query_result_reservation_total{0};
    if (!tasks.empty() && !query_resources.retained_result_reservation_bytes)
        query_result_reservation_total.reset();
    else if (query_resources.retained_result_reservation_bytes) {
        for (std::size_t index = 0; index < tasks.size(); ++index)
            if (!add_reservation(*query_resources.retained_result_reservation_bytes, query_result_reservations))
                return Diagnostics{{DiagnosticCode::invalid_input, "family_queries.retained_result_memory",
                    "Retained query-result reservations overflow the addressable size."}};
        query_result_reservation_total = query_result_reservations;
    }
    if (resources.memory_bytes && !query_result_reservation_total)
        return Diagnostics{{DiagnosticCode::unsupported, "family_queries.retained_result_memory",
            "A finite query memory budget requires a retained-result reservation for every scheduled query."}};

    auto active_resources = resources;
    if (active_resources.memory_bytes) {
        const auto coarse_retained = *coarse.retained_result_reservation_bytes;
        if (*query_result_reservation_total > *active_resources.memory_bytes - coarse_retained)
            return Diagnostics{{DiagnosticCode::unsupported, "family_queries.retained_result_memory",
                "Retained coarse and query results exceed the shared memory budget."}};
        active_resources.memory_bytes = *active_resources.memory_bytes - coarse_retained - *query_result_reservation_total;
    }
    auto executor_result = execution::make_executor(active_resources);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&executor_result)) return *diagnostics;
    auto executor = std::get<std::unique_ptr<execution::Executor>>(std::move(executor_result));
    auto effective_context = context;
    effective_context.resources = executor->resources();
    auto query_result = executor->run<registry::SelectorPort>(tasks, effective_context, mode, limit);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&query_result)) return *diagnostics;

    return FamilyQueryResult{std::move(coarse), std::move(records),
        std::get<execution::BatchResult<registry::SelectorPort>>(std::move(query_result)),
        query_result_reservation_total};
}

artifacts::ArtifactResult<artifacts::RecordedSweepArtifact> record_family_query_sweep(
    const problem::ResolvedContent& canonical_spec, const FamilyQueryResult& result,
    std::span<const artifacts::RecordedRunArtifact> coarse_runs,
    std::span<const std::optional<artifacts::RecordedRunArtifact>> query_runs,
    artifacts::EncodeLimits limits) {
    const auto count = result.sweep.cases.size();
    if (result.sweep.batch.tasks.size() != count || result.queries.size() != count ||
        coarse_runs.size() != count || query_runs.size() != count)
        return artifact_error(artifacts::ArtifactErrorCode::invalid_input, "sweep.alignment",
            "Cases, task records, query dispositions, and run artifacts must have matching lengths");
    if (result.query_batch.run_id != result.sweep.batch.run_id)
        return artifact_error(artifacts::ArtifactErrorCode::identity, "sweep.run_id",
            "Coarse and query phases must share a run ID");
    const auto coarse_resources = phase_resources(result.sweep.batch, result.sweep.requested_resources,
        result.sweep.retained_result_reservation_bytes);
    std::optional<std::size_t> query_retained;
    if (result.sweep.retained_result_reservation_bytes && result.query_result_reservation_bytes) {
        const auto coarse = *result.sweep.retained_result_reservation_bytes;
        const auto query = *result.query_result_reservation_bytes;
        if (query > std::numeric_limits<std::size_t>::max() - coarse)
            return artifact_error(artifacts::ArtifactErrorCode::invalid_input, "sweep.retained_result_memory",
                "Retained result reservations overflow the addressable size.");
        query_retained = coarse + query;
    }
    const auto query_resources = phase_resources(result.query_batch, result.sweep.requested_resources, query_retained);
    if (!coarse_resources || !query_resources)
        return artifact_error(artifacts::ArtifactErrorCode::invalid_input, "sweep.resources",
            "Both execution phases must retain their requested resource policy");

    std::vector<artifacts::SweepCaseInput> cases;
    cases.reserve(count);
    std::unordered_set<std::size_t> scheduled_tasks;
    for (std::size_t i = 0; i < count; ++i) {
        const auto& source = result.sweep.cases[i];
        const auto& query_record = result.queries[i];
        if (source.identity != query_record.identity)
            return artifact_error(artifacts::ArtifactErrorCode::identity, "sweep.cases[" + std::to_string(i) + "]",
                "Query identity is not aligned with its coarse case");
        if (!source.selection)
            return artifact_error(artifacts::ArtifactErrorCode::reference, "sweep.cases[" + std::to_string(i) + "].selection",
                "Selection settings were not retained with the coarse case");
        if (!recorded_run_matches(coarse_runs[i], result.sweep.batch.tasks[i].outcome))
            return artifact_error(artifacts::ArtifactErrorCode::identity,
                "sweep.cases[" + std::to_string(i) + "].coarse_run.outcome",
                "Recorded coarse outcome does not match the live strategy task outcome.");

        artifacts::SweepQueryDisposition disposition;
        if (const auto* not_run = std::get_if<FamilyQueryNotRun>(&query_record.status)) {
            const auto mapped = not_run_reason(not_run->reason);
            if (!mapped) return artifact_error(artifacts::ArtifactErrorCode::invalid_input,
                "sweep.cases[" + std::to_string(i) + "].query", "Unknown not-run reason");
            if (query_runs[i]) return artifact_error(artifacts::ArtifactErrorCode::reference,
                "sweep.cases[" + std::to_string(i) + "].query", "A not-run query cannot have a run artifact");
            disposition = artifacts::SweepQueryNotRun{*mapped};
        } else if (const auto* rejected = std::get_if<FamilyQueryRejected>(&query_record.status)) {
            if (query_runs[i]) return artifact_error(artifacts::ArtifactErrorCode::reference,
                "sweep.cases[" + std::to_string(i) + "].query", "A rejected query cannot have a run artifact");
            disposition = artifacts::SweepQueryRejected{rejected->diagnostics};
        } else {
            const auto task_index = std::get<FamilyQueryScheduled>(query_record.status).task_index;
            if (task_index >= result.query_batch.tasks.size() || !scheduled_tasks.insert(task_index).second)
                return artifact_error(artifacts::ArtifactErrorCode::reference,
                    "sweep.cases[" + std::to_string(i) + "].query", "Scheduled query task index is invalid or duplicated");
            if (!query_runs[i]) return artifact_error(artifacts::ArtifactErrorCode::reference,
                "sweep.cases[" + std::to_string(i) + "].query", "A scheduled query requires its recorded outcome");
            if (!recorded_query_matches(*query_runs[i], result.query_batch.tasks[task_index].outcome))
                return artifact_error(artifacts::ArtifactErrorCode::identity,
                    "sweep.cases[" + std::to_string(i) + "].query.outcome",
                    "Recorded query outcome does not match the live selector task outcome.");
            disposition = *query_runs[i];
        }

        const auto& selection = *source.selection;
        const auto seed = selection.seed ? std::optional<std::uint64_t>{static_cast<std::uint64_t>(*selection.seed)} : std::nullopt;
        cases.push_back({source.identity.scenario.value, source.identity.configuration, coarse_runs[i],
            {static_cast<std::uint64_t>(selection.count), selection.distinctness_tolerance,
                selection.directions, seed}, std::move(disposition)});
    }
    if (scheduled_tasks.size() != result.query_batch.tasks.size())
        return artifact_error(artifacts::ArtifactErrorCode::reference, "sweep.query_tasks",
            "Every query task must be referenced by exactly one case");
    return artifacts::encode_recorded_sweep(canonical_spec, result.sweep.batch.run_id,
        cases, *coarse_resources, *query_resources, limits);
}

} // namespace csl::experiments
