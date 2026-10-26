#include <csl/artifacts/stage_projection_batch.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/sets/data.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <span>

namespace csl::artifacts {
namespace {
using Json = nlohmann::json;

ArtifactError error(ArtifactErrorCode code, std::string path, std::string message) {
    return {code, std::move(path), std::move(message)};
}
const char* relation(SetRelation value) {
    switch (value) {
    case SetRelation::equivalent: return "equivalent";
    case SetRelation::inner: return "inner";
    case SetRelation::outer: return "outer";
    case SetRelation::heuristic: return "heuristic";
    }
    return "unknown";
}
const char* assurance(Assurance value) { return value == Assurance::validated ? "validated" : "numerical"; }
const char* stop_reason(StopReason value) {
    switch (value) {
    case StopReason::cancelled: return "cancelled";
    case StopReason::deadline_expired: return "deadline_expired";
    case StopReason::resource_limit: return "resource_limit";
    case StopReason::numerical_failure: return "numerical_failure";
    }
    return "unknown";
}
bool valid_digest(std::string_view value) {
    return value.size() == 64 && std::all_of(value.begin(), value.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
Json point(double x, double y) { return Json::array({x, y}); }
Json coordinate(const CoordinateAnnotation& value, std::size_t index) {
    Json result{{"id", "x" + std::to_string(index)},
        {"name", value.label.value_or("x" + std::to_string(index))},
        {"unit", value.unit ? Json(*value.unit) : Json(nullptr)}};
    if (value.target) result["target"] = {{"value", value.target->value}, {"source", value.target->source}};
    if (value.bounds) result["bounds"] = {
        {"lower", {{"value", value.bounds->first.value}, {"source", value.bounds->first.source}}},
        {"upper", {{"value", value.bounds->second.value}, {"source", value.bounds->second.source}}}};
    return result;
}
Json matrix_rows(const numeric::MatrixView& matrix) {
    Json rows = Json::array();
    for (std::size_t i = 0; i < matrix.rows(); ++i) {
        Json row = Json::array();
        for (std::size_t j = 0; j < matrix.cols(); ++j) row.push_back(matrix(i, j));
        rows.push_back(std::move(row));
    }
    return rows;
}
Json support(const EvidenceSupport& value) {
    return std::visit([](const auto& item) -> Json {
        using T = std::decay_t<decltype(item)>;
        if constexpr (std::is_same_v<T, Unestablished>) return {{"kind", "unestablished"}};
        else if constexpr (std::is_same_v<T, NumericalCheck>) return {{"kind", "numerical_check"},
            {"absolute_tolerance", item.absolute_tolerance}, {"relative_tolerance", item.relative_tolerance},
            {"max_residual", item.max_residual}, {"verifier", item.verifier.value}};
        else if constexpr (std::is_same_v<T, SymbolicArgument>) return {{"kind", "symbolic_argument"},
            {"reference", item.reference}, {"assumptions", item.assumptions}};
        else if constexpr (std::is_same_v<T, CertificateReference>) return {{"kind", "unchecked_certificate_reference"},
            {"artifact", item.artifact}, {"verifier", item.verifier}};
        else return {{"kind", "exact_farkas_evidence"}, {"subject_problem", item.subject().problem.value},
            {"subject_program", item.subject().program.value}};
    }, value);
}
Json evidence(const PlotSetProjection& projection) {
    Json assumptions = projection.assumptions;
    return {{"request_id", projection.reference.identity.request.value},
        {"ideal_output_id", projection.reference.identity.ideal_output.value},
        {"scope", "set_relation"},
        {"input_set_ids", [&] { Json ids = Json::array(); for (const auto& id : projection.reference.inputs) ids.push_back(id.value); return ids; }()},
        {"support", support(projection.support)}, {"assumptions", std::move(assumptions)}};
}
Json failure_cause(const StageProjectionFailure& failure) {
    return std::visit([](const auto& cause) -> Json {
        using T = std::decay_t<decltype(cause)>;
        if constexpr (std::is_same_v<T, registry::Rejection> || std::is_same_v<T, Unsupported>) {
            const auto& diagnostics = cause.diagnostics;
            Json detail = Json::array();
            for (const auto& item : diagnostics)
                detail.push_back({{"field", item.field}, {"explanation", item.explanation}});
            return {{"kind", std::is_same_v<T, registry::Rejection> ? "rejected" : "unsupported"},
                {"explanation", diagnostics.empty() ? "No diagnostic was supplied." : diagnostics.front().explanation},
                {"diagnostics", std::move(detail)}};
        }
        else if constexpr (std::is_same_v<T, OperationStopped>)
            return {{"kind", "stopped"}, {"explanation", cause.diagnostics.empty() ? "Geometry operation stopped." : cause.diagnostics},
                {"stop_reason", stop_reason(cause.reason)}, {"stop_diagnostics", cause.diagnostics}};
        else return {{"kind", "artifact_error"}, {"explanation", cause.message}};
    }, failure.cause);
}

ArtifactResult<Json> geometry(const SetHandle& handle, std::string component_id) {
    const auto native = sets::from_handle(handle);
    if (const auto* issue = std::get_if<Diagnostic>(&native))
        return error(ArtifactErrorCode::unsupported, "geometry", issue->explanation);
    const auto represented = std::get<sets::SetData>(native).representation();
    Json output{{"component_id", std::move(component_id)}};
    if (std::holds_alternative<sets::EmptyRepresentation>(represented)) {
        output["kind"] = "empty";
        return output;
    }
    if (std::holds_alternative<sets::UniversalRepresentation>(represented)) {
        output["kind"] = "unbounded";
        output["vertices"] = Json::array({point(0, 0)});
        output["rays"] = Json::array({point(1, 0), point(-1, 0), point(0, 1), point(0, -1)});
        return output;
    }
    if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&represented)) {
        if (singleton->point.size() != 2) return error(ArtifactErrorCode::reference, "geometry", "Expected two-dimensional singleton");
        if (!std::isfinite(singleton->point[0]) || !std::isfinite(singleton->point[1]))
            return error(ArtifactErrorCode::invalid_input, "geometry.point", "Nonfinite coordinate");
        output["kind"] = "point";
        output["vertices"] = Json::array({point(singleton->point[0], singleton->point[1])});
        return output;
    }
    const auto* v = std::get_if<sets::VRepresentation>(&represented);
    if (!v) return error(ArtifactErrorCode::unsupported, "geometry", "Only native V, empty, universal and singleton projections can be saved");
    if (v->vertices.cols() != 2 || v->rays.cols() != 2)
        return error(ArtifactErrorCode::reference, "geometry", "Expected a two-dimensional V representation");
    for (std::size_t i = 0; i < v->vertices.rows(); ++i)
        for (std::size_t j = 0; j < 2; ++j)
            if (!std::isfinite(v->vertices(i, j))) return error(ArtifactErrorCode::invalid_input, "geometry.vertices", "Nonfinite coordinate");
    for (std::size_t i = 0; i < v->rays.rows(); ++i)
        for (std::size_t j = 0; j < 2; ++j)
            if (!std::isfinite(v->rays(i, j))) return error(ArtifactErrorCode::invalid_input, "geometry.rays", "Nonfinite coordinate");
    output["vertices"] = matrix_rows(v->vertices);
    output["rays"] = matrix_rows(v->rays);
    output["interpretation"] = "conv_vertices_plus_cone_rays";
    if (v->vertices.rows() == 0) output["kind"] = "empty";
    else {
        bool unbounded = false;
        for (std::size_t i = 0; i < v->rays.rows(); ++i)
            unbounded = unbounded || v->rays(i, 0) != 0.0 || v->rays(i, 1) != 0.0;
        if (unbounded) {
            output["kind"] = "unbounded";
            return output;
        }
        if (v->vertices.rows() == 1) {
            output["kind"] = "point";
            return output;
        }
        const double x0 = v->vertices(0, 0), y0 = v->vertices(0, 1);
        std::size_t second = 1;
        while (second < v->vertices.rows() && v->vertices(second, 0) == x0 && v->vertices(second, 1) == y0) ++second;
        bool area = false;
        if (second < v->vertices.rows()) {
            const double dx = v->vertices(second, 0) - x0;
            const double dy = v->vertices(second, 1) - y0;
            for (std::size_t i = second + 1; i < v->vertices.rows(); ++i) {
                const double ex = v->vertices(i, 0) - x0;
                const double ey = v->vertices(i, 1) - y0;
                if (dx * ey - dy * ex != 0.0) { area = true; break; }
            }
        }
        output["kind"] = area ? "polygon" : second == v->vertices.rows() ? "point" : "segment";
    }
    return output;
}
}

ArtifactResult<std::string> encode_stage_projection_batch_json(
    const StageProjectionBatchIdentity& identity, const StageProjectionBatchCapture& batch) {
    if (identity.run.value.empty() || identity.route.empty() || identity.source_record_schema.empty() ||
        batch.problem.value.empty() || batch.request.value.empty() || identity.state_coordinates.size() < 2 ||
        identity.requested_coordinate_pairs.empty() || !valid_digest(identity.source_record_sha256))
        return error(ArtifactErrorCode::invalid_input, "identity", "Run, route, source record, coordinates, pairs, and a lowercase SHA-256 are required");
    if (identity.stage_axis.points.empty()) return error(ArtifactErrorCode::invalid_input, "stage_axis", "At least one stage is required");
    if (identity.stage_axis.points.size() > std::vector<StageProjectionRecord>{}.max_size() / identity.requested_coordinate_pairs.size())
        return error(ArtifactErrorCode::limit, "records", "Stage/pair grid exceeds supported container size");
    for (std::size_t i = 0; i < identity.stage_axis.points.size(); ++i)
        if (!std::isfinite(identity.stage_axis.points[i]) || (i && identity.stage_axis.points[i] <= identity.stage_axis.points[i - 1]))
            return error(ArtifactErrorCode::invalid_input, "stage_axis.points", "Stage axis must be finite and strictly increasing");
    if (identity.stage_axis.kind == PlotAxis::Kind::stage)
        for (std::size_t i = 0; i < identity.stage_axis.points.size(); ++i)
            if (identity.stage_axis.points[i] != static_cast<double>(i))
                return error(ArtifactErrorCode::invalid_input, "stage_axis.points", "Stage axis must be the contiguous R0-based sequence");
    for (std::size_t i = 0; i < identity.state_coordinates.size(); ++i) {
        const auto& coordinate = identity.state_coordinates[i];
        if (coordinate.target && (!std::isfinite(coordinate.target->value) || coordinate.target->source.empty()))
            return error(ArtifactErrorCode::invalid_input, "coordinates[" + std::to_string(i) + "].target", "Coordinate target must be finite and source-attributed");
        if (coordinate.bounds && (!std::isfinite(coordinate.bounds->first.value) || !std::isfinite(coordinate.bounds->second.value) ||
            coordinate.bounds->first.source.empty() || coordinate.bounds->second.source.empty() ||
            coordinate.bounds->first.value > coordinate.bounds->second.value))
            return error(ArtifactErrorCode::invalid_input, "coordinates[" + std::to_string(i) + "].bounds", "Coordinate bounds must be finite, ordered, and source-attributed");
    }
    for (std::size_t i = 0; i < identity.requested_coordinate_pairs.size(); ++i) {
        const auto [first, second] = identity.requested_coordinate_pairs[i];
        if (first >= identity.state_coordinates.size() || second >= identity.state_coordinates.size() || first == second)
            return error(ArtifactErrorCode::reference, "requested_pairs[" + std::to_string(i) + "]", "Coordinate pair is out of range or repeated");
        if (std::find(identity.requested_coordinate_pairs.begin(), identity.requested_coordinate_pairs.begin() + static_cast<std::ptrdiff_t>(i), identity.requested_coordinate_pairs[i]) !=
            identity.requested_coordinate_pairs.begin() + static_cast<std::ptrdiff_t>(i))
            return error(ArtifactErrorCode::reference, "requested_pairs", "Duplicate ordered coordinate pair");
    }
    if (batch.records.size() != identity.stage_axis.points.size() * identity.requested_coordinate_pairs.size())
        return error(ArtifactErrorCode::reference, "records", "Capture does not contain the complete stage/pair grid");

    Json coordinates = Json::array(), pairs = Json::array(), records = Json::array(), trajectories = Json::array();
    for (std::size_t i = 0; i < identity.state_coordinates.size(); ++i) coordinates.push_back(coordinate(identity.state_coordinates[i], i));
    for (const auto& pair : identity.requested_coordinate_pairs) pairs.push_back(pair);
    for (std::size_t i = 0; i < identity.trajectory_series.size(); ++i) {
        const auto& trajectory = identity.trajectory_series[i];
        if (trajectory.source_run != identity.run || trajectory.coordinates[0] >= identity.state_coordinates.size() ||
            trajectory.coordinates[1] >= identity.state_coordinates.size() || trajectory.coordinates[0] == trajectory.coordinates[1] ||
            trajectory.points.size() != identity.stage_axis.points.size() || trajectory.evidence.empty())
            return error(ArtifactErrorCode::reference, "trajectory_series[" + std::to_string(i) + "]", "Trajectory identity, coordinate pair, evidence, or stage count is invalid");
        Json points = Json::array();
        for (const auto& value : trajectory.points) {
            if (!std::isfinite(value[0]) || !std::isfinite(value[1]))
                return error(ArtifactErrorCode::invalid_input, "trajectory_series[" + std::to_string(i) + "].points", "Trajectory coordinates must be finite");
            points.push_back(value);
        }
        trajectories.push_back({{"kind", "trajectory"}, {"source_run_id", trajectory.source_run.value},
            {"coordinate_ids", {"x" + std::to_string(trajectory.coordinates[0]), "x" + std::to_string(trajectory.coordinates[1])}},
            {"points", std::move(points)}, {"evidence", trajectory.evidence}});
    }
    for (std::size_t s = 0; s < identity.stage_axis.points.size(); ++s) {
        for (std::size_t p = 0; p < identity.requested_coordinate_pairs.size(); ++p) {
            const auto& row = batch.records[s * identity.requested_coordinate_pairs.size() + p];
            if (row.stage.value != s || row.pair.first != identity.requested_coordinate_pairs[p][0] ||
                row.pair.second != identity.requested_coordinate_pairs[p][1] ||
                row.pair.first >= identity.state_coordinates.size() || row.pair.second >= identity.state_coordinates.size() ||
                row.pair.coordinates[0].label != identity.state_coordinates[row.pair.first].label ||
                row.pair.coordinates[0].unit != identity.state_coordinates[row.pair.first].unit ||
                row.pair.coordinates[1].label != identity.state_coordinates[row.pair.second].label ||
                row.pair.coordinates[1].unit != identity.state_coordinates[row.pair.second].unit)
                return error(ArtifactErrorCode::reference, "records", "Capture ordering or resolved coordinate identity does not match request");
            if (identity.stage_axis.kind == PlotAxis::Kind::physical_time &&
                (!row.physical_time || *row.physical_time != identity.stage_axis.points[s]))
                return error(ArtifactErrorCode::reference, "records.physical_time", "Physical time must align with its stage axis point");
            Json source_ids = Json::array();
            for (const auto& evidence : row.source_evidence) {
                if (evidence.stage.value != row.stage.value) return error(ArtifactErrorCode::reference, "records.source_evidence", "Source evidence stage mismatch");
                source_ids.push_back(evidence.source_set.value);
            }
            Json outcome;
            if (const auto* success = std::get_if<StageProjectionSuccess>(&row.outcome)) {
                if (success->projection.problem != batch.problem || success->projection.stage.value != row.stage.value)
                    return error(ArtifactErrorCode::identity, "records.outcome", "Projection identity does not match batch");
                if (!success->projection.provider.actual)
                    return error(ArtifactErrorCode::identity, "records.outcome.provider", "Successful projection has no actual provider identity");
                source_ids = Json::array();
                Json components = Json::array(), projection_evidence = Json::array();
                std::vector<std::string> component_ids;
                std::vector<SetHandle> component_sets{success->projection.projected_relation};
                for (const auto& component : success->additional_components) component_sets.push_back(component);
                for (const auto& component : component_sets) {
                    if (component.id.value.empty() ||
                        std::find(component_ids.begin(), component_ids.end(), component.id.value) != component_ids.end())
                        return error(ArtifactErrorCode::identity, "records.outcome.components", "Geometry component IDs must be nonempty and unique");
                    component_ids.push_back(component.id.value);
                    auto shape = geometry(component, component.id.value);
                    if (const auto* failure = std::get_if<ArtifactError>(&shape)) return *failure;
                    components.push_back(std::get<Json>(std::move(shape)));
                }
                projection_evidence.push_back(evidence(success->projection));
                for (const auto& input : success->projection.reference.inputs) source_ids.push_back(input.value);
                outcome = {{"status", "success"}, {"relation", relation(success->projection.relation)},
                    {"assurance", assurance(batch.requested_assurance)},
                    {"provider", {{"id", success->projection.provider.actual->id.value}, {"version", success->projection.provider.actual->version}}},
                    {"evidence", std::move(projection_evidence)},
                    {"components", std::move(components)}};
                if (success->error_bound) {
                    if (!std::isfinite(success->error_bound->bound) || success->error_bound->bound < 0.0 ||
                        success->error_bound->metric.value.empty())
                        return error(ArtifactErrorCode::invalid_input, "records.outcome.error_bound", "Error bound must be finite, nonnegative, and identified");
                    outcome["error_bound"] = {{"metric", success->error_bound->metric.value},
                        {"bound", success->error_bound->bound}, {"units", success->error_bound->units}};
                }
            } else if (const auto* unavailable = std::get_if<StageProjectionUnavailable>(&row.outcome)) {
                if (unavailable->explanation.empty())
                    return error(ArtifactErrorCode::invalid_input, "records.outcome.explanation", "Unavailable outcomes require an explanation");
                if ((unavailable->kind == StageProjectionGap::Kind::stopped) != unavailable->stop.has_value())
                    return error(ArtifactErrorCode::reference, "records.outcome.stop", "Only stopped outcomes must carry a stop reason");
                const char* kind = unavailable->kind == StageProjectionGap::Kind::missing ? "missing" :
                    unavailable->kind == StageProjectionGap::Kind::unsupported ? "unsupported" : "stopped";
                outcome = {{"status", "unavailable"}, {"kind", kind}, {"explanation", unavailable->explanation}};
                if (unavailable->stop) {
                    outcome["stop_reason"] = stop_reason(unavailable->stop->reason);
                    outcome["stop_diagnostics"] = unavailable->stop->diagnostics;
                }
            } else {
                const auto& failed = std::get<StageProjectionFailure>(row.outcome);
                const auto cause = failure_cause(failed);
                if (cause["explanation"].get<std::string>().empty())
                    return error(ArtifactErrorCode::invalid_input, "records.outcome.explanation", "Failure outcomes require an explanation");
                outcome = {{"status", "failure"}, {"kind", cause["kind"]}, {"explanation", cause["explanation"]}};
                if (cause.contains("diagnostics")) outcome["diagnostics"] = cause["diagnostics"];
                if (cause.contains("stop_reason")) {
                    outcome["stop_reason"] = cause["stop_reason"];
                    outcome["stop_diagnostics"] = cause["stop_diagnostics"];
                }
                if (failed.identity.problem != batch.problem || failed.identity.request.value.empty())
                    return error(ArtifactErrorCode::identity, "records.outcome", "Failure identity does not match batch problem/request");
            }
            records.push_back({{"stage", s}, {"physical_time", row.physical_time ? Json(*row.physical_time) : Json(nullptr)},
                {"pair_index", p}, {"source_assurance", row.source_assurance ? Json(assurance(*row.source_assurance)) : Json(nullptr)},
                {"source_set_ids", std::move(source_ids)}, {"outcome", std::move(outcome)}});
        }
    }
    Json document{{"schema", "csl.stage-projection-batch/1"},
        {"provenance", {{"run_id", identity.run.value}, {"record_schema", identity.source_record_schema},
            {"source_sha256", identity.source_record_sha256}}},
        {"problem_id", batch.problem.value}, {"request_id", batch.request.value},
        {"route_id", identity.route}, {"coordinates", std::move(coordinates)},
        {"requested_pairs", std::move(pairs)}, {"stage_axis", {{"kind", identity.stage_axis.kind == PlotAxis::Kind::physical_time ? "physical_time" : "stage"},
            {"points", identity.stage_axis.points}, {"unit", identity.stage_axis.unit ? Json(*identity.stage_axis.unit) : Json(nullptr)}}},
        {"relation", relation(batch.required_relation)}, {"assurance", assurance(batch.requested_assurance)},
        {"records", std::move(records)}, {"trajectory_series", std::move(trajectories)}};
    const std::string canonical = document.dump();
    const auto bytes = std::as_bytes(std::span{canonical.data(), canonical.size()});
    const auto content = problem::snapshot_content(bytes);
    if (const auto* issue = std::get_if<Diagnostic>(&content))
        return error(ArtifactErrorCode::allocation, "content_sha256", issue->explanation);
    document["content_sha256"] = problem::hex(std::get<problem::ResolvedContent>(content).digest());
    return document.dump(2) + "\n";
}

} // namespace csl::artifacts
