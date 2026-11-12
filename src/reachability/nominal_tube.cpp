#include <csl/reachability/nominal_tube.hpp>

#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_predecessor.hpp>

#include <chrono>
#include <limits>
#include <new>
#include <numeric>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

namespace csl::reachability {
namespace {
Diagnostics error(std::string field, std::string explanation,
        DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{code, std::move(field), std::move(explanation)}};
}

std::string field(const std::string& value) {
    return std::to_string(value.size()) + ":" + value;
}

std::string child_id(const ProblemId& problem, const RequestId& request,
        std::size_t stage, const char* suffix) {
    return "nominal-tube/" + field(problem.value) + field(request.value) +
        std::to_string(stage) + "/" + suffix;
}

std::string child_id(const ProblemId& problem, const RequestId& request,
        std::size_t stage, const std::string& suffix) {
    return child_id(problem, request, stage, suffix.c_str());
}

Matrix copy_matrix(const numeric::MatrixView& view) {
    Matrix result{view.rows(), view.cols(), {}};
    result.values.reserve(view.rows() * view.cols());
    for (std::size_t row = 0; row < view.rows(); ++row)
        for (std::size_t column = 0; column < view.cols(); ++column)
            result.values.push_back(view(row, column));
    return result;
}

std::vector<std::size_t> identity_coordinates(std::size_t dimension) {
    std::vector<std::size_t> result(dimension);
    std::iota(result.begin(), result.end(), std::size_t{0});
    return result;
}

std::variant<sets::SetData, Diagnostics> native_h(const SetHandle& handle,
        std::size_t dimension, const std::vector<std::string>& labels,
        const char* role) {
    auto imported = sets::from_handle(handle);
    if (const auto* failure = std::get_if<Diagnostic>(&imported)) return Diagnostics{*failure};
    auto data = std::get<sets::SetData>(std::move(imported));
    if (data.metadata()->set.dimension != dimension)
        return error(std::string("tube.") + role + ".dimension", "Set dimension differs from the resolved state dimension.", DiagnosticCode::invalid_input);
    const auto representation = data.representation();
    if (!std::holds_alternative<sets::HRepresentation>(representation))
        return error(std::string("tube.") + role + ".representation",
            "The first nominal tube profile requires native closed-H sets; convert other representations explicitly.");
    if (data.metadata()->coordinate_labels != labels)
        return error(std::string("tube.") + role + ".coordinates",
            "Set labels and ordering must match the resolved full-state coordinates.", DiagnosticCode::invalid_input);
    return data;
}

RequestProvenance provenance(const registry::Provenance& selected,
        const GeometryRequestIdentity& identity) {
    return {identity.request, selected.port, selected.requested.id, selected.requested.version,
        selected.actual ? std::optional<ModuleId>{selected.actual->id} : std::nullopt,
        selected.actual ? std::optional<std::string>{selected.actual->version} : std::nullopt};
}

bool is_state_h(const OperationResult& result, std::size_t dimension,
        const std::vector<std::string>& labels) {
    if (result.relation != SetRelation::equivalent ||
        result.output.metadata.representation.value != "csl.polyhedron.h" ||
        result.output.metadata.dimension != dimension) return false;
    auto imported = sets::from_handle(result.output);
    const auto* data = std::get_if<sets::SetData>(&imported);
    return data && std::holds_alternative<sets::HRepresentation>(data->representation()) &&
        data->metadata()->coordinate_labels == labels;
}

void append_forward(NominalTube& tube, const ForwardTube& forward) {
    tube.stages.reserve(forward.stages.size());
    for (const auto& stage : forward.stages) {
        NominalTubeStage result;
        result.stage = stage.stage;
        result.forward = stage.marginal;
        result.coordinates = stage.state_coordinates.empty()
            ? identity_coordinates(stage.marginal.output.metadata.dimension)
            : stage.state_coordinates;
        auto imported = sets::from_handle(stage.marginal.output);
        if (const auto* data = std::get_if<sets::SetData>(&imported))
            result.coordinate_labels = data->metadata()->coordinate_labels;
        result.source_sets = stage.marginal.evidence.reference.inputs;
        result.providers = stage.providers;
        result.lineage = stage.operation_lineage;
        result.lineage.push_back(stage.marginal.evidence);
        tube.stages.push_back(std::move(result));
    }
}

std::variant<OperationResult, Unsupported, OperationStopped> intersect(
        const SetHandle& left, const SetHandle& right, ProblemId problem,
        RequestId request, StageIndex stage, const NominalTubeDependencies& dependencies,
        NominalTubeStage& record, NominalTubePhase phase,
        std::optional<GeometryRequestIdentity>& active, const ExecutionContext& context) {
    const auto& selected = dependencies.intersection;
    if (!selected.provenance().actual)
        return Unsupported{error("tube.intersection.provider", "Intersection provider identity is unresolved.")};
    const GeometryRequestIdentity identity{{problem.value},
        {child_id(problem, request, stage.value, phase == NominalTubePhase::terminal ? "terminal" :
            phase == NominalTubePhase::intersection ? "intersection" : "backward-intersection")},
        {child_id(problem, request, stage.value, phase == NominalTubePhase::terminal ? "backward-set" :
            phase == NominalTubePhase::intersection ? "tube-intersection" : "backward-set")}};
    OperationRequest operation{identity, selected.provenance().actual->id,
        Intersection{left, right}, SetRelation::equivalent, Assurance::numerical};
    active = identity;
    record.requests.push_back(geometry_reference(operation));
    record.providers.push_back(provenance(selected.provenance(), identity));
    record.source_sets.push_back(left.id);
    record.source_sets.push_back(right.id);
    auto prepared = selected.prepare(operation);
    if (auto* rejected = std::get_if<registry::Rejection>(&prepared))
        return Unsupported{rejected->diagnostics};
    auto workspace = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared)).create();
    auto outcome = std::get<0>(workspace)->run(context);
    if (auto* stopped = std::get_if<OperationStopped>(&outcome)) return *stopped;
    if (auto* rejected = std::get_if<Unsupported>(&outcome)) return *rejected;
    const auto* result = std::get_if<OperationResult>(&outcome);
    if (!result) return Unsupported{error("tube.intersection.result",
        "Intersection provider returned a query result instead of a set.", DiagnosticCode::evidence_mismatch)};
    if (const auto diagnostics = check_geometry_evidence(result->evidence, operation); !diagnostics.empty())
        return Unsupported{diagnostics};
    record.lineage.push_back(result->evidence);
    return *result;
}

std::variant<OperationResult, Unsupported, OperationStopped> compact_h(
        OperationResult input, ProblemId problem, RequestId request, StageIndex stage,
        NominalTubePhase phase, const NominalTubeDependencies& dependencies,
        NominalTubeStage& record, std::optional<GeometryRequestIdentity>& active,
        const ExecutionContext& context) {
    if (!dependencies.compact_h_to_v) return input;
    const auto& to_v = *dependencies.compact_h_to_v;
    const auto& to_h = dependencies.forward.to_h;
    if (!to_v.provenance().actual || !to_h.provenance().actual)
        return Unsupported{error("tube.compaction.provider", "Bounded H compaction requires resolved H-to-V and V-to-H providers.")};
    const auto phase_name = phase == NominalTubePhase::terminal ? "terminal" :
        phase == NominalTubePhase::backward ? "backward" : "intersection";
    const auto make_request = [&](const SetHandle& source, const char* direction) {
        const auto suffix = std::string(phase_name) + "/compact-h/" + direction;
        GeometryRequestIdentity identity{{problem.value}, {child_id(problem, request, stage.value, suffix)},
            {child_id(problem, request, stage.value, suffix + "/output")}};
        const auto representation = std::string("csl.polyhedron.") +
            (std::string(direction) == "to-v" ? "v" : "h");
        return ConversionRequest{identity, source, {representation}, Assurance::numerical};
    };
    const auto run_conversion = [&](const registry::PreparedProvider<registry::ConversionPort>& provider,
            const ConversionRequest& conversion) -> std::variant<OperationResult, Unsupported, OperationStopped> {
        active = conversion.identity;
        record.requests.push_back({conversion.identity, {conversion.input.id}});
        record.providers.push_back(provenance(provider.provenance(), conversion.identity));
        record.source_sets.push_back(conversion.input.id);
        auto prepared = provider.prepare(conversion);
        if (auto* rejected = std::get_if<registry::Rejection>(&prepared))
            return Unsupported{rejected->diagnostics};
        auto workspace = std::get<registry::PreparedPipeline<registry::ConversionPort>>(
            std::move(prepared)).create();
        auto outcome = std::get<0>(workspace)->run(context);
        if (auto* stopped = std::get_if<OperationStopped>(&outcome)) return *stopped;
        if (auto* rejected = std::get_if<Unsupported>(&outcome)) return *rejected;
        const auto* result = std::get_if<OperationResult>(&outcome);
        if (!result) return Unsupported{error("tube.compaction.result", "Conversion provider returned a query instead of a set.", DiagnosticCode::evidence_mismatch)};
        if (const auto diagnostics = check_geometry_evidence(result->evidence, conversion); !diagnostics.empty())
            return Unsupported{diagnostics};
        if (result->relation != SetRelation::equivalent ||
            result->output.metadata.dimension != input.output.metadata.dimension)
            return Unsupported{error("tube.compaction.result", "H compaction conversion changed relation or state dimension.", DiagnosticCode::evidence_mismatch)};
        record.lineage.push_back(result->evidence);
        return *result;
    };

    auto h_to_v = make_request(input.output, "to-v");
    auto v_result = run_conversion(to_v, h_to_v);
    if (auto* rejected = std::get_if<Unsupported>(&v_result)) return *rejected;
    if (auto* stopped = std::get_if<OperationStopped>(&v_result)) return *stopped;
    auto v = std::get<OperationResult>(std::move(v_result));
    if (v.output.metadata.representation.value != "csl.polyhedron.v")
        return Unsupported{error("tube.compaction.representation", "H-to-V provider did not materialize V data.", DiagnosticCode::evidence_mismatch)};

    auto v_to_h = make_request(v.output, "to-h");
    auto h_result = run_conversion(to_h, v_to_h);
    if (auto* rejected = std::get_if<Unsupported>(&h_result)) return *rejected;
    if (auto* stopped = std::get_if<OperationStopped>(&h_result)) return *stopped;
    auto h = std::get<OperationResult>(std::move(h_result));
    if (h.output.metadata.representation.value != "csl.polyhedron.h")
        return Unsupported{error("tube.compaction.representation", "V-to-H provider did not materialize H data.", DiagnosticCode::evidence_mismatch)};
    auto imported_h = sets::from_handle(h.output);
    if (auto* rejected = std::get_if<Diagnostic>(&imported_h)) return Unsupported{{*rejected}};
    auto h_data = std::get<sets::SetData>(std::move(imported_h));
    const auto h_representation = h_data.representation();
    const auto* h_native = std::get_if<sets::HRepresentation>(&h_representation);
    if (!h_native) return Unsupported{error("tube.compaction.representation", "V-to-H output does not contain native H data.", DiagnosticCode::evidence_mismatch)};
    auto imported_source = sets::from_handle(input.output);
    if (auto* rejected = std::get_if<Diagnostic>(&imported_source)) return Unsupported{{*rejected}};
    const auto& source_labels = std::get<sets::SetData>(imported_source).metadata()->coordinate_labels;
    const auto& output_labels = h_data.metadata()->coordinate_labels;
    if (source_labels.size() != input.output.metadata.dimension ||
        (!output_labels.empty() && output_labels != source_labels))
        return Unsupported{error("tube.compaction.coordinates", "H conversion changed coordinate order or labels.", DiagnosticCode::evidence_mismatch)};
    if (output_labels.empty()) {
        auto relabeled = sets::make_h({{child_id(problem, request, stage.value,
            std::string(phase_name) + "/compact-h/labelled")}, input.output.metadata.dimension, source_labels},
            *h_native);
        if (auto* rejected = std::get_if<Diagnostic>(&relabeled)) return Unsupported{{*rejected}};
        const auto target = std::get<sets::SetData>(std::move(relabeled)).as_handle();
        record.coordinate_lineage.push_back({h.output, target,
            identity_coordinates(input.output.metadata.dimension)});
        h.output = target;
    }

    auto composed = h.evidence;
    composed.reference.identity = GeometryRequestIdentity{{problem.value},
        {child_id(problem, request, stage.value, std::string(phase_name) + "/compact-h/result")},
        {h.output.id.value}};
    composed.reference.inputs = {input.output.id, v.output.id};
    composed.scope = GeometryClaimScope::set_relation;
    composed.support = Unestablished{};
    composed.error_bound.reset();
    composed.assumptions.push_back("bounded H set compacted by an explicitly requested equivalent numerical H-to-V-to-H conversion chain");
    input.output = std::move(h.output);
    input.relation = SetRelation::equivalent;
    input.evidence = std::move(composed);
    return input;
}

std::variant<OperationResult, Unsupported, OperationStopped> as_intersection_result(
        NominalPredecessorOutcome outcome, NominalTubeStage& record,
        std::optional<GeometryRequestIdentity>& active) {
    if (auto* failure = std::get_if<NominalPredecessorFailure>(&outcome)) {
        active = failure->projection.identity;
        record.requests.push_back(failure->predecessor);
        record.requests.push_back(failure->projection);
        record.providers.push_back(failure->projection_provider);
        record.lineage.insert(record.lineage.end(), failure->completed_lineage.begin(), failure->completed_lineage.end());
        return std::visit([](auto cause) -> std::variant<OperationResult, Unsupported, OperationStopped> {
            using T = std::decay_t<decltype(cause)>;
            if constexpr (std::is_same_v<T, Unsupported>) return cause;
            else return cause;
        }, failure->cause);
    }
    auto result = std::get<NominalPredecessorResult>(std::move(outcome));
    active = result.projection_request;
    record.requests.push_back(result.result.evidence.reference);
    record.requests.push_back({result.projection_request, result.result.evidence.reference.inputs});
    record.providers.push_back(result.projection_provider);
    record.lineage.push_back(result.result.evidence);
    return std::move(result.result);
}

} // namespace

NominalTubeOutcome nominal_tube(const problem::ResolvedProblem& resolved, RequestId request,
        const SetHandle& terminal_feasibility, const NominalTubeDependencies& dependencies,
        const ExecutionContext& context) {
    NominalTube tube{resolved.identity(), request, {}};
    StageIndex active_stage{0};
    NominalTubePhase active_phase = NominalTubePhase::forward;
    std::optional<GeometryRequestIdentity> active_request;
    const auto fail = [&](auto cause) -> NominalTubeOutcome {
        using T = std::decay_t<decltype(cause)>;
        return NominalTubeFailure{std::move(tube), active_stage, active_phase, active_request,
            std::variant<Unsupported, OperationStopped>{std::in_place_type<T>, std::move(cause)}, {}, {}, {}, {}};
    };
    try {
        if (request.value.empty()) return fail(Unsupported{error("tube.request", "Nonempty immutable request ID required.", DiagnosticCode::invalid_input)});

        auto forward_outcome = nominal_forward(resolved,
            {child_id(tube.problem, request, 0, "forward")}, dependencies.forward, context);
        if (auto* failure = std::get_if<ForwardFailure>(&forward_outcome)) {
            append_forward(tube, failure->prefix);
            active_stage = failure->stage;
            active_phase = NominalTubePhase::forward;
            if (failure->active_request) active_request = failure->active_request->identity;
            auto outcome = std::visit([&](auto cause) -> NominalTubeFailure {
                using T = std::decay_t<decltype(cause)>;
                return {std::move(tube), active_stage, active_phase, active_request,
                    std::variant<Unsupported, OperationStopped>{std::in_place_type<T>, std::move(cause)}, {}, {}, {}, {}};
            }, failure->cause);
            outcome.forward_partial = failure->partial_relation;
            outcome.forward_providers = failure->providers;
            outcome.forward_lineage = failure->completed_lineage;
            outcome.coordinate_lineage = failure->coordinate_lineage;
            return outcome;
        }
        if (auto* empty = std::get_if<EmptyForwardStage>(&forward_outcome)) {
            append_forward(tube, empty->prefix);
            return NominalTubeEmptyForward{std::move(tube), empty->stage, empty->evidence};
        }
        const auto& forward = std::get<ForwardTube>(forward_outcome);
        append_forward(tube, forward);
        const auto source = resolved.description();
        const auto system = resolved.model();
        const auto dimension = system.dimensions().state;
        const auto horizon = system.horizon();
        if (tube.stages.size() != horizon + 1 || source->states.size() != horizon + 1)
            return fail(Unsupported{error("tube.stages", "Resolved state and forward stage counts do not match the horizon.", DiagnosticCode::evidence_mismatch)});
        if (forward.stages.empty()) return fail(Unsupported{error("tube.forward", "Completed forward outcome omitted all stages.", DiagnosticCode::evidence_mismatch)});
        const auto state_labels = tube.stages.front().coordinate_labels;
        std::vector<SetHandle> state_sets;
        state_sets.reserve(horizon + 1);
        for (std::size_t stage = 0; stage <= horizon; ++stage) {
            active_stage = {stage}; active_phase = stage == horizon ? NominalTubePhase::terminal : NominalTubePhase::backward;
            const auto* handle = std::get_if<SetHandle>(&source->states[stage]);
            if (!handle) return fail(Unsupported{error("tube.state-set", "This first tube profile requires explicit native-H state-constraint handles.", DiagnosticCode::unsupported)});
            auto checked = native_h(*handle, dimension, state_labels, "state");
            if (auto* rejected = std::get_if<Diagnostics>(&checked)) return fail(Unsupported{std::move(*rejected)});
            state_sets.push_back(*handle);
        }
        auto checked_terminal = native_h(terminal_feasibility, dimension, state_labels, "terminal");
        if (auto* rejected = std::get_if<Diagnostics>(&checked_terminal)) {
            active_stage = {horizon}; active_phase = NominalTubePhase::terminal;
            return fail(Unsupported{std::move(*rejected)});
        }
        const auto control_domains = resolved.controls().description();
        const auto* continuous = std::get_if<ContinuousDomain>(control_domains.get());
        if (!continuous || continuous->stages.size() != horizon)
            return fail(Unsupported{error("tube.controls", "Continuous control sets must cover every transition.")} );
        std::vector<SetHandle> control_sets;
        control_sets.reserve(horizon);
        for (std::size_t stage = 0; stage < horizon; ++stage) {
            const auto* handle = std::get_if<SetHandle>(&continuous->stages[stage]);
            if (!handle) {
                active_stage = {stage}; active_phase = NominalTubePhase::backward;
                return fail(Unsupported{error("tube.control-set", "This first tube profile requires explicit native-H control-set handles.")} );
            }
            auto imported = sets::from_handle(*handle);
            if (const auto* rejected = std::get_if<Diagnostic>(&imported)) {
                active_stage = {stage}; active_phase = NominalTubePhase::backward;
                return fail(Unsupported{{*rejected}});
            }
            const auto& data = std::get<sets::SetData>(imported);
            if (!std::holds_alternative<sets::HRepresentation>(data.representation())) {
                active_stage = {stage}; active_phase = NominalTubePhase::backward;
                return fail(Unsupported{error("tube.control-set", "The first tube profile requires native closed-H control sets.")} );
            }
            control_sets.push_back(*handle);
        }
        for (const auto& stage : tube.stages) {
            if (!stage.forward || !is_state_h(*stage.forward, dimension, state_labels)) {
                active_stage = stage.stage; active_phase = NominalTubePhase::forward;
                return fail(Unsupported{error("tube.forward.result", "Forward stage is not an equivalent full-state H set with source coordinate ordering.", DiagnosticCode::evidence_mismatch)});
            }
        }

        active_stage = {horizon}; active_phase = NominalTubePhase::terminal;
        auto terminal_result = intersect(state_sets[horizon], terminal_feasibility, tube.problem,
            request, active_stage, dependencies, tube.stages[horizon], active_phase, active_request, context);
        if (auto* rejected = std::get_if<Unsupported>(&terminal_result)) return fail(*rejected);
        if (auto* stopped = std::get_if<OperationStopped>(&terminal_result)) return fail(*stopped);
        auto backward = std::get<OperationResult>(std::move(terminal_result));
        if (!is_state_h(backward, dimension, state_labels))
            return fail(Unsupported{error("tube.terminal.result", "Terminal feasibility is not a full-state H result.", DiagnosticCode::evidence_mismatch)});
        tube.stages[horizon].backward = backward;
        auto compacted_terminal = compact_h(std::move(backward), tube.problem, request, active_stage,
            active_phase, dependencies, tube.stages[horizon], active_request, context);
        if (auto* rejected = std::get_if<Unsupported>(&compacted_terminal)) return fail(*rejected);
        if (auto* stopped = std::get_if<OperationStopped>(&compacted_terminal)) return fail(*stopped);
        backward = std::get<OperationResult>(std::move(compacted_terminal));
        if (!is_state_h(backward, dimension, state_labels))
            return fail(Unsupported{error("tube.terminal.compaction", "Compacted terminal set changed state coordinates.", DiagnosticCode::evidence_mismatch)});
        tube.stages[horizon].backward = backward;

        active_phase = NominalTubePhase::intersection;
        auto terminal_intersection = intersect(tube.stages[horizon].forward->output,
            backward.output, tube.problem, request, active_stage, dependencies,
            tube.stages[horizon], active_phase, active_request, context);
        if (auto* rejected = std::get_if<Unsupported>(&terminal_intersection)) return fail(*rejected);
        if (auto* stopped = std::get_if<OperationStopped>(&terminal_intersection)) return fail(*stopped);
        auto terminal_i = std::get<OperationResult>(std::move(terminal_intersection));
        if (!is_state_h(terminal_i, dimension, state_labels))
            return fail(Unsupported{error("tube.intersection.result", "Full-state terminal intersection changed representation or coordinates.", DiagnosticCode::evidence_mismatch)});
        tube.stages[horizon].intersection = terminal_i;
        auto compacted_terminal_i = compact_h(std::move(terminal_i), tube.problem, request, active_stage,
            active_phase, dependencies, tube.stages[horizon], active_request, context);
        if (auto* rejected = std::get_if<Unsupported>(&compacted_terminal_i)) return fail(*rejected);
        if (auto* stopped = std::get_if<OperationStopped>(&compacted_terminal_i)) return fail(*stopped);
        auto terminal_intersection_set = std::get<OperationResult>(std::move(compacted_terminal_i));
        if (!is_state_h(terminal_intersection_set, dimension, state_labels))
            return fail(Unsupported{error("tube.intersection.compaction", "Compacted terminal intersection changed state coordinates.", DiagnosticCode::evidence_mismatch)});
        tube.stages[horizon].intersection = std::move(terminal_intersection_set);

        for (std::size_t reverse = horizon; reverse > 0; --reverse) {
            const auto stage_index = reverse - 1;
            active_stage = {stage_index}; active_phase = NominalTubePhase::backward;
            const auto stage_model = system.stage({stage_index});
            if (const auto* rejected = std::get_if<Diagnostic>(&stage_model)) return fail(Unsupported{{*rejected}});
            const auto dynamics = std::get<model::DynamicsStage>(stage_model);
            Matrix a = copy_matrix(dynamics.A);
            Matrix b = copy_matrix(dynamics.B);
            Vector offset(dynamics.offset.values().begin(), dynamics.offset.values().end());
            const GeometryRequestIdentity predecessor_id{{tube.problem.value},
                {child_id(tube.problem, request, stage_index, "predecessor")},
                {child_id(tube.problem, request, stage_index, "predecessor-output")}};
            active_request = predecessor_id;
            NominalPredecessorRequest predecessor_request{predecessor_id,
                state_sets[stage_index], control_sets[stage_index],
                tube.stages[stage_index + 1].backward->output, std::move(a), std::move(b),
                std::move(offset), SetRelation::equivalent, Assurance::numerical};
            auto prepared = prepare_nominal_predecessor(predecessor_request,
                dependencies.forward.projection);
            if (auto* rejected = std::get_if<Diagnostics>(&prepared)) return fail(Unsupported{std::move(*rejected)});
            if (auto* rejected = std::get_if<registry::Rejection>(&prepared)) return fail(Unsupported{rejected->diagnostics});
            auto predecessor = std::get<PreparedNominalPredecessor>(std::move(prepared)).run(context);
            auto predecessor_result = as_intersection_result(std::move(predecessor),
                tube.stages[stage_index], active_request);
            if (auto* rejected = std::get_if<Unsupported>(&predecessor_result)) return fail(*rejected);
            if (auto* stopped = std::get_if<OperationStopped>(&predecessor_result)) return fail(*stopped);
            auto preimage = std::get<OperationResult>(std::move(predecessor_result));
            if (!is_state_h(preimage, dimension, state_labels))
                return fail(Unsupported{error("tube.predecessor.result", "Existential predecessor changed the full-state H coordinates.", DiagnosticCode::evidence_mismatch)});

            auto backward_result = intersect(state_sets[stage_index], preimage.output,
                tube.problem, request, active_stage, dependencies, tube.stages[stage_index],
                NominalTubePhase::backward, active_request, context);
            if (auto* rejected = std::get_if<Unsupported>(&backward_result)) return fail(*rejected);
            if (auto* stopped = std::get_if<OperationStopped>(&backward_result)) return fail(*stopped);
            auto backward_stage = std::get<OperationResult>(std::move(backward_result));
            if (!is_state_h(backward_stage, dimension, state_labels))
                return fail(Unsupported{error("tube.backward.result", "Backward stage is not a full-state H set.", DiagnosticCode::evidence_mismatch)});
            tube.stages[stage_index].backward = backward_stage;
            auto compacted_backward = compact_h(std::move(backward_stage), tube.problem, request,
                active_stage, NominalTubePhase::backward, dependencies, tube.stages[stage_index],
                active_request, context);
            if (auto* rejected = std::get_if<Unsupported>(&compacted_backward)) return fail(*rejected);
            if (auto* stopped = std::get_if<OperationStopped>(&compacted_backward)) return fail(*stopped);
            backward_stage = std::get<OperationResult>(std::move(compacted_backward));
            if (!is_state_h(backward_stage, dimension, state_labels))
                return fail(Unsupported{error("tube.backward.compaction", "Compacted backward set changed state coordinates.", DiagnosticCode::evidence_mismatch)});
            tube.stages[stage_index].backward = backward_stage;

            active_phase = NominalTubePhase::intersection;
            auto intersection_result = intersect(tube.stages[stage_index].forward->output,
                backward_stage.output, tube.problem, request, active_stage, dependencies,
                tube.stages[stage_index], active_phase, active_request, context);
            if (auto* rejected = std::get_if<Unsupported>(&intersection_result)) return fail(*rejected);
            if (auto* stopped = std::get_if<OperationStopped>(&intersection_result)) return fail(*stopped);
            auto full_state_intersection = std::get<OperationResult>(std::move(intersection_result));
            if (!is_state_h(full_state_intersection, dimension, state_labels))
                return fail(Unsupported{error("tube.intersection.result", "Full-state stage intersection changed representation or coordinates.", DiagnosticCode::evidence_mismatch)});
            tube.stages[stage_index].intersection = full_state_intersection;
            auto compacted_intersection = compact_h(std::move(full_state_intersection), tube.problem,
                request, active_stage, active_phase, dependencies, tube.stages[stage_index],
                active_request, context);
            if (auto* rejected = std::get_if<Unsupported>(&compacted_intersection)) return fail(*rejected);
            if (auto* stopped = std::get_if<OperationStopped>(&compacted_intersection)) return fail(*stopped);
            auto intersection_set = std::get<OperationResult>(std::move(compacted_intersection));
            if (!is_state_h(intersection_set, dimension, state_labels))
                return fail(Unsupported{error("tube.intersection.compaction", "Compacted full-state intersection changed state coordinates.", DiagnosticCode::evidence_mismatch)});
            tube.stages[stage_index].intersection = std::move(intersection_set);
        }
        return tube;
    } catch (const std::bad_alloc&) {
        return fail(OperationStopped{StopReason::resource_limit, "Allocation failed while constructing the nominal H tube."});
    } catch (const std::length_error&) {
        return fail(OperationStopped{StopReason::resource_limit, "Nominal H tube storage exceeded container capacity."});
    } catch (const std::logic_error& failure) {
        return fail(Unsupported{error("tube.construction", failure.what(), DiagnosticCode::invalid_input)});
    }
}
} // namespace csl::reachability
