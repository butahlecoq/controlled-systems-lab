#include <csl/experiments/replay_artifact.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
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
    Json integration = replay.integration ? Json("exact_discrete_map") : Json(nullptr);
    Json hold = replay.hold ? Json("constant_on_interval") : Json(nullptr);
    Json initial = replay.declared_initial_state ? Json(*replay.declared_initial_state) : Json(nullptr);
    Json objective = replay.original_objective ? Json(*replay.original_objective) : Json(nullptr);
    return {{"status", replay_status(replay.status)},
        {"plant", {{"name", replay.plant.name}, {"version", replay.plant.version}, {"source", replay.plant.source}}},
        {"parameters", std::move(parameters)}, {"initial_state", std::move(initial)},
        {"time_unit", replay.time_unit}, {"times", replay.times},
        {"state_units", replay.state_units}, {"control_units", replay.control_units},
        {"objective_name", replay.objective_name}, {"objective_unit", replay.objective_unit},
        {"integration", std::move(integration)}, {"control_hold", std::move(hold)},
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
    return {{"schema", "csl.viz04-replay-comparison/1"},
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
        a.integration == b.integration && a.hold == b.hold && a.numerical == b.numerical;
}

bool valid_history(const std::vector<Vector>& history, std::size_t dimension) {
    return std::all_of(history.begin(), history.end(), [dimension](const auto& row) {
        return row.size() == dimension && std::all_of(row.begin(), row.end(),
            [](double value) { return std::isfinite(value); });
    });
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
        result.witnesses.push_back({linear, nonlinear});
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
            replay.objective_unit, replay.missing_prerequisites, {}};
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
        const auto text = comparison_json(comparison).dump(2, ' ', false, Json::error_handler_t::strict) + "\n";
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
        if (!document.is_object() || document.value("schema", std::string{}) != "csl.viz04-replay-comparison/1" ||
            !document.contains("source_run") || !document.at("source_run").is_object() ||
            !document.at("source_run").contains("run") || !document.at("source_run").at("run").is_string() ||
            document.at("source_run").at("run").get<std::string>().empty() ||
            !document.at("source_run").contains("content_sha256") ||
            !document.at("source_run").at("content_sha256").is_string() ||
            document.at("source_run").at("content_sha256").get<std::string>().size() != 64 ||
            !document.contains("witnesses") || !document.at("witnesses").is_array())
            return error(artifacts::ArtifactErrorCode::invalid_input, "replay_comparison.schema",
                "Document does not match csl.viz04-replay-comparison/1");
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
