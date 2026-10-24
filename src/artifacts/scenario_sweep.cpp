#include <csl/artifacts/scenario_sweep.hpp>

#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <set>

namespace csl::artifacts {
namespace {
using Json = nlohmann::json;

template<class T>
Json optional_json(const std::optional<T>& value) {
    return value ? Json(*value) : Json(nullptr);
}

ArtifactError error(ArtifactErrorCode code, std::string path, std::string message) {
    return {code, std::move(path), std::move(message)};
}

std::string bytes_to_string(std::span<const std::byte> bytes) {
    std::string text;
    text.reserve(bytes.size());
    for (const auto byte : bytes) text.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
    return text;
}

ArtifactResult<problem::ResolvedContent> own(std::string_view text) {
    std::vector<std::byte> bytes;
    bytes.reserve(text.size());
    for (const unsigned char value : text) bytes.push_back(static_cast<std::byte>(value));
    auto result = problem::snapshot_content(bytes);
    if (auto* content = std::get_if<problem::ResolvedContent>(&result)) return *content;
    return error(ArtifactErrorCode::allocation, "sweep.content", "Could not own canonical sweep bytes");
}

std::string not_run_name(SweepNotRunReason reason) {
    switch (reason) {
    case SweepNotRunReason::strategy_skipped: return "strategy_skipped";
    case SweepNotRunReason::strategy_failed: return "strategy_failed";
    case SweepNotRunReason::strategy_unsupported: return "strategy_unsupported";
    case SweepNotRunReason::family_unavailable: return "family_unavailable";
    }
    return {};
}

SweepNotRunReason parse_not_run(std::string_view value) {
    if (value == "strategy_skipped") return SweepNotRunReason::strategy_skipped;
    if (value == "strategy_failed") return SweepNotRunReason::strategy_failed;
    if (value == "strategy_unsupported") return SweepNotRunReason::strategy_unsupported;
    if (value == "family_unavailable") return SweepNotRunReason::family_unavailable;
    throw std::invalid_argument("Unknown query not-run reason");
}

std::string memory_support_name(SweepMemorySupport support) {
    switch (support) {
    case SweepMemorySupport::unlimited_accounting: return "unlimited_accounting";
    case SweepMemorySupport::active_workspace_reservations: return "active_workspace_reservations";
    case SweepMemorySupport::active_and_retained_reservations: return "active_and_retained_reservations";
    case SweepMemorySupport::process_observation: return "process_observation";
    case SweepMemorySupport::operating_system_limit: return "operating_system_limit";
    }
    return {};
}

SweepMemorySupport parse_memory_support(std::string_view value) {
    if (value == "unlimited_accounting") return SweepMemorySupport::unlimited_accounting;
    if (value == "active_workspace_reservations") return SweepMemorySupport::active_workspace_reservations;
    if (value == "active_and_retained_reservations") return SweepMemorySupport::active_and_retained_reservations;
    if (value == "process_observation") return SweepMemorySupport::process_observation;
    if (value == "operating_system_limit") return SweepMemorySupport::operating_system_limit;
    throw std::invalid_argument("Unknown memory support kind");
}

Json resource_json(const SweepPhaseResources& resources) {
    const auto valid = check_resources(resources.requested);
    if (!valid.empty()) throw error(ArtifactErrorCode::invalid_input, "resources.requested", "Invalid requested resource policy");
    if (memory_support_name(resources.memory_support).empty())
        throw error(ArtifactErrorCode::invalid_input, "resources", "Invalid resource observation");
    if (resources.memory_support == SweepMemorySupport::active_and_retained_reservations &&
        (!resources.retained_result_reservation_bytes || !resources.peak_workspace_reservation_bytes ||
         !resources.enforced_memory_reservation_budget_bytes || !resources.requested.memory_bytes))
        throw error(ArtifactErrorCode::invalid_input, "resources.retained_result_reservation_bytes",
            "Active and retained accounting requires reservations and an enforced memory limit");
    if (resources.memory_support == SweepMemorySupport::active_workspace_reservations &&
        (!resources.peak_workspace_reservation_bytes || !resources.enforced_memory_reservation_budget_bytes ||
         !resources.requested.memory_bytes))
        throw error(ArtifactErrorCode::invalid_input, "resources.peak_workspace_reservation_bytes",
            "Workspace accounting requires a reservation and an enforced memory limit");
    if (resources.enforced_memory_reservation_budget_bytes && (!resources.requested.memory_bytes ||
        *resources.enforced_memory_reservation_budget_bytes > *resources.requested.memory_bytes))
        throw error(ArtifactErrorCode::invalid_input, "resources.enforced_memory_reservation_budget_bytes",
            "Enforced reservation budget must be present in and no larger than the requested policy");
    if ((resources.memory_support == SweepMemorySupport::process_observation ||
         resources.memory_support == SweepMemorySupport::operating_system_limit) &&
        resources.memory_observation_scope.empty())
        throw error(ArtifactErrorCode::invalid_input, "resources.memory_observation_scope",
            "Observed or enforced memory requires an accounting scope");
    if (resources.memory_support == SweepMemorySupport::process_observation &&
        !resources.observed_process_memory_bytes)
        throw error(ArtifactErrorCode::invalid_input, "resources.observed_process_memory_bytes",
            "Process observation requires a measured memory value, including zero");
    if (resources.memory_support == SweepMemorySupport::operating_system_limit &&
        (!resources.requested.memory_bytes || !resources.observed_process_memory_bytes))
        throw error(ArtifactErrorCode::invalid_input, "resources.memory_support",
            "Operating-system memory limiting requires a requested limit and observed usage");
    return {{"requested", {{"total_threads", resources.requested.total_threads},
            {"outer_workers", resources.requested.outer_workers},
            {"threads_per_worker", resources.requested.threads_per_worker},
            {"memory_bytes", optional_json(resources.requested.memory_bytes)}}},
        {"executor_worker_threads_started", optional_json(resources.executor_worker_threads_started)},
        {"peak_active_tasks", optional_json(resources.peak_active_tasks)},
        {"backend_threads", optional_json(resources.backend_threads)},
        {"peak_workspace_reservation_bytes", optional_json(resources.peak_workspace_reservation_bytes)},
        {"retained_result_reservation_bytes", optional_json(resources.retained_result_reservation_bytes)},
        {"enforced_memory_reservation_budget_bytes", optional_json(resources.enforced_memory_reservation_budget_bytes)},
        {"observed_process_memory_bytes", optional_json(resources.observed_process_memory_bytes)},
        {"memory_support", memory_support_name(resources.memory_support)},
        {"memory_observation_scope", resources.memory_observation_scope}};
}

SweepPhaseResources parse_resources(const Json& value) {
    if (!value.is_object() || value.size() != 10 || !value.contains("requested") ||
        !value.contains("executor_worker_threads_started") || !value.contains("peak_active_tasks") ||
        !value.contains("backend_threads") || !value.contains("peak_workspace_reservation_bytes") ||
        !value.contains("retained_result_reservation_bytes") || !value.contains("enforced_memory_reservation_budget_bytes") ||
        !value.contains("observed_process_memory_bytes") ||
        !value.contains("memory_support") || !value.contains("memory_observation_scope"))
        throw error(ArtifactErrorCode::invalid_input, "resources", "Resource fields do not match sweep schema");
    const auto& requested = value.at("requested");
    if (!requested.is_object() || requested.size() != 4 || !requested.contains("total_threads") ||
        !requested.contains("outer_workers") || !requested.contains("threads_per_worker") || !requested.contains("memory_bytes"))
        throw error(ArtifactErrorCode::invalid_input, "resources.requested", "Requested resource fields do not match sweep schema");
    SweepPhaseResources result{{requested.at("total_threads").get<std::size_t>(),
        requested.at("outer_workers").get<std::size_t>(),
        requested.at("threads_per_worker").get<std::size_t>(),
        requested.at("memory_bytes").is_null() ? std::nullopt :
            std::optional<std::size_t>{requested.at("memory_bytes").get<std::size_t>()},
        }, {}, {}, {}, {}, {}, {}, {}, SweepMemorySupport::unlimited_accounting, {}};
    const auto optional_count = [](const Json& item) -> std::optional<std::uint64_t> {
        if (item.is_null()) return {};
        return item.get<std::uint64_t>();
    };
    result.executor_worker_threads_started = optional_count(value.at("executor_worker_threads_started"));
    result.peak_active_tasks = optional_count(value.at("peak_active_tasks"));
    result.backend_threads = optional_count(value.at("backend_threads"));
    result.peak_workspace_reservation_bytes = optional_count(value.at("peak_workspace_reservation_bytes"));
    result.retained_result_reservation_bytes = optional_count(value.at("retained_result_reservation_bytes"));
    result.enforced_memory_reservation_budget_bytes = optional_count(value.at("enforced_memory_reservation_budget_bytes"));
    result.observed_process_memory_bytes = optional_count(value.at("observed_process_memory_bytes"));
    result.memory_support = parse_memory_support(value.at("memory_support").get<std::string>());
    result.memory_observation_scope = value.at("memory_observation_scope").get<std::string>();
    (void)resource_json(result);
    return result;
}

bool valid_selection(const SweepSelectionInput& selection) {
    const auto dimensions = selection.directions.empty() ? 0 : selection.directions.front().size();
    return selection.requested_count > 0 && std::isfinite(selection.distinctness_tolerance) &&
        selection.distinctness_tolerance >= 0.0 &&
        std::all_of(selection.directions.begin(), selection.directions.end(), [dimensions](const Vector& direction) {
            return direction.size() == dimensions &&
                std::all_of(direction.begin(), direction.end(), [](double coordinate) { return std::isfinite(coordinate); });
        });
}

Json selection_json(const SweepSelectionInput& selection) {
    if (!valid_selection(selection))
        throw error(ArtifactErrorCode::invalid_input, "selection", "Selection request must be finite and have a positive count");
    return {{"requested_count", selection.requested_count}, {"distinctness_tolerance", selection.distinctness_tolerance},
        {"directions", selection.directions}, {"seed", optional_json(selection.seed)}};
}

SweepSelectionInput parse_selection(const Json& value) {
    if (!value.is_object() || value.size() != 4 || !value.contains("requested_count") ||
        !value.contains("distinctness_tolerance") || !value.contains("directions") || !value.contains("seed"))
        throw error(ArtifactErrorCode::invalid_input, "selection", "Selection fields do not match sweep schema");
    SweepSelectionInput result{value.at("requested_count").get<std::uint64_t>(),
        value.at("distinctness_tolerance").get<double>(), value.at("directions").get<std::vector<Vector>>(),
        value.at("seed").is_null() ? std::nullopt : std::optional<std::uint64_t>{value.at("seed").get<std::uint64_t>()}};
    if (!valid_selection(result)) throw error(ArtifactErrorCode::invalid_input, "selection", "Invalid selection values");
    return result;
}

std::string run_text(const RecordedRunArtifact& run) { return bytes_to_string(run.content().bytes()); }

std::string run_configuration_id(std::string_view text) {
    const auto run = Json::parse(text.begin(), text.end());
    return run.at("configuration").at("id").get<std::string>();
}

Json query_json(const SweepQueryDisposition& query) {
    if (const auto* not_run = std::get_if<SweepQueryNotRun>(&query)) {
        const auto name = not_run_name(not_run->reason);
        if (name.empty()) throw error(ArtifactErrorCode::invalid_input, "query.reason", "Unknown query disposition");
        return {{"kind", "not_run"}, {"reason", name}};
    }
    if (const auto* rejected = std::get_if<SweepQueryRejected>(&query)) {
        if (rejected->diagnostics.empty()) throw error(ArtifactErrorCode::invalid_input, "query.diagnostics", "Rejection must retain diagnostics");
        Json diagnostics = Json::array();
        for (const auto& diagnostic : rejected->diagnostics) {
            if (static_cast<std::uint32_t>(diagnostic.code) > static_cast<std::uint32_t>(DiagnosticCode::invalid_claim))
                throw error(ArtifactErrorCode::invalid_input, "query.diagnostics.code", "Unknown diagnostic code");
            diagnostics.push_back({{"code", static_cast<std::uint32_t>(diagnostic.code)},
                {"field", diagnostic.field}, {"explanation", diagnostic.explanation}});
        }
        return {{"kind", "rejected"}, {"diagnostics", std::move(diagnostics)}};
    }
    return {{"kind", "run"}, {"artifact", run_text(std::get<RecordedRunArtifact>(query))}};
}

Json case_json(const SweepCaseInput& item, const DecodeLimits& limits) {
    if (item.scenario_id.empty() || item.configuration.value.empty())
        throw error(ArtifactErrorCode::invalid_input, "cases.identity", "Scenario and configuration IDs must be nonempty");
    if (!valid_selection(item.selection))
        throw error(ArtifactErrorCode::invalid_input, "cases.selection", "Invalid deterministic selection request");
    const auto coarse = run_text(item.coarse_run);
    if (std::holds_alternative<ArtifactError>(decode_recorded_run(coarse, limits)))
        throw error(ArtifactErrorCode::reference, "cases.coarse_run", "Coarse run is not a valid recorded run artifact");
    if (run_configuration_id(coarse) != item.configuration.value)
        throw error(ArtifactErrorCode::identity, "cases.configuration_id", "Configuration ID does not match the coarse run");
    Json query = query_json(item.query);
    if (query.value("kind", std::string{}) == "run") {
        const auto query_text = query.at("artifact").get<std::string>();
        if (std::holds_alternative<ArtifactError>(decode_recorded_run(query_text, limits)))
            throw error(ArtifactErrorCode::reference, "cases.query", "Query run is not a valid recorded run artifact");
        if (run_configuration_id(query_text) != item.configuration.value)
            throw error(ArtifactErrorCode::identity, "cases.query", "Configuration ID does not match the query run");
    }
    return {{"scenario_id", item.scenario_id}, {"configuration_id", item.configuration.value},
        {"coarse_run", coarse}, {"selection", selection_json(item.selection)}, {"query", std::move(query)}};
}

Json parse_case(const Json& item, const DecodeLimits& limits) {
    if (!item.is_object() || item.size() != 5 || !item.contains("scenario_id") ||
        !item.contains("configuration_id") || !item.contains("coarse_run") ||
        !item.contains("selection") || !item.contains("query"))
        throw error(ArtifactErrorCode::invalid_input, "cases", "Case fields do not match sweep schema");
    const auto coarse = item.at("coarse_run").get<std::string>();
    if (std::holds_alternative<ArtifactError>(decode_recorded_run(coarse, limits)))
        throw error(ArtifactErrorCode::reference, "cases.coarse_run", "Coarse run is not a valid recorded run artifact");
    const auto configuration = item.at("configuration_id").get<std::string>();
    if (run_configuration_id(coarse) != configuration)
        throw error(ArtifactErrorCode::identity, "cases.configuration_id", "Configuration ID does not match the coarse run");
    (void)parse_selection(item.at("selection"));
    const auto& query = item.at("query");
    if (!query.is_object() || !query.contains("kind")) throw error(ArtifactErrorCode::invalid_input, "cases.query", "Invalid query disposition");
    const auto kind = query.at("kind").get<std::string>();
    if (kind == "not_run") {
        if (query.size() != 2 || !query.contains("reason")) throw error(ArtifactErrorCode::invalid_input, "cases.query", "Invalid not-run disposition");
        (void)parse_not_run(query.at("reason").get<std::string>());
    } else if (kind == "rejected") {
        if (query.size() != 2 || !query.contains("diagnostics") || !query.at("diagnostics").is_array() || query.at("diagnostics").empty())
            throw error(ArtifactErrorCode::invalid_input, "cases.query", "Rejected query must retain diagnostics");
        for (const auto& diagnostic : query.at("diagnostics"))
            if (!diagnostic.is_object() || diagnostic.size() != 3 || !diagnostic.contains("code") ||
                !diagnostic.contains("field") || !diagnostic.contains("explanation") ||
                !diagnostic.at("code").is_number_integer() ||
                diagnostic.at("code").get<std::uint32_t>() > static_cast<std::uint32_t>(DiagnosticCode::invalid_claim) ||
                !diagnostic.at("field").is_string() || !diagnostic.at("explanation").is_string())
                throw error(ArtifactErrorCode::invalid_input, "cases.query.diagnostics", "Invalid portable diagnostic");
    } else if (kind == "run") {
        if (query.size() != 2 || !query.contains("artifact") ||
            std::holds_alternative<ArtifactError>(decode_recorded_run(query.at("artifact").get<std::string>(), limits)))
            throw error(ArtifactErrorCode::reference, "cases.query", "Query run is not a valid recorded run artifact");
        if (run_configuration_id(query.at("artifact").get<std::string>()) != configuration)
            throw error(ArtifactErrorCode::identity, "cases.query", "Configuration ID does not match the query run");
    } else throw error(ArtifactErrorCode::invalid_input, "cases.query.kind", "Unknown query disposition");
    return item;
}

Json parse_bounded(std::string_view text, const DecodeLimits& limits) {
    if (text.size() > limits.bytes) throw error(ArtifactErrorCode::limit, "sweep.bytes", "Input exceeds byte limit");
    std::uint64_t depth = 0, nodes = 0;
    const auto count_node = [&] {
        if (++nodes > limits.nodes) throw error(ArtifactErrorCode::limit, "sweep.nodes", "Node capacity exceeded");
    };
    for (std::size_t i = 0; i < text.size(); ++i) {
        const char c = text[i];
        if (c == '"') {
            count_node();
            std::uint64_t length = 0;
            bool closed = false;
            for (++i; i < text.size(); ++i) {
                const char ch = text[i];
                if (ch == '"') { closed = true; break; }
                if (ch == '\\' && i + 1 < text.size()) {
                    ++i;
                    if (text[i] == 'u') i = std::min(i + 4, text.size() - 1);
                }
                if (++length > limits.string_bytes)
                    throw error(ArtifactErrorCode::limit, "sweep.string", "String capacity exceeded");
            }
            if (!closed) throw error(ArtifactErrorCode::invalid_input, "sweep.syntax", "Unterminated string");
        } else if (c == '{' || c == '[') {
            count_node();
            if (++depth > limits.depth) throw error(ArtifactErrorCode::limit, "sweep.depth", "Nesting depth exceeded");
        } else if (c == '}' || c == ']') {
            if (depth == 0) throw error(ArtifactErrorCode::invalid_input, "sweep.syntax", "Unexpected closing delimiter");
            --depth;
        } else if (c == 't' || c == 'f' || c == 'n' || c == '-' || (c >= '0' && c <= '9')) {
            count_node();
            while (i + 1 < text.size() && text[i + 1] != ',' && text[i + 1] != ']' && text[i + 1] != '}' &&
                text[i + 1] != ' ' && text[i + 1] != '\n' && text[i + 1] != '\r' && text[i + 1] != '\t') ++i;
        }
    }
    std::vector<std::set<std::string>> object_keys;
    return Json::parse(text.begin(), text.end(), [&](int, Json::parse_event_t event, Json& parsed) {
        if (event == Json::parse_event_t::object_start) object_keys.emplace_back();
        else if (event == Json::parse_event_t::key) {
            if (object_keys.empty() || !object_keys.back().insert(parsed.get<std::string>()).second)
                throw error(ArtifactErrorCode::invalid_input, "sweep.duplicate_key", "Duplicate object key");
        } else if (event == Json::parse_event_t::object_end) object_keys.pop_back();
        return true;
    });
}
}

ArtifactResult<RecordedSweepArtifact> encode_recorded_sweep(const problem::ResolvedContent& spec, std::string run_id,
    const std::vector<SweepCaseInput>& cases, const SweepPhaseResources& coarse, const SweepPhaseResources& query,
    EncodeLimits limits) {
    try {
        if (run_id.empty() || cases.empty()) return error(ArtifactErrorCode::invalid_input, "sweep", "Run ID and at least one case are required");
        if (cases.size() > limits.bytes / 32 || cases.size() > 1000000)
            return error(ArtifactErrorCode::limit, "sweep.cases", "Case count exceeds byte or structural limits");
        const auto spec_text = bytes_to_string(spec.bytes());
        DecodeLimits validation_limits{limits.bytes, 1000000, 64, limits.bytes};
        const auto parsed_spec = parse_bounded(spec_text, validation_limits);
        if (parsed_spec.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "sweep.spec", "Sweep spec must be canonical JSON");
        if (spec_text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "sweep.spec", "Sweep spec exceeds byte limit");
        std::set<std::pair<std::string, std::string>> identities;
        Json records = Json::array();
        for (std::size_t i = 0; i < cases.size(); ++i) {
            const auto& item = cases[i];
            if (!identities.emplace(item.scenario_id, item.configuration.value).second)
                return error(ArtifactErrorCode::identity, "cases[" + std::to_string(i) + "]", "Scenario/configuration identity must be unique");
            records.push_back(case_json(item, validation_limits));
        }
        Json wire{{"schema", "csl.scenario-sweep/1"}, {"run_id", std::move(run_id)},
            {"spec", spec_text}, {"spec_digest", problem::hex(spec.digest())},
            {"cases", std::move(records)}, {"coarse_resources", resource_json(coarse)},
            {"query_resources", resource_json(query)}};
        const auto text = wire.dump();
        if (text.size() > limits.bytes) return error(ArtifactErrorCode::limit, "sweep.bytes", "Encoded sweep exceeds byte limit");
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) return RecordedSweepArtifact(*owned);
        return std::get<ArtifactError>(std::move(content));
    } catch (const ArtifactError& failure) { return failure; }
      catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "sweep", "Allocation failed"); }
      catch (const std::exception& failure) { return error(ArtifactErrorCode::invalid_input, "sweep", std::string("Invalid sweep data: ") + failure.what()); }
}

ArtifactResult<RecordedSweepArtifact> decode_recorded_sweep(std::string_view text, DecodeLimits limits) {
    try {
        auto wire = parse_bounded(text, limits);
        if (wire.dump() != text) return error(ArtifactErrorCode::invalid_input, "sweep.canonical", "Sweep JSON is not canonical");
        if (!wire.is_object() || wire.size() != 7 || !wire.contains("schema") || !wire.contains("run_id") ||
            !wire.contains("spec") || !wire.contains("spec_digest") || !wire.contains("cases") ||
            !wire.contains("coarse_resources") || !wire.contains("query_resources"))
            return error(ArtifactErrorCode::invalid_input, "sweep.fields", "Sweep fields do not match schema");
        if (wire.at("schema") != "csl.scenario-sweep/1") return error(ArtifactErrorCode::unsupported, "sweep.schema", "Unknown sweep schema");
        if (wire.at("run_id").get<std::string>().empty()) return error(ArtifactErrorCode::invalid_input, "sweep.run_id", "Run ID must be nonempty");
        const auto spec_text = wire.at("spec").get<std::string>();
        if (spec_text.size() > limits.string_bytes) return error(ArtifactErrorCode::limit, "sweep.spec", "Spec exceeds string limit");
        const auto spec = parse_bounded(spec_text, limits);
        if (spec.dump() != spec_text) return error(ArtifactErrorCode::invalid_input, "sweep.spec", "Spec is not canonical JSON");
        auto owned_spec = own(spec_text);
        if (std::holds_alternative<ArtifactError>(owned_spec) ||
            problem::hex(std::get<problem::ResolvedContent>(owned_spec).digest()) != wire.at("spec_digest").get<std::string>())
            return error(ArtifactErrorCode::identity, "sweep.spec_digest", "Spec digest mismatch");
        const auto& cases = wire.at("cases");
        if (!cases.is_array() || cases.empty() || cases.size() > limits.nodes)
            return error(ArtifactErrorCode::limit, "sweep.cases", "Case count is empty or exceeds structural limits");
        std::set<std::pair<std::string, std::string>> identities;
        for (std::size_t i = 0; i < cases.size(); ++i) {
            const auto valid_case = parse_case(cases[i], limits);
            const auto identity = std::pair{valid_case.at("scenario_id").get<std::string>(), valid_case.at("configuration_id").get<std::string>()};
            if (identity.first.empty() || identity.second.empty() || !identities.insert(identity).second)
                return error(ArtifactErrorCode::identity, "sweep.cases[" + std::to_string(i) + "]", "Case identity is empty or duplicated");
        }
        (void)parse_resources(wire.at("coarse_resources"));
        (void)parse_resources(wire.at("query_resources"));
        auto content = own(text);
        if (auto* owned = std::get_if<problem::ResolvedContent>(&content)) return RecordedSweepArtifact(*owned);
        return std::get<ArtifactError>(std::move(content));
    } catch (const ArtifactError& failure) { return failure; }
      catch (const std::bad_alloc&) { return error(ArtifactErrorCode::allocation, "sweep", "Allocation failed"); }
      catch (const std::exception& failure) { return error(ArtifactErrorCode::invalid_input, "sweep", std::string("Invalid sweep data: ") + failure.what()); }
}

} // namespace csl::artifacts
