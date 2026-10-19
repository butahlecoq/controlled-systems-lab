#include <csl/geometry/lazy.hpp>

#include <csl/sets/data.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <set>
#include <utility>

namespace csl::geometry::lazy {
namespace {
constexpr const char* module = "csl.geometry.lazy-expression";
constexpr const char* representation = "csl.geometry.lazy-v";

struct Payload final : SetPayload {
    SetMetadata metadata;
    SetId id;
    ExpressionDescription expression;
    Payload(SetMetadata stored_metadata, SetId stored_id, ExpressionDescription stored_expression)
        : metadata(std::move(stored_metadata)), id(std::move(stored_id)),
          expression(std::move(stored_expression)) {}
};

Diagnostics error(std::string field, std::string explanation,
        DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{code, std::move(field), std::move(explanation)}};
}

bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now() >= *context.deadline);
}

OperationStopped stop(const ExecutionContext& context) {
    return {context.cancellation.stop_requested() ? StopReason::cancelled : StopReason::deadline_expired,
        "Lazy expression stopped before publication."};
}

bool same(const SetMetadata& a, const SetMetadata& b) {
    return a.dimension == b.dimension && a.representation == b.representation &&
        a.convex == b.convex && a.polyhedral == b.polyhedral && a.bounded == b.bounded;
}

std::variant<std::vector<std::string>, Diagnostics> labels(const SetHandle& handle) {
    if (std::dynamic_pointer_cast<const Payload>(handle.payload)) {
        auto description = inspect_expression(handle);
        if (const auto* failure = std::get_if<Diagnostics>(&description)) return *failure;
        return std::get<ExpressionDescription>(std::move(description)).coordinate_labels;
    }
    auto imported = sets::from_handle(handle);
    if (const auto* failure = std::get_if<Diagnostic>(&imported)) return Diagnostics{*failure};
    const auto data = std::get<sets::SetData>(std::move(imported));
    const auto native = data.representation();
    if (!std::holds_alternative<sets::VRepresentation>(native) &&
        !std::holds_alternative<sets::EmptyRepresentation>(native))
        return error("lazy.leaf", "Only native V and empty leaves are supported.");
    return data.metadata()->coordinate_labels;
}

std::variant<std::vector<std::string>, Diagnostics> output_labels(const GeometryOperation& operation) {
    if (const auto* affine = std::get_if<AffineImage>(&operation)) {
        auto source = labels(affine->input);
        if (std::holds_alternative<Diagnostics>(source)) return std::get<Diagnostics>(std::move(source));
        return std::vector<std::string>{}; // General maps do not retain source coordinate names.
    }
    if (const auto* projection = std::get_if<Projection>(&operation)) {
        auto source = labels(projection->input);
        if (const auto* failure = std::get_if<Diagnostics>(&source)) return *failure;
        const auto& original = std::get<std::vector<std::string>>(source);
        std::vector<std::string> result;
        for (const auto index : projection->coordinates)
            if (!original.empty()) result.push_back(original[index]);
        return result;
    }
    if (const auto* sum = std::get_if<MinkowskiSum>(&operation)) {
        auto left = labels(sum->left);
        if (const auto* failure = std::get_if<Diagnostics>(&left)) return *failure;
        auto right = labels(sum->right);
        if (const auto* failure = std::get_if<Diagnostics>(&right)) return *failure;
        if (std::get<std::vector<std::string>>(left) != std::get<std::vector<std::string>>(right))
            return error("lazy.coordinates", "Independent sum operands require matching coordinate labels.",
                DiagnosticCode::invalid_input);
        return std::get<std::vector<std::string>>(std::move(left));
    }
    return error("lazy.operation", "Only affine image, coordinate projection, and independent sum are supported.");
}

Diagnostics shape(const OperationRequest& request, const registry::Requirements& requirements) {
    if (request.identity.problem.value.empty() || request.identity.request.value.empty() ||
        request.identity.ideal_output.value.empty())
        return error("lazy.identity", "Complete immutable operation identity is required.", DiagnosticCode::invalid_input);
    if (request.implementation.value != module)
        return error("lazy.implementation", "Request must identify the selected lazy expression module.",
            DiagnosticCode::invalid_input);
    if (request.assurance != Assurance::numerical || requirements.output.assurance != Assurance::numerical)
        return error("lazy.assurance", "Validated lazy-expression assurance is unavailable.");
    if (request.required_relation != SetRelation::equivalent ||
        (requirements.output.relation && *requirements.output.relation != SetRelation::equivalent))
        return error("lazy.relation", "Lazy expressions require an equivalent mathematical relation.");
    if (auto result = check_operation_shape(request); !result.empty()) return result;
    if (const auto* affine = std::get_if<AffineImage>(&request.operation)) {
        if (std::any_of(affine->map.values.begin(), affine->map.values.end(),
                [](double value) { return !std::isfinite(value); }) ||
            std::any_of(affine->offset.begin(), affine->offset.end(),
                [](double value) { return !std::isfinite(value); }))
            return error("lazy.coefficients", "Affine coefficients must be finite binary64 values.",
                DiagnosticCode::invalid_input);
    }
    if (const auto* projection = std::get_if<Projection>(&request.operation)) {
        const std::set<std::size_t> unique(projection->coordinates.begin(), projection->coordinates.end());
        if (unique.size() != projection->coordinates.size())
            return error("lazy.coordinates", "Projected coordinate indices must be distinct.",
                DiagnosticCode::invalid_input);
    }
    const auto checked_labels = output_labels(request.operation);
    if (const auto* failure = std::get_if<Diagnostics>(&checked_labels)) return *failure;
    return {};
}

SetMetadata output_metadata(const GeometryOperation& operation) {
    SetMetadata result{0, {representation}, SetProperty::yes, SetProperty::yes, SetProperty::unknown};
    if (const auto* affine = std::get_if<AffineImage>(&operation)) {
        result.dimension = affine->map.rows;
        result.bounded = affine->input.metadata.bounded;
    } else if (const auto* projection = std::get_if<Projection>(&operation)) {
        result.dimension = projection->coordinates.size();
        result.bounded = projection->input.metadata.bounded;
    } else if (const auto* sum = std::get_if<MinkowskiSum>(&operation)) {
        result.dimension = sum->left.metadata.dimension;
        if (sum->left.metadata.bounded == SetProperty::yes && sum->right.metadata.bounded == SetProperty::yes)
            result.bounded = SetProperty::yes;
    }
    return result;
}

class Workspace final : public SetOperatorWorkspace {
public:
    OperationOutcome apply(const OperationRequest& request, const ExecutionContext& context) override {
        if (stopped(context)) return stop(context);
        if (auto failures = shape(request, {}); !failures.empty()) return Unsupported{std::move(failures)};
        auto checked_labels = output_labels(request.operation);
        if (const auto* failure = std::get_if<Diagnostics>(&checked_labels)) return Unsupported{*failure};
        GeometryEvidence evidence{geometry_reference(request), GeometryClaimScope::set_relation,
            Unestablished{}, {"Expression identity is mathematical; binary64 evaluation is not validated."}, {}};
        if (auto failures = check_geometry_evidence(evidence, request); !failures.empty())
            return Unsupported{std::move(failures)};
        const SetMetadata metadata = output_metadata(request.operation);
        const SetId id{request.identity.ideal_output.value};
        auto payload = std::make_shared<const Payload>(metadata, id,
            ExpressionDescription{request.operation, evidence,
                std::get<std::vector<std::string>>(std::move(checked_labels))});
        if (stopped(context)) return stop(context);
        return OperationResult{{metadata, std::move(payload), id}, SetRelation::equivalent, std::move(evidence)};
    }
};
} // namespace

std::variant<ExpressionDescription, Diagnostics> inspect_expression(const SetHandle& handle) {
    const auto payload = std::dynamic_pointer_cast<const Payload>(handle.payload);
    if (!payload) return error("lazy.payload", "Input is not this module's lazy expression.");
    if (handle.id != payload->id || !same(handle.metadata, payload->metadata))
        return error("lazy.metadata", "Lazy expression envelope differs from its immutable payload.",
            DiagnosticCode::invalid_input);
    return payload->expression;
}

registry::Registration<registry::GeometryPort> make_expression_registration() {
    return {{{module}, "1.0.0"},
        [](const OperationRequest& request, const registry::Requirements& requirements) -> registry::Capability {
            if (auto failures = shape(request, requirements); !failures.empty()) return failures;
            registry::Output output;
            output.representation = {representation};
            output.relation = SetRelation::equivalent;
            return registry::Offer{output};
        },
        [](const OperationRequest&) { return std::make_unique<Workspace>(); }};
}
} // namespace csl::geometry::lazy
