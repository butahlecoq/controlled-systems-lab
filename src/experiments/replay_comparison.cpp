#include <csl/experiments/replay_artifact.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <limits>
#include <set>
#include <stdexcept>

namespace csl::experiments {
namespace {
using Json = nlohmann::json;

artifacts::ArtifactError error(artifacts::ArtifactErrorCode code, std::string path,
    std::string message) {
    return {code, std::move(path), std::move(message)};
}

const char* check_status(verification::CheckStatus value) {
    switch (value) {
    case verification::CheckStatus::not_checked: return "not_checked";
    case verification::CheckStatus::numerical_pass: return "numerical_pass";
    case verification::CheckStatus::violation: return "violation";
    case verification::CheckStatus::invalid_input: return "invalid_input";
    case verification::CheckStatus::unsupported: return "unsupported";
    }
    return "unknown";
}

const char* replay_status(simulation::ReplayStatus value) {
    switch (value) {
    case simulation::ReplayStatus::complete: return "complete";
    case simulation::ReplayStatus::unavailable: return "unavailable";
    case simulation::ReplayStatus::invalid_input: return "invalid_input";
    case simulation::ReplayStatus::numerical_failure: return "numerical_failure";
    case simulation::ReplayStatus::callback_failure: return "callback_failure";
    case simulation::ReplayStatus::cancelled: return "cancelled";
    case simulation::ReplayStatus::resource_limit: return "resource_limit";
    }
    return "unknown";
}

const char* policy_class(ReplayPolicyClass value) {
    switch (value) {
    case ReplayPolicyClass::nominal_reference: return "nominal_reference";
    case ReplayPolicyClass::frozen_coefficient_regulator: return "frozen_coefficient_regulator";
    case ReplayPolicyClass::selected_linear_witness: return "selected_linear_witness";
    }
    return "unknown";
}

const char* diagnostic_code(DiagnosticCode value) {
    switch (value) {
    case DiagnosticCode::invalid_input: return "invalid_input";
    case DiagnosticCode::unsupported: return "unsupported";
    case DiagnosticCode::evidence_mismatch: return "evidence_mismatch";
    case DiagnosticCode::invalid_claim: return "invalid_claim";
    }
    return "unknown";
}

Json vector_json(const Vector& values) { return values; }
Json history_json(const std::vector<Vector>& values) {
    Json result = Json::array();
    for (const auto& row : values) result.push_back(vector_json(row));
    return result;
}

Json objective_json(const TerminalObjective& objective) {
    return std::visit([](const auto& value) -> Json {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, LinearTerminal>)
            return {{"kind", "linear"}, {"coefficients", value.coefficients}, {"offset", value.offset}};
        else if constexpr (std::is_same_v<T, QuadraticTerminal>)
            return {{"kind", "quadratic"}, {"Q", {{"rows", value.Q.rows}, {"cols", value.Q.cols},
                    {"values", value.Q.values}}}, {"linear", value.linear}, {"offset", value.offset}};
        else
            return {{"kind", "residual_norm"}, {"map", {{"rows", value.map.rows},
                    {"cols", value.map.cols}, {"values", value.map.values}}}, {"target", value.target}};
    }, objective);
}

template<class T> Json optional_json(const std::optional<T>& value) {
    return value ? Json(*value) : Json(nullptr);
}

Json annotation_json(const artifacts::CoordinateAnnotation& value) {
    Json result{{"label", optional_json(value.label)}, {"unit", optional_json(value.unit)}};
    if (value.target) result["target"] = {{"value", value.target->value}, {"source", value.target->source}};
    else result["target"] = nullptr;
    if (value.bounds) result["bounds"] = {{{"value", value.bounds->first.value}, {"source", value.bounds->first.source}},
        {{"value", value.bounds->second.value}, {"source", value.bounds->second.source}}};
    else result["bounds"] = nullptr;
    return result;
}

Json evidence_json(const artifacts::PlotEvidence& evidence) {
    Json residuals = Json::array();
    for (const auto& item : evidence.residuals)
        residuals.push_back({{"field", item.field}, {"violation", item.measure.violation},
            {"scale", item.measure.scale}, {"tolerance", item.tolerance}, {"satisfied", item.satisfied}});
    return {{"bindings", check_status(evidence.bindings)},
        {"feasibility", check_status(evidence.feasibility)},
        {"objective", check_status(evidence.objective)},
        {"optimality", check_status(evidence.optimality)},
        {"completeness", check_status(evidence.completeness)},
        {"validated", check_status(evidence.validated)}, {"residuals", std::move(residuals)}};
}

Json replay_json(const simulation::ReplayRecord& replay) {
    Json parameters = Json::array();
    for (const auto& parameter : replay.parameters)
        parameters.push_back({{"name", parameter.name}, {"value", parameter.value}, {"unit", parameter.unit}});
    Json diagnostics = Json::array();
    for (const auto& item : replay.diagnostics)
        diagnostics.push_back({{"code", diagnostic_code(item.code)}, {"field", item.field},
            {"explanation", item.explanation}});
    Json integration = nullptr;
    if (replay.integration) {
        switch (*replay.integration) {
        case simulation::IntegrationMethod::exact_discrete_map:
            integration = "exact_discrete_map";
            break;
        case simulation::IntegrationMethod::adaptive_rk4_step_doubling:
            integration = "adaptive_rk4_step_doubling";
            break;
        }
    }
    Json hold = replay.hold ? Json("constant_on_interval") : Json(nullptr);
    Json initial = replay.declared_initial_state ? Json(*replay.declared_initial_state) : Json(nullptr);
    Json objective = replay.original_objective ? Json(*replay.original_objective) : Json(nullptr);
    Json residual = std::visit([](const auto& evidence) -> Json {
        using T = std::decay_t<decltype(evidence)>;
        if constexpr (std::is_same_v<T, simulation::IntegrationResidualNotApplicable>) {
            return {{"status", "not_applicable"}};
        } else if constexpr (std::is_same_v<T, simulation::IntegrationResidualUnavailable>) {
            const auto reason = evidence.reason == simulation::IntegrationResidualUnavailableReason::legacy_artifact
                ? "legacy_artifact" : "not_recorded";
            return {{"status", "unavailable"}, {"reason", reason}};
        } else {
            Json measurements = Json::array();
            for (const auto& item : evidence.measurements)
                measurements.push_back({{"name", item.name}, {"value", item.value}, {"unit", item.unit}});
            return {{"status", "available"}, {"definition", evidence.definition},
                {"measurements", std::move(measurements)}};
        }
    }, replay.integration_residual);
    Json numerical = replay.numerical
        ? Json{{"absolute_tolerance", replay.numerical->absolute_tolerance},
            {"relative_tolerance", replay.numerical->relative_tolerance}}
        : Json(nullptr);
    Json limits = replay.integration_limits ? Json{{"absolute_tolerance", replay.integration_limits->absolute_tolerance},
        {"relative_tolerance", replay.integration_limits->relative_tolerance},
        {"max_attempts_per_interval", replay.integration_limits->max_attempts_per_interval}} : Json(nullptr);
    Json receipts = Json::array();
    for (const auto& item : replay.integration_receipts)
        receipts.push_back({{"accepted_steps", item.accepted_steps}, {"rejected_steps", item.rejected_steps},
            {"max_accepted_local_error_estimates", item.max_accepted_local_error_estimates}});
    return {{"status", replay_status(replay.status)},
        {"plant", {{"name", replay.plant.name}, {"version", replay.plant.version}, {"source", replay.plant.source}}},
        {"parameters", std::move(parameters)}, {"initial_state", std::move(initial)},
        {"time_unit", replay.time_unit}, {"times", replay.times},
        {"state_units", replay.state_units}, {"control_units", replay.control_units},
        {"objective_name", replay.objective_name}, {"objective_unit", replay.objective_unit},
        {"integration", std::move(integration)}, {"control_hold", std::move(hold)},
        {"numerical_policy", std::move(numerical)}, {"integration_limits", std::move(limits)},
        {"integration_receipts", std::move(receipts)}, {"integration_residual", std::move(residual)},
        {"controls", history_json(replay.controls)}, {"states", history_json(replay.states)},
        {"original_objective", std::move(objective)},
        {"replay_time_ns", std::chrono::duration_cast<std::chrono::nanoseconds>(replay.replay_time).count()},
        {"missing_prerequisites", replay.missing_prerequisites}, {"diagnostics", std::move(diagnostics)}};
}

Json comparison_json(const ReplayComparison& comparison) {
    Json witnesses = Json::array();
    for (const auto& item : comparison.witnesses) {
        witnesses.push_back({{"source_ordinal", item.linear.source_ordinal},
            {"strategy", item.linear.strategy.value}, {"strategy_version", item.linear.strategy_version},
            {"policy_class", policy_class(item.policy_class)},
            {"claims", {{"nonlinear_feasibility", check_status(item.claims.nonlinear_feasibility)},
                {"nonlinear_objective_quality", check_status(item.claims.nonlinear_objective_quality)},
                {"nonlinear_global_optimality", check_status(item.claims.nonlinear_global_optimality)}}},
            {"linear_states", history_json(item.linear.states)},
            {"linear_controls", history_json(item.linear.controls)},
            {"linear_objective", item.linear.objective}, {"linear_evidence", evidence_json(item.linear.evidence)},
            {"replay", replay_json(item.nonlinear)}});
    }
    Json coordinates = Json::array();
    for (const auto& item : comparison.state_coordinates.coordinates)
        coordinates.push_back(annotation_json(item));
    Json controls = Json::array();
    for (const auto& item : comparison.control_coordinates.coordinates)
        controls.push_back(annotation_json(item));
    const auto axis_kind = comparison.state_axis.kind == artifacts::PlotAxis::Kind::stage
        ? "stage" : "physical_time";
    return {{"schema", "csl.viz04-replay-comparison/3"},
        {"source_run", {{"run", comparison.source_run.run.value},
            {"content_sha256", problem::hex(comparison.source_run.content_digest)}}},
        {"problem", comparison.problem.value}, {"strategy", comparison.witnesses.empty()
            ? std::string{} : comparison.witnesses.front().linear.strategy.value},
        {"strategy_version", comparison.witnesses.empty()
            ? std::string{} : comparison.witnesses.front().linear.strategy_version},
        {"state_axis", {{"kind", axis_kind}, {"points", comparison.state_axis.points},
            {"interval_ends", comparison.state_axis.interval_ends}, {"unit", optional_json(comparison.state_axis.unit)}}},
        {"state_coordinates", std::move(coordinates)}, {"control_coordinates", std::move(controls)},
        {"linear_objective_convention", objective_json(comparison.linear_objective)},
        {"linear_objective_unit", optional_json(comparison.linear_objective_unit)}, {"witnesses", std::move(witnesses)}};
}

bool same_declaration(const simulation::ReplayRecord& a, const simulation::ReplayRecord& b) {
    return a.plant.name == b.plant.name && a.plant.version == b.plant.version &&
        a.plant.source == b.plant.source && a.parameters == b.parameters &&
        a.declared_initial_state == b.declared_initial_state && a.time_unit == b.time_unit &&
        a.times == b.times && a.state_units == b.state_units && a.control_units == b.control_units &&
        a.objective_name == b.objective_name && a.objective_unit == b.objective_unit &&
        a.integration == b.integration && a.hold == b.hold && a.numerical == b.numerical &&
        a.integration_limits == b.integration_limits;
}

bool valid_history(const std::vector<Vector>& history, std::size_t dimension) {
    return std::all_of(history.begin(), history.end(), [dimension](const auto& row) {
        return row.size() == dimension && std::all_of(row.begin(), row.end(),
            [](double value) { return std::isfinite(value); });
    });
}

bool finite_number(const Json& value) {
    return value.is_number() && std::isfinite(value.get<double>());
}

bool finite_vector(const Json& value) {
    return value.is_array() && std::all_of(value.begin(), value.end(), finite_number);
}

bool finite_history(const Json& value) {
    return value.is_array() && std::all_of(value.begin(), value.end(), finite_vector);
}

bool string_array(const Json& value) {
    return value.is_array() && std::all_of(value.begin(), value.end(),
        [](const auto& item) { return item.is_string(); });
}

bool optional_string(const Json& value) {
    return value.is_null() || value.is_string();
}

bool annotation_array(const Json& value) {
    if (!value.is_array()) return false;
    for (const auto& item : value) {
        if (!item.is_object() || !item.contains("label") || !optional_string(item["label"]) ||
            !item.contains("unit") || !optional_string(item["unit"]) || !item.contains("target") ||
            !item.contains("bounds")) return false;
        const auto valid_point = [](const Json& point) {
            return point.is_object() && point.contains("value") && finite_number(point["value"]) &&
                point.contains("source") && point["source"].is_string();
        };
        if (!item["target"].is_null() && !valid_point(item["target"])) return false;
        const auto& bounds = item["bounds"];
        if (!bounds.is_null() && (!bounds.is_array() || bounds.size() != 2 ||
            !valid_point(bounds[0]) || !valid_point(bounds[1]))) return false;
    }
    return true;
}

bool objective_document(const Json& objective) {
    if (!objective.is_object() || !objective.contains("kind") || !objective["kind"].is_string()) return false;
    const auto kind = objective["kind"].get<std::string>();
    if (kind == "linear")
        return objective.contains("coefficients") && finite_vector(objective["coefficients"]) &&
            objective.contains("offset") && finite_number(objective["offset"]);
    if (kind == "quadratic" || kind == "residual_norm") {
        const char* matrix_name = kind == "quadratic" ? "Q" : "map";
        if (!objective.contains(matrix_name) || !objective[matrix_name].is_object()) return false;
        const auto& matrix = objective[matrix_name];
        if (!matrix.contains("rows") || !matrix["rows"].is_number_unsigned() ||
            !matrix.contains("cols") || !matrix["cols"].is_number_unsigned() ||
            !matrix.contains("values") || !finite_vector(matrix["values"])) return false;
        const auto rows = matrix["rows"].get<std::uint64_t>();
        const auto cols = matrix["cols"].get<std::uint64_t>();
        if (cols != 0 && rows > std::numeric_limits<std::uint64_t>::max() / cols) return false;
        if (matrix["values"].size() != rows * cols) return false;
        if (kind == "quadratic")
            return objective.contains("linear") && finite_vector(objective["linear"]) &&
                objective.contains("offset") && finite_number(objective["offset"]);
        return objective.contains("target") && finite_vector(objective["target"]);
    }
    return false;
}

bool evidence_document(const Json& evidence) {
    if (!evidence.is_object() || !evidence.contains("residuals") || !evidence["residuals"].is_array()) return false;
    const auto status = [](const Json& value) {
        return value.is_string() && (value == "not_checked" || value == "numerical_pass" ||
            value == "violation" || value == "invalid_input" || value == "unsupported");
    };
    for (const char* field : {"bindings", "feasibility", "objective", "optimality", "completeness", "validated"})
        if (!evidence.contains(field) || !status(evidence[field])) return false;
    for (const auto& residual : evidence["residuals"])
        if (!residual.is_object() || !residual.contains("field") || !residual["field"].is_string() ||
            !residual.contains("violation") || !finite_number(residual["violation"]) ||
            !residual.contains("scale") || !finite_number(residual["scale"]) ||
            !residual.contains("tolerance") || !finite_number(residual["tolerance"]) ||
            !residual.contains("satisfied") || !residual["satisfied"].is_boolean()) return false;
    return true;
}

bool numerical_policy_document(const Json& policy) {
    return policy.is_null() || (policy.is_object() && policy.size() == 2 &&
        policy.contains("absolute_tolerance") && finite_number(policy["absolute_tolerance"]) &&
        policy["absolute_tolerance"].get<double>() >= 0.0 &&
        policy.contains("relative_tolerance") && finite_number(policy["relative_tolerance"]) &&
        policy["relative_tolerance"].get<double>() >= 0.0);
}

bool integration_residual_document(const Json& residual) {
    if (!residual.is_object() || !residual.contains("status") || !residual["status"].is_string()) return false;
    const auto status = residual["status"].get<std::string>();
    if (status == "not_applicable") return residual.size() == 1;
    if (status == "unavailable")
        return residual.size() == 2 && residual.contains("reason") && residual["reason"].is_string() &&
            (residual["reason"] == "legacy_artifact" || residual["reason"] == "not_recorded");
    if (status != "available" || residual.size() != 3 || !residual.contains("definition") ||
        !residual["definition"].is_string() || residual["definition"].get<std::string>().empty() ||
        !residual.contains("measurements") || !residual["measurements"].is_array() ||
        residual["measurements"].empty()) return false;
    std::set<std::string> names;
    for (const auto& measurement : residual["measurements"])
        if (!measurement.is_object() || measurement.size() != 3 ||
            !measurement.contains("name") || !measurement["name"].is_string() ||
            measurement["name"].get<std::string>().empty() ||
            !names.insert(measurement["name"].get<std::string>()).second ||
            !measurement.contains("value") || !finite_number(measurement["value"]) ||
            !measurement.contains("unit") || !measurement["unit"].is_string() ||
            measurement["unit"].get<std::string>().empty()) return false;
    return true;
}

bool integration_limits_document(const Json& limits) {
    if (limits.is_null()) return true;
    return limits.is_object() && limits.size() == 3 &&
        limits.contains("absolute_tolerance") && finite_number(limits["absolute_tolerance"]) &&
        limits["absolute_tolerance"].get<double>() >= 0.0 &&
        limits.contains("relative_tolerance") && finite_number(limits["relative_tolerance"]) &&
        limits["relative_tolerance"].get<double>() >= 0.0 &&
        (limits["absolute_tolerance"].get<double>() > 0.0 ||
         limits["relative_tolerance"].get<double>() > 0.0) &&
        limits.contains("max_attempts_per_interval") &&
        limits["max_attempts_per_interval"].is_number_unsigned() &&
        limits["max_attempts_per_interval"].get<std::uint64_t>() > 0;
}

bool replay_document(const Json& replay, std::size_t state_dimensions,
    std::size_t control_dimensions, std::size_t linear_intervals, bool version_two, bool version_three) {
    if (!replay.is_object() || !replay.contains("status") || !replay["status"].is_string() ||
        !replay.contains("plant") || !replay["plant"].is_object() ||
        !replay.contains("parameters") || !replay["parameters"].is_array() ||
        !replay.contains("initial_state") || !replay.contains("time_unit") || !replay["time_unit"].is_string() ||
        !replay.contains("times") || !finite_vector(replay["times"]) ||
        !replay.contains("state_units") || !string_array(replay["state_units"]) ||
        !replay.contains("control_units") || !string_array(replay["control_units"]) ||
        !replay.contains("objective_name") || !replay["objective_name"].is_string() ||
        !replay.contains("objective_unit") || !replay["objective_unit"].is_string() ||
        !replay.contains("integration") || !optional_string(replay["integration"]) ||
        !replay.contains("control_hold") || !optional_string(replay["control_hold"]) ||
        !replay.contains("controls") || !finite_history(replay["controls"]) ||
        !replay.contains("states") || !finite_history(replay["states"]) ||
        !replay.contains("original_objective") || !replay.contains("replay_time_ns") ||
        !replay["replay_time_ns"].is_number_integer() || !replay.contains("missing_prerequisites") ||
        !string_array(replay["missing_prerequisites"]) || !replay.contains("diagnostics") ||
        !replay["diagnostics"].is_array() ||
        (version_two && (!replay.contains("numerical_policy") ||
            !numerical_policy_document(replay["numerical_policy"]) ||
            !replay.contains("integration_residual") ||
            !integration_residual_document(replay["integration_residual"]))) ||
        (version_three && (!replay.contains("integration_limits") ||
            !integration_limits_document(replay["integration_limits"]) ||
            !replay.contains("integration_receipts") || !replay["integration_receipts"].is_array()))) return false;
    if (!replay["replay_time_ns"].is_number_unsigned() &&
        replay["replay_time_ns"].get<std::int64_t>() < 0) return false;
    const auto& plant = replay["plant"];
    for (const char* field : {"name", "version", "source"})
        if (!plant.contains(field) || !plant[field].is_string()) return false;
    for (const auto& parameter : replay["parameters"])
        if (!parameter.is_object() || !parameter.contains("name") || !parameter["name"].is_string() ||
            !parameter.contains("value") || !finite_number(parameter["value"]) ||
            !parameter.contains("unit") || !parameter["unit"].is_string()) return false;
    if (!replay["initial_state"].is_null() && !finite_vector(replay["initial_state"])) return false;
    if (version_two) {
        const auto residual_status = replay["integration_residual"]["status"].get<std::string>();
        if (replay["integration"].is_null()) {
            if (residual_status != "unavailable") return false;
        } else {
            const auto method = replay["integration"].get<std::string>();
            if ((method != "exact_discrete_map" && method != "adaptive_rk4_step_doubling") ||
                (method == "exact_discrete_map") != (residual_status == "not_applicable")) return false;
        }
    }
    if (version_three && replay["integration"].is_string()) {
        const auto method = replay["integration"].get<std::string>();
        const auto& receipts = replay["integration_receipts"];
        if (method == "exact_discrete_map" && (!replay["integration_limits"].is_null() || !receipts.empty())) return false;
        if (method == "adaptive_rk4_step_doubling") {
            const bool has_limits = !replay["integration_limits"].is_null();
            const auto residual_status = replay["integration_residual"]["status"].get<std::string>();
            if ((!has_limits && (!receipts.empty() || residual_status != "unavailable" ||
                    replay["status"] == "complete")) || receipts.size() > linear_intervals) return false;
            std::size_t measurement_index = 0;
            for (std::size_t interval = 0; interval < receipts.size(); ++interval) {
                if (!has_limits) return false;
                const auto& receipt = receipts[interval];
                if (!receipt.is_object() || receipt.size() != 3 ||
                    !receipt.contains("accepted_steps") || !receipt["accepted_steps"].is_number_unsigned() ||
                    !receipt.contains("rejected_steps") || !receipt["rejected_steps"].is_number_unsigned() ||
                    !receipt.contains("max_accepted_local_error_estimates") ||
                    !finite_vector(receipt["max_accepted_local_error_estimates"]) ||
                    receipt["max_accepted_local_error_estimates"].size() != state_dimensions) return false;
                const auto accepted = receipt["accepted_steps"].get<std::uint64_t>();
                const auto rejected = receipt["rejected_steps"].get<std::uint64_t>();
                const auto budget = replay["integration_limits"]["max_attempts_per_interval"].get<std::uint64_t>();
                if (accepted == 0 || accepted > budget || rejected > budget-accepted) return false;
                for (std::size_t coordinate = 0; coordinate < state_dimensions; ++coordinate) {
                    const auto& measurements = replay["integration_residual"]["measurements"];
                    if (measurement_index >= measurements.size()) return false;
                    const auto& measurement = measurements[measurement_index++];
                    const auto expected_name = "interval[" + std::to_string(interval) + "].state[" +
                        std::to_string(coordinate) + "]";
                    if (measurement["name"] != expected_name ||
                        measurement["value"] != receipt["max_accepted_local_error_estimates"][coordinate] ||
                        measurement["unit"] != replay["state_units"][coordinate]) return false;
                }
            }
            const auto expected_measurements = receipts.size() * state_dimensions;
            const bool has_estimates = !receipts.empty();
            if (measurement_index != expected_measurements ||
                (has_estimates != (replay["integration_residual"]["status"] == "available"))) return false;
        }
    }
    for (const auto& diagnostic : replay["diagnostics"])
        if (!diagnostic.is_object() || !diagnostic.contains("code") || !diagnostic["code"].is_string() ||
            !diagnostic.contains("field") || !diagnostic["field"].is_string() ||
            !diagnostic.contains("explanation") || !diagnostic["explanation"].is_string()) return false;
    const auto status = replay["status"].get<std::string>();
    if (status != "complete" && status != "unavailable" && status != "invalid_input" &&
        status != "numerical_failure" && status != "callback_failure" && status != "cancelled" &&
        status != "resource_limit") return false;
    const auto& controls = replay["controls"];
    const auto& states = replay["states"];
    if (std::any_of(controls.begin(), controls.end(), [control_dimensions](const auto& row) {
            return row.size() != control_dimensions;
        }) || std::any_of(states.begin(), states.end(), [state_dimensions](const auto& row) {
            return row.size() != state_dimensions;
        }) || controls.size() > linear_intervals || states.size() > replay["times"].size()) return false;
    if (status == "complete")
        return replay["state_units"].size() == state_dimensions &&
            replay["control_units"].size() == control_dimensions &&
            controls.size() == linear_intervals && states.size() == controls.size() + 1 &&
            states.size() == replay["times"].size() && !replay["time_unit"].get<std::string>().empty() &&
            !replay["original_objective"].is_null() && finite_number(replay["original_objective"]) &&
            replay["missing_prerequisites"].empty() &&
            (version_two ? (replay["integration"].is_string() &&
                !replay["integration"].get<std::string>().empty()) :
                replay["integration"] == "exact_discrete_map") &&
            (!version_three || replay["integration"].get<std::string>() != "adaptive_rk4_step_doubling" ||
                (replay["integration_receipts"].size() == linear_intervals &&
                 replay["integration_receipts"].size() == controls.size() &&
                 replay["integration_residual"]["status"] == "available")) &&
            replay["control_hold"] == "constant_on_interval";
    if (status == "unavailable" && replay["missing_prerequisites"].empty()) return false;
    return replay["original_objective"].is_null();
}

bool comparison_document(const Json& document) {
    const auto schema = document.is_object() && document.contains("schema") && document["schema"].is_string()
        ? document["schema"].get<std::string>() : std::string{};
    const bool version_three = schema == "csl.viz04-replay-comparison/3";
    const bool version_two = version_three || schema == "csl.viz04-replay-comparison/2";
    if (!document.is_object() || (!version_two && schema != "csl.viz04-replay-comparison/1") ||
        !document.contains("source_run") || !document["source_run"].is_object() ||
        !document.contains("problem") || !document["problem"].is_string() || document["problem"].get<std::string>().empty() ||
        !document.contains("strategy") || !document["strategy"].is_string() || document["strategy"].get<std::string>().empty() ||
        !document.contains("strategy_version") || !document["strategy_version"].is_string() ||
        document["strategy_version"].get<std::string>().empty() ||
        !document.contains("state_axis") || !document["state_axis"].is_object() ||
        !document.contains("state_coordinates") || !annotation_array(document["state_coordinates"]) ||
        !document.contains("control_coordinates") || !annotation_array(document["control_coordinates"]) ||
        !document.contains("linear_objective_convention") || !objective_document(document["linear_objective_convention"]) ||
        !document.contains("linear_objective_unit") || !optional_string(document["linear_objective_unit"]) ||
        !document.contains("witnesses") || !document["witnesses"].is_array() || document["witnesses"].empty()) return false;
    const auto& source = document["source_run"];
    if (!source.contains("run") || !source["run"].is_string() || source["run"].get<std::string>().empty() ||
        !source.contains("content_sha256") || !source["content_sha256"].is_string()) return false;
    const auto digest = source["content_sha256"].get<std::string>();
    if (digest.size() != 64 || !std::all_of(digest.begin(), digest.end(), [](unsigned char c) {
            return std::isxdigit(c) != 0;
        })) return false;
    const auto& axis = document["state_axis"];
    if (!axis.contains("kind") || !axis["kind"].is_string() ||
        (axis["kind"] != "stage" && axis["kind"] != "physical_time") ||
        !axis.contains("points") || !finite_vector(axis["points"]) ||
        !axis.contains("interval_ends") || !finite_vector(axis["interval_ends"]) ||
        !axis.contains("unit") || !optional_string(axis["unit"]) ||
        document["state_coordinates"].empty()) return false;
    std::set<std::uint64_t> source_ordinals;
    for (const auto& witness : document["witnesses"]) {
        if (!witness.is_object() || !witness.contains("source_ordinal") ||
            !witness["source_ordinal"].is_number_unsigned() || !witness.contains("strategy") ||
            !witness["strategy"].is_string() || !witness.contains("strategy_version") ||
            !witness["strategy_version"].is_string() || !witness.contains("policy_class") ||
            !witness["policy_class"].is_string() ||
            (witness["policy_class"] != "nominal_reference" &&
                witness["policy_class"] != "frozen_coefficient_regulator" &&
                witness["policy_class"] != "selected_linear_witness") ||
            !witness.contains("claims") || !witness["claims"].is_object() ||
            !witness.contains("linear_states") ||
            !finite_history(witness["linear_states"]) || !witness.contains("linear_controls") ||
            !finite_history(witness["linear_controls"]) || !witness.contains("linear_objective") ||
            !finite_number(witness["linear_objective"]) || !witness.contains("linear_evidence") ||
            !evidence_document(witness["linear_evidence"]) || !witness.contains("replay") ||
            !replay_document(witness["replay"], document["state_coordinates"].size(),
                document["control_coordinates"].size(), witness["linear_controls"].size(), version_two, version_three) ||
            witness["linear_states"].size() != witness["linear_controls"].size() + 1 ||
            witness["linear_states"].size() < 2 ||
            witness["linear_states"].size() != axis["points"].size() ||
            witness["strategy"] != document["strategy"] ||
            witness["strategy_version"] != document["strategy_version"]) return false;
        if (!source_ordinals.insert(witness["source_ordinal"].get<std::uint64_t>()).second) return false;
        const auto& claims = witness["claims"];
        const auto check_status_valid = [](const Json& value) {
            return value.is_string() && (value == "not_checked" || value == "numerical_pass" ||
                value == "violation" || value == "invalid_input" || value == "unsupported");
        };
        for (const char* field : {"nonlinear_feasibility", "nonlinear_objective_quality",
                "nonlinear_global_optimality"})
            if (!claims.contains(field) || !check_status_valid(claims[field]) ||
                claims[field] != "not_checked") return false;
        const auto& replay = witness["replay"];
        const auto& linear_states = witness["linear_states"];
        const auto& linear_controls = witness["linear_controls"];
        if (std::any_of(linear_states.begin(), linear_states.end(), [&](const auto& row) {
                return row.size() != document["state_coordinates"].size();
            }) || std::any_of(linear_controls.begin(), linear_controls.end(), [&](const auto& row) {
                return row.size() != document["control_coordinates"].size();
            })) return false;
        const auto& replay_controls = replay["controls"];
        if (replay_controls.size() > linear_controls.size()) return false;
        for (std::size_t i = 0; i < replay_controls.size(); ++i)
            if (replay_controls[i] != linear_controls[i]) return false;
        if (replay["status"] == "complete" && replay_controls != linear_controls) return false;
        if (replay_controls.size() != linear_controls.size() &&
            std::find(replay["missing_prerequisites"].begin(), replay["missing_prerequisites"].end(),
                "controls.complete_history") == replay["missing_prerequisites"].end()) return false;
        if (replay["status"] == "complete" && axis["kind"] == "physical_time" &&
            (replay["times"] != axis["points"] ||
                (axis["unit"].is_string() && replay["time_unit"] != axis["unit"]))) return false;
    }
    return true;
}
}

artifacts::ArtifactResult<ReplayComparison> associate_replays(const Problem& source,
    const artifacts::PlotData& plot, artifacts::RunRecordRef source_run,
    std::span<const simulation::ReplayRecord> replays,
    std::optional<std::string> linear_objective_unit) {
    if (source.id != plot.problem)
        return error(artifacts::ArtifactErrorCode::identity, "problem", "Plot data belongs to another linear problem");
    if (source_run.run != plot.run)
        return error(artifacts::ArtifactErrorCode::identity, "source_run.run", "Run reference does not match plot data");
    if (plot.paths.empty())
        return error(artifacts::ArtifactErrorCode::reference, "witnesses", "Replay association requires at least one selected linear path");
    if (plot.paths.size() != replays.size())
        return error(artifacts::ArtifactErrorCode::reference, "witnesses", "There must be one replay record per selected linear path");
    if (linear_objective_unit && linear_objective_unit->empty())
        return error(artifacts::ArtifactErrorCode::invalid_input, "linear_objective_unit", "A declared objective unit cannot be empty");
    ReplayComparison result{source_run, plot.problem, plot.state_axis, plot.states, plot.controls,
        source.objective, std::move(linear_objective_unit), {}};
    std::set<std::size_t> ordinals;
    for (std::size_t index = 0; index < plot.paths.size(); ++index) {
        const auto& linear = plot.paths[index];
        const auto& nonlinear = replays[index];
        if (linear.run != source_run.run || linear.strategy != plot.strategy ||
            linear.strategy_version != plot.strategy_version || !ordinals.insert(linear.source_ordinal).second)
            return error(artifacts::ArtifactErrorCode::identity, "witnesses[" + std::to_string(index) + "]",
                "Linear path identity is not a unique selected path from the referenced run");
        if (linear.states.size() < 2 ||
            linear.controls.size() + 1 != linear.states.size() ||
            plot.state_axis.points.size() != linear.states.size() ||
            !valid_history(linear.states, plot.states.coordinates.size()) ||
            !valid_history(linear.controls, plot.controls.coordinates.size()))
            return error(artifacts::ArtifactErrorCode::invalid_input, "witnesses[" + std::to_string(index) + "]",
                "Linear witness histories must be complete, finite, and match the declared coordinates");
        const bool controls_are_prefix = nonlinear.controls.size() <= linear.controls.size() &&
            std::equal(nonlinear.controls.begin(), nonlinear.controls.end(), linear.controls.begin());
        const bool controls_are_complete = nonlinear.controls.size() == linear.controls.size();
        if (!controls_are_prefix || (nonlinear.status == simulation::ReplayStatus::complete && !controls_are_complete) ||
            (!controls_are_complete && std::find(nonlinear.missing_prerequisites.begin(),
                nonlinear.missing_prerequisites.end(), "controls.complete_history") == nonlinear.missing_prerequisites.end()))
            return error(artifacts::ArtifactErrorCode::reference, "witnesses[" + std::to_string(index) + "].replay.controls",
                "Replay controls must match the selected witness prefix, and a partial history must name its missing controls");
        if (!result.witnesses.empty() && !same_declaration(result.witnesses.front().nonlinear, nonlinear))
            return error(artifacts::ArtifactErrorCode::identity, "witnesses[" + std::to_string(index) + "].replay.plant",
                "All compared witness replays must use the same declared plant and physical grid");
        if (nonlinear.declared_initial_state && !linear.states.empty() &&
            *nonlinear.declared_initial_state != linear.states.front())
            return error(artifacts::ArtifactErrorCode::reference, "witnesses[" + std::to_string(index) + "].replay.initial_state",
                "Replay must start from the selected linear witness initial state");
        if (nonlinear.state_units.size() != plot.states.coordinates.size() ||
            nonlinear.control_units.size() != plot.controls.coordinates.size())
            return error(artifacts::ArtifactErrorCode::invalid_input, "witnesses[" + std::to_string(index) + "].replay.units",
                "Replay units must match the state and control dimensions");
        for (std::size_t coordinate = 0; coordinate < nonlinear.state_units.size(); ++coordinate) {
            const auto& unit = plot.states.coordinates[coordinate].unit;
            if (unit && *unit != nonlinear.state_units[coordinate])
                return error(artifacts::ArtifactErrorCode::reference, "witnesses[" + std::to_string(index) + "].replay.state_units",
                    "Replay state units disagree with the linear plot coordinates");
        }
        for (std::size_t coordinate = 0; coordinate < nonlinear.control_units.size(); ++coordinate) {
            const auto& unit = plot.controls.coordinates[coordinate].unit;
            if (unit && *unit != nonlinear.control_units[coordinate])
                return error(artifacts::ArtifactErrorCode::reference, "witnesses[" + std::to_string(index) + "].replay.control_units",
                    "Replay control units disagree with the linear plot coordinates");
        }
        if (nonlinear.status == simulation::ReplayStatus::complete) {
            if (nonlinear.states.size() != linear.states.size() || nonlinear.times.size() != nonlinear.states.size() ||
                !nonlinear.original_objective || nonlinear.time_unit.empty() ||
                !valid_history(nonlinear.states, nonlinear.state_units.size()))
                return error(artifacts::ArtifactErrorCode::invalid_input, "witnesses[" + std::to_string(index) + "].replay",
                    "A completed replay needs one finite state per physical time and a plant objective");
            if (plot.state_axis.kind == artifacts::PlotAxis::Kind::physical_time &&
                (plot.state_axis.points != nonlinear.times ||
                    (plot.state_axis.unit && *plot.state_axis.unit != nonlinear.time_unit)))
                return error(artifacts::ArtifactErrorCode::reference, "witnesses[" + std::to_string(index) + "].replay.times",
                    "Replay physical times must match the linear witness axis and unit");
        } else {
            if (nonlinear.original_objective)
                return error(artifacts::ArtifactErrorCode::invalid_input, "witnesses[" + std::to_string(index) + "].replay.objective",
                    "An incomplete replay cannot claim a completed plant objective");
            if (nonlinear.status == simulation::ReplayStatus::unavailable && nonlinear.missing_prerequisites.empty())
                return error(artifacts::ArtifactErrorCode::invalid_input, "witnesses[" + std::to_string(index) + "].replay.missing_prerequisites",
                    "Unavailable replay must name its missing prerequisites");
            if (nonlinear.states.size() > linear.states.size() ||
                !valid_history(nonlinear.states, nonlinear.state_units.size()))
                return error(artifacts::ArtifactErrorCode::invalid_input, "witnesses[" + std::to_string(index) + "].replay.states",
                    "An incomplete replay may retain only a finite state prefix");
        }
        result.witnesses.push_back({linear, nonlinear,
            ReplayPolicyClass::selected_linear_witness, {}});
    }
    return result;
}

artifacts::ArtifactResult<ReplayTrajectoryPair> project_replay_trajectories(
    const ReplayComparison& comparison, artifacts::CoordinatePair pair,
    std::array<artifacts::CoordinateAnnotation, 2> coordinate_labels) {
    if (pair.first == pair.second || pair.first >= comparison.state_coordinates.coordinates.size() ||
        pair.second >= comparison.state_coordinates.coordinates.size())
        return error(artifacts::ArtifactErrorCode::invalid_input, "coordinates",
            "A replay projection needs two distinct declared state coordinates");
    ReplayTrajectoryPair result{comparison.source_run, comparison.problem, comparison.state_axis,
        std::move(coordinate_labels), {}};
    for (const auto& association : comparison.witnesses) {
        const auto& replay = association.nonlinear;
        ReplayTrajectoryPath path{association.linear.source_ordinal, association.linear.objective,
            association.linear.evidence.optimality, replay.status, replay.original_objective,
            replay.objective_unit, replay.missing_prerequisites, {},
            association.policy_class, association.claims};
        for (const auto& state : replay.states) {
            if (pair.first >= state.size() || pair.second >= state.size())
                return error(artifacts::ArtifactErrorCode::invalid_input, "coordinates",
                    "Replay state does not contain the requested projection coordinates");
            path.points.push_back({state[pair.first], state[pair.second]});
        }
        if (replay.status == simulation::ReplayStatus::complete) {
            result.state_axis.kind = artifacts::PlotAxis::Kind::physical_time;
            result.state_axis.points = replay.times;
            result.state_axis.interval_ends.clear();
            result.state_axis.unit = replay.time_unit;
        }
        result.paths.push_back(std::move(path));
    }
    return result;
}

artifacts::ArtifactResult<problem::ResolvedContent> encode_replay_comparison(
    const ReplayComparison& comparison, artifacts::EncodeLimits limits) {
    try {
        const auto document = comparison_json(comparison);
        if (!comparison_document(document))
            return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison",
                "Comparison does not satisfy the replay artifact schema");
        const auto text = document.dump(2, ' ', false, Json::error_handler_t::strict) + "\n";
        if (text.size() > limits.bytes)
            return error(artifacts::ArtifactErrorCode::limit, "replay_comparison", "Replay artifact exceeds its byte limit");
        auto content = problem::snapshot_content({reinterpret_cast<const std::byte*>(text.data()), text.size()});
        if (const auto* failure = std::get_if<Diagnostic>(&content))
            return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison", failure->explanation);
        return std::get<problem::ResolvedContent>(std::move(content));
    } catch (const std::length_error& exception) {
        return error(artifacts::ArtifactErrorCode::limit, "replay_comparison", exception.what());
    } catch (const std::exception& exception) {
        return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison", exception.what());
    }
}

artifacts::ArtifactResult<problem::ResolvedContent> decode_replay_comparison(
    std::string_view text, artifacts::DecodeLimits limits) {
    try {
        if (text.size() > limits.bytes)
            return error(artifacts::ArtifactErrorCode::limit, "replay_comparison", "Replay artifact exceeds its byte limit");
        std::vector<std::set<std::string>> object_keys;
        std::uint64_t nodes = 0, string_bytes = 0;
        std::size_t depth = 0;
        auto document = Json::parse(text.begin(), text.end(), [&](int, Json::parse_event_t event, Json& value) {
            const bool starts_container = event == Json::parse_event_t::object_start ||
                event == Json::parse_event_t::array_start;
            const bool ends_container = event == Json::parse_event_t::object_end ||
                event == Json::parse_event_t::array_end;
            if (starts_container) {
                if (++nodes > limits.nodes || ++depth > limits.depth)
                    throw std::length_error("Replay artifact exceeds its node or nesting limit");
            } else if (event == Json::parse_event_t::value) {
                if (++nodes > limits.nodes)
                    throw std::length_error("Replay artifact exceeds its node limit");
            }
            if (value.is_string()) {
                const auto size = value.get_ref<const std::string&>().size();
                if (size > limits.string_bytes - std::min(string_bytes, limits.string_bytes))
                    throw std::length_error("Replay artifact exceeds its string limit");
                string_bytes += size;
            }
            if (event == Json::parse_event_t::object_start) object_keys.emplace_back();
            else if (event == Json::parse_event_t::key) {
                if (++nodes > limits.nodes)
                    throw std::length_error("Replay artifact exceeds its node limit");
                if (object_keys.empty() || !object_keys.back().insert(value.get<std::string>()).second)
                    throw std::runtime_error("Replay artifact has a duplicate JSON key");
            } else if (event == Json::parse_event_t::object_end && !object_keys.empty()) object_keys.pop_back();
            if (ends_container && depth > 0) --depth;
            return true;
        });
        if (!comparison_document(document))
            return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison.schema",
                "Document does not match csl.viz04-replay-comparison/1, /2 or /3");
        auto content = problem::snapshot_content({reinterpret_cast<const std::byte*>(text.data()), text.size()});
        if (const auto* failure = std::get_if<Diagnostic>(&content))
            return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison", failure->explanation);
        return std::get<problem::ResolvedContent>(std::move(content));
    } catch (const std::length_error& exception) {
        return error(artifacts::ArtifactErrorCode::limit, "replay_comparison", exception.what());
    } catch (const std::exception& exception) {
        return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison", exception.what());
    }
}

} // namespace csl::experiments
