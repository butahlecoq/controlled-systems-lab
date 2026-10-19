#include <csl/geometry/lazy.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <unordered_map>
#include <utility>

namespace csl::geometry::lazy {
namespace {
constexpr const char* module = "csl.geometry.lazy-support";
using Answer = std::variant<SupportResult, OperationStopped, Unsupported>;

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
        "Lazy support query stopped before publication."};
}

bool finite(const Vector& values) {
    return std::all_of(values.begin(), values.end(), [](double value) { return std::isfinite(value); });
}

GeometryRequestIdentity child_identity(const GeometryRequestIdentity& parent, const std::string& path) {
    const auto scope = [&](const std::string& value) {
        return std::to_string(value.size()) + ":" + value + "/" + path;
    };
    return {parent.problem, {scope(parent.request.value)}, {scope(parent.ideal_output.value)}};
}

struct CacheKey {
    const SetPayload* payload;
    Vector direction;
    bool operator==(const CacheKey&) const = default;
};
struct CacheHash {
    std::size_t operator()(const CacheKey& key) const {
        std::size_t value = std::hash<const SetPayload*>{}(key.payload);
        for (const double component : key.direction)
            value ^= std::hash<double>{}(component) + 0x9e3779b9U + (value << 6) + (value >> 2);
        return value;
    }
};
using Cache = std::unordered_map<CacheKey, SupportResult, CacheHash>;

Answer evaluate_node(const SetHandle& input, const Vector& direction,
        const GeometryRequestIdentity& parent, const std::string& path,
        const registry::PreparedProvider<registry::GeometryPort>& leaf_provider,
        const ExecutionContext& context, Cache& cache) {
    if (stopped(context)) return stop(context);
    if (input.metadata.representation.value != "csl.geometry.lazy-v") {
        const auto& provenance = leaf_provider.provenance();
        if (!provenance.actual)
            return Unsupported{error("lazy.leaf_provider", "Selected leaf support identity is unavailable.")};
        OperationRequest request{child_identity(parent, path), provenance.actual->id,
            SupportQuery{input, direction}, SetRelation::equivalent, Assurance::numerical};
        auto admitted = leaf_provider.prepare(request);
        if (const auto* rejected = std::get_if<registry::Rejection>(&admitted))
            return Unsupported{rejected->diagnostics};
        auto prepared = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admitted));
        auto outcome = std::get<0>(prepared.create())->run(context);
        if (const auto* value = std::get_if<SupportResult>(&outcome)) return *value;
        if (const auto* stop_result = std::get_if<OperationStopped>(&outcome)) return *stop_result;
        if (const auto* rejected = std::get_if<Unsupported>(&outcome)) return *rejected;
        return Unsupported{error("lazy.leaf_result", "Selected leaf provider returned a non-support result.",
            DiagnosticCode::evidence_mismatch)};
    }

    auto inspected = inspect_expression(input);
    if (const auto* failure = std::get_if<Diagnostics>(&inspected)) return Unsupported{*failure};
    CacheKey key{input.payload.get(), direction};
    if (const auto found = cache.find(key); found != cache.end()) return found->second;
    const auto& operation = std::get<ExpressionDescription>(inspected).operation;
    if (const auto* affine = std::get_if<AffineImage>(&operation)) {
        Vector transformed(affine->map.cols);
        for (std::size_t column = 0; column < affine->map.cols; ++column)
            for (std::size_t row = 0; row < affine->map.rows; ++row)
                transformed[column] += direction[row] * affine->map.values[row * affine->map.cols + column];
        if (!finite(transformed)) return Unsupported{error("lazy.direction", "Transformed direction is nonfinite.")};
        auto child = evaluate_node(affine->input, transformed, parent, path + "0", leaf_provider, context, cache);
        if (const auto* result = std::get_if<SupportResult>(&child)) {
            if (!std::holds_alternative<double>(result->value)) {
                cache.emplace(std::move(key), *result);
                return *result;
            }
            double value = std::get<double>(result->value);
            for (std::size_t row = 0; row < direction.size(); ++row)
                value += direction[row] * affine->offset[row];
            if (!std::isfinite(value)) return Unsupported{error("lazy.value", "Affine support value is nonfinite.")};
            if (!result->maximizer) return Unsupported{error("lazy.maximizer", "Finite leaf support omitted its maximizer.",
                DiagnosticCode::evidence_mismatch)};
            Vector maximizer(affine->map.rows);
            for (std::size_t row = 0; row < affine->map.rows; ++row) {
                maximizer[row] = affine->offset[row];
                for (std::size_t column = 0; column < affine->map.cols; ++column)
                    maximizer[row] += affine->map.values[row * affine->map.cols + column] * (*result->maximizer)[column];
            }
            if (!finite(maximizer)) return Unsupported{error("lazy.maximizer", "Affine maximizer is nonfinite.")};
            SupportResult answer{value, std::move(maximizer), result->evidence};
            cache.emplace(std::move(key), answer);
            return answer;
        }
        return child;
    }
    if (const auto* projection = std::get_if<Projection>(&operation)) {
        Vector embedded(projection->input.metadata.dimension);
        for (std::size_t column = 0; column < direction.size(); ++column)
            embedded[projection->coordinates[column]] = direction[column];
        auto child = evaluate_node(projection->input, embedded, parent, path + "0", leaf_provider, context, cache);
        if (const auto* result = std::get_if<SupportResult>(&child)) {
            if (!result->maximizer) {
                cache.emplace(std::move(key), *result);
                return *result;
            }
            Vector maximizer;
            for (const auto index : projection->coordinates) maximizer.push_back((*result->maximizer)[index]);
            SupportResult answer{result->value, std::move(maximizer), result->evidence};
            cache.emplace(std::move(key), answer);
            return answer;
        }
        return child;
    }
    if (const auto* sum = std::get_if<MinkowskiSum>(&operation)) {
        auto left = evaluate_node(sum->left, direction, parent, path + "0", leaf_provider, context, cache);
        if (!std::holds_alternative<SupportResult>(left)) return left;
        auto right = evaluate_node(sum->right, direction, parent, path + "1", leaf_provider, context, cache);
        if (!std::holds_alternative<SupportResult>(right)) return right;
        const auto& a = std::get<SupportResult>(left);
        const auto& b = std::get<SupportResult>(right);
        if (std::holds_alternative<EmptySupport>(a.value) || std::holds_alternative<EmptySupport>(b.value)) {
            SupportResult answer{EmptySupport{}, {}, a.evidence};
            cache.emplace(std::move(key), answer);
            return answer;
        }
        if (std::holds_alternative<UnboundedSupport>(a.value) || std::holds_alternative<UnboundedSupport>(b.value)) {
            SupportResult answer{UnboundedSupport{}, {}, a.evidence};
            cache.emplace(std::move(key), answer);
            return answer;
        }
        if (!a.maximizer || !b.maximizer)
            return Unsupported{error("lazy.maximizer", "Finite sum support omitted a child maximizer.",
                DiagnosticCode::evidence_mismatch)};
        const double value = std::get<double>(a.value) + std::get<double>(b.value);
        Vector maximizer(a.maximizer->size());
        for (std::size_t i = 0; i < maximizer.size(); ++i)
            maximizer[i] = (*a.maximizer)[i] + (*b.maximizer)[i];
        if (!std::isfinite(value) || !finite(maximizer))
            return Unsupported{error("lazy.value", "Summed support value or maximizer is nonfinite.")};
        SupportResult answer{value, std::move(maximizer), a.evidence};
        cache.emplace(std::move(key), answer);
        return answer;
    }
    return Unsupported{error("lazy.operation", "Expression payload contains an unsupported operation.",
        DiagnosticCode::evidence_mismatch)};
}
Answer evaluate(const SetHandle& input, const Vector& direction,
        const GeometryRequestIdentity& parent, const std::string& path,
        const registry::PreparedProvider<registry::GeometryPort>& leaf_provider,
        const ExecutionContext& context) {
    Cache cache;
    return evaluate_node(input, direction, parent, path, leaf_provider, context, cache);
}

Diagnostics shape(const OperationRequest& request, const registry::Requirements& requirements) {
    if (request.identity.problem.value.empty() || request.identity.request.value.empty() ||
        request.identity.ideal_output.value.empty())
        return error("lazy.identity", "Complete support query identity is required.", DiagnosticCode::invalid_input);
    if (request.implementation.value != module || !std::holds_alternative<SupportQuery>(request.operation))
        return error("lazy.operation", "Selected lazy support module requires SupportQuery.");
    if (request.assurance != Assurance::numerical || requirements.output.assurance != Assurance::numerical)
        return error("lazy.assurance", "Validated lazy support is unavailable.");
    if (request.required_relation != SetRelation::equivalent ||
        (requirements.output.relation && *requirements.output.relation != SetRelation::equivalent))
        return error("lazy.relation", "Lazy support requires equivalent relation semantics.");
    if (auto result = check_operation_shape(request); !result.empty()) return result;
    const auto& query = std::get<SupportQuery>(request.operation);
    if (!finite(query.direction))
        return error("lazy.direction", "Directions must be finite binary64 values.", DiagnosticCode::invalid_input);
    const auto inspected = inspect_expression(query.input);
    if (const auto* failure = std::get_if<Diagnostics>(&inspected)) return *failure;
    return {};
}

class Workspace final : public SetOperatorWorkspace {
    registry::PreparedProvider<registry::GeometryPort> leaf_provider_;
public:
    explicit Workspace(registry::PreparedProvider<registry::GeometryPort> provider)
        : leaf_provider_(std::move(provider)) {}

    OperationOutcome apply(const OperationRequest& request, const ExecutionContext& context) override {
        if (stopped(context)) return stop(context);
        if (auto failures = shape(request, {}); !failures.empty()) return Unsupported{std::move(failures)};
        const auto& query = std::get<SupportQuery>(request.operation);
        auto answer = evaluate(query.input, query.direction, request.identity, "root", leaf_provider_, context);
        if (const auto* failure = std::get_if<Unsupported>(&answer)) return *failure;
        if (const auto* stop_result = std::get_if<OperationStopped>(&answer)) return *stop_result;
        auto result = std::get<SupportResult>(std::move(answer));
        result.evidence = {geometry_reference(request), GeometryClaimScope::support_value,
            Unestablished{}, {"Composed binary64 support sample; no validated rounding or global enclosure claim."}, {}};
        if (auto failures = check_geometry_evidence(result.evidence, request); !failures.empty())
            return Unsupported{std::move(failures)};
        if (stopped(context)) return stop(context);
        return result;
    }
};
} // namespace

registry::Registration<registry::GeometryPort> make_support_registration(
        registry::PreparedProvider<registry::GeometryPort> leaf_support) {
    return {{{module}, "1.0.0"},
        [](const OperationRequest& request, const registry::Requirements& requirements) -> registry::Capability {
            if (auto failures = shape(request, requirements); !failures.empty()) return failures;
            registry::Output output;
            output.relation = SetRelation::equivalent;
            return registry::Offer{output};
        },
        [leaf_support = std::move(leaf_support)](const OperationRequest&) {
            return std::make_unique<Workspace>(leaf_support);
        }};
}

SampleOutcome sample_support(const registry::PreparedProvider<registry::GeometryPort>& provider,
        const SetHandle& input, const std::vector<Vector>& directions,
        const GeometryRequestIdentity& identity, const ExecutionContext& context) {
    if (identity.problem.value.empty() || identity.request.value.empty() || identity.ideal_output.value.empty())
        return Unsupported{error("lazy.identity", "Complete support-sample identity is required.",
            DiagnosticCode::invalid_input)};
    if (const auto inspected = inspect_expression(input); std::holds_alternative<Diagnostics>(inspected))
        return Unsupported{std::get<Diagnostics>(inspected)};
    if (!provider.provenance().actual || provider.provenance().actual->id.value != module)
        return Unsupported{error("lazy.provider", "A prepared lazy-support provider is required.",
            DiagnosticCode::invalid_input)};
    SupportSamples result{{identity, {input.id}}, SampleCoverage::directions_only, {}};
    for (std::size_t index = 0; index < directions.size(); ++index) {
        if (stopped(context)) return stop(context);
        const auto& direction = directions[index];
        if (direction.size() != input.metadata.dimension || !finite(direction))
            return Unsupported{error("lazy.direction", "Sample direction has wrong dimension or nonfinite entry.",
                DiagnosticCode::invalid_input)};
        const auto scoped = child_identity(identity, "sample" + std::to_string(index));
        OperationRequest request{scoped, {module}, SupportQuery{input, direction},
            SetRelation::equivalent, Assurance::numerical};
        auto admitted = provider.prepare(request);
        if (const auto* rejected = std::get_if<registry::Rejection>(&admitted))
            return Unsupported{rejected->diagnostics};
        auto prepared = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admitted));
        auto outcome = std::get<0>(prepared.create())->run(context);
        if (const auto* sample = std::get_if<SupportResult>(&outcome)) {
            if (auto failures = check_geometry_evidence(sample->evidence, request); !failures.empty())
                return Unsupported{std::move(failures)};
            result.samples.push_back({direction, *sample});
        } else if (const auto* interrupted = std::get_if<OperationStopped>(&outcome)) return *interrupted;
        else if (const auto* refused = std::get_if<Unsupported>(&outcome)) return *refused;
        else return Unsupported{error("lazy.result", "Support provider returned a non-support outcome.",
            DiagnosticCode::evidence_mismatch)};
    }
    if (stopped(context)) return stop(context);
    return result;
}
} // namespace csl::geometry::lazy
