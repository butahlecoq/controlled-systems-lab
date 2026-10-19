#include <csl/geometry/lazy.hpp>

#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace csl::geometry::lazy {
namespace {
constexpr const char* module = "csl.geometry.lazy-materializer";
constexpr const char* native_v = "csl.polyhedron.v";
using GrowthResult = std::variant<RepresentationGrowth, Diagnostics>;
struct Rows { Matrix vertices; Matrix rays; };
using RowResult = std::variant<Rows, Unsupported, OperationStopped>;

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
        "Lazy materialization stopped without publishing a partial set."};
}

bool add(std::size_t a, std::size_t b, std::size_t& result) {
    if (a > std::numeric_limits<std::size_t>::max() - b) return false;
    result = a + b;
    return true;
}

bool multiply(std::size_t a, std::size_t b, std::size_t& result) {
    if (b && a > std::numeric_limits<std::size_t>::max() / b) return false;
    result = a * b;
    return true;
}

using GrowthCache = std::unordered_map<const SetPayload*, RepresentationGrowth>;
GrowthResult estimate_node(const SetHandle& handle, GrowthCache& cache) {
    if (handle.metadata.representation.value != "csl.geometry.lazy-v") {
        auto imported = sets::from_handle(handle);
        if (const auto* failure = std::get_if<Diagnostic>(&imported)) return Diagnostics{*failure};
        if (const auto found = cache.find(handle.payload.get()); found != cache.end()) return found->second;
        const auto data = std::get<sets::SetData>(std::move(imported));
        const auto native = data.representation();
        if (std::holds_alternative<sets::EmptyRepresentation>(native)) {
            cache.emplace(handle.payload.get(), RepresentationGrowth{});
            return RepresentationGrowth{};
        }
        const auto* v = std::get_if<sets::VRepresentation>(&native);
        if (!v) return error("lazy.leaf", "Only native V and empty leaves can be materialized.");
        const auto vertices = v->vertices.rows();
        const auto rays = v->rays.rows();
        const RepresentationGrowth result{vertices, rays, vertices, rays, vertices, rays, 0, 0};
        cache.emplace(handle.payload.get(), result);
        return result;
    }
    auto inspected = inspect_expression(handle);
    if (const auto* failure = std::get_if<Diagnostics>(&inspected)) return *failure;
    if (const auto found = cache.find(handle.payload.get()); found != cache.end()) return found->second;
    const auto& operation = std::get<ExpressionDescription>(inspected).operation;
    if (const auto* affine = std::get_if<AffineImage>(&operation)) {
        auto result = estimate_node(affine->input, cache);
        if (const auto* growth = std::get_if<RepresentationGrowth>(&result)) {
            std::size_t cells;
            if (!multiply(growth->estimated_vertices, handle.metadata.dimension, cells) ||
                !multiply(growth->estimated_rays, handle.metadata.dimension, cells))
                return error("lazy.growth", "Affine output cell count overflowed.");
            cache.emplace(handle.payload.get(), *growth);
        }
        return result;
    }
    if (const auto* projection = std::get_if<Projection>(&operation)) {
        auto result = estimate_node(projection->input, cache);
        if (const auto* growth = std::get_if<RepresentationGrowth>(&result)) {
            std::size_t cells;
            if (!multiply(growth->estimated_vertices, handle.metadata.dimension, cells) ||
                !multiply(growth->estimated_rays, handle.metadata.dimension, cells))
                return error("lazy.growth", "Projection output cell count overflowed.");
            cache.emplace(handle.payload.get(), *growth);
        }
        return result;
    }
    if (const auto* sum = std::get_if<MinkowskiSum>(&operation)) {
        auto left = estimate_node(sum->left, cache);
        if (const auto* failure = std::get_if<Diagnostics>(&left)) return *failure;
        auto right = estimate_node(sum->right, cache);
        if (const auto* failure = std::get_if<Diagnostics>(&right)) return *failure;
        const auto& a = std::get<RepresentationGrowth>(left);
        const auto& b = std::get<RepresentationGrowth>(right);
        RepresentationGrowth result;
        if (!add(a.source_vertices, b.source_vertices, result.source_vertices) ||
            !add(a.source_rays, b.source_rays, result.source_rays) ||
            !multiply(a.estimated_vertices, b.estimated_vertices, result.estimated_vertices))
            return error("lazy.growth", "Vertex count arithmetic overflowed.");
        if (result.estimated_vertices != 0 &&
            !add(a.estimated_rays, b.estimated_rays, result.estimated_rays))
            return error("lazy.growth", "Ray count arithmetic overflowed.");
        std::size_t cells;
        if (!multiply(result.estimated_vertices, handle.metadata.dimension, cells) ||
            !multiply(result.estimated_rays, handle.metadata.dimension, cells))
            return error("lazy.growth", "Summed output cell count overflowed.");
        result.peak_vertices = std::max({a.peak_vertices, b.peak_vertices, result.estimated_vertices});
        result.peak_rays = std::max({a.peak_rays, b.peak_rays, result.estimated_rays});
        cache.emplace(handle.payload.get(), result);
        return result;
    }
    return error("lazy.operation", "Expression has an unsupported operation.", DiagnosticCode::evidence_mismatch);
}
GrowthResult estimate(const SetHandle& handle) {
    GrowthCache cache;
    return estimate_node(handle, cache);
}

void collect_lineage_node(const SetHandle& handle, std::vector<GeometryEvidence>& lineage,
        std::unordered_set<const SetPayload*>& visited) {
    if (handle.metadata.representation.value != "csl.geometry.lazy-v") return;
    const auto inspected = inspect_expression(handle);
    if (!std::holds_alternative<ExpressionDescription>(inspected)) return;
    if (!visited.insert(handle.payload.get()).second) return;
    const auto& expression = std::get<ExpressionDescription>(inspected);
    if (const auto* affine = std::get_if<AffineImage>(&expression.operation))
        collect_lineage_node(affine->input, lineage, visited);
    else if (const auto* projection = std::get_if<Projection>(&expression.operation))
        collect_lineage_node(projection->input, lineage, visited);
    else if (const auto* sum = std::get_if<MinkowskiSum>(&expression.operation)) {
        collect_lineage_node(sum->left, lineage, visited);
        collect_lineage_node(sum->right, lineage, visited);
    }
    lineage.push_back(expression.creation_evidence);
}
void collect_lineage(const SetHandle& handle, std::vector<GeometryEvidence>& lineage) {
    std::unordered_set<const SetPayload*> visited;
    collect_lineage_node(handle, lineage, visited);
}

Diagnostics request_shape(const ConversionRequest& request) {
    if (request.identity.problem.value.empty() || request.identity.request.value.empty() ||
        request.identity.ideal_output.value.empty())
        return error("lazy.identity", "Complete immutable conversion identity is required.",
            DiagnosticCode::invalid_input);
    if (request.assurance != Assurance::numerical)
        return error("lazy.assurance", "Validated lazy materialization is unavailable.");
    if (request.output.value != native_v)
        return error("lazy.output", "Only native V materialization is supported.");
    auto inspected = inspect_expression(request.input);
    if (const auto* failure = std::get_if<Diagnostics>(&inspected)) return *failure;
    return {};
}

Diagnostics check_budget(const RepresentationGrowth& growth, MaterializationBudget budget) {
    if (growth.peak_vertices > budget.max_vertices || growth.peak_rays > budget.max_rays)
        return error("lazy.budget", "Expression row growth exceeds the caller's materialization budget.");
    return {};
}

Matrix copy_matrix(const numeric::MatrixView& view) {
    Matrix result{view.rows(), view.cols(), Vector(view.rows() * view.cols())};
    for (std::size_t row = 0; row < view.rows(); ++row)
        for (std::size_t column = 0; column < view.cols(); ++column)
            result.values[row * view.cols() + column] = view(row, column);
    return result;
}

using RowCache = std::unordered_map<const SetPayload*, Rows>;
RowResult evaluate_node(const SetHandle& handle, const ExecutionContext& context, RowCache& cache) {
    if (stopped(context)) return stop(context);
    if (handle.metadata.representation.value != "csl.geometry.lazy-v") {
        auto imported = sets::from_handle(handle);
        if (const auto* failure = std::get_if<Diagnostic>(&imported)) return Unsupported{{*failure}};
        if (const auto found = cache.find(handle.payload.get()); found != cache.end()) return found->second;
        const auto data = std::get<sets::SetData>(std::move(imported));
        const auto native = data.representation();
        if (std::holds_alternative<sets::EmptyRepresentation>(native)) {
            Rows result{{0, handle.metadata.dimension, {}}, {0, handle.metadata.dimension, {}}};
            cache.emplace(handle.payload.get(), result);
            return result;
        }
        const auto* v = std::get_if<sets::VRepresentation>(&native);
        if (!v) return Unsupported{error("lazy.leaf", "Only native V and empty leaves are supported.")};
        Rows result{copy_matrix(v->vertices), copy_matrix(v->rays)};
        cache.emplace(handle.payload.get(), result);
        return result;
    }
    auto inspected = inspect_expression(handle);
    if (const auto* failure = std::get_if<Diagnostics>(&inspected)) return Unsupported{*failure};
    if (const auto found = cache.find(handle.payload.get()); found != cache.end()) return found->second;
    const auto& operation = std::get<ExpressionDescription>(inspected).operation;
    if (const auto* affine = std::get_if<AffineImage>(&operation)) {
        auto source = evaluate_node(affine->input, context, cache);
        if (!std::holds_alternative<Rows>(source)) return source;
        const auto& rows = std::get<Rows>(source);
        Rows result{{rows.vertices.rows, affine->map.rows, Vector(rows.vertices.rows * affine->map.rows)},
            {rows.rays.rows, affine->map.rows, Vector(rows.rays.rows * affine->map.rows)}};
        const auto transform = [&](const Matrix& input, Matrix& output, bool offset) {
            for (std::size_t row = 0; row < input.rows; ++row) {
                if (stopped(context)) return false;
                for (std::size_t target = 0; target < output.cols; ++target) {
                    double value = offset ? affine->offset[target] : 0.0;
                    for (std::size_t source_column = 0; source_column < input.cols; ++source_column)
                        value += affine->map.values[target * input.cols + source_column] *
                            input.values[row * input.cols + source_column];
                    if (!std::isfinite(value)) return false;
                    output.values[row * output.cols + target] = value;
                }
            }
            return true;
        };
        if (!transform(rows.vertices, result.vertices, true) || !transform(rows.rays, result.rays, false))
            return stopped(context) ? RowResult{stop(context)} :
                RowResult{Unsupported{error("lazy.arithmetic", "Affine materialization produced nonfinite data.")}};
        cache.emplace(handle.payload.get(), result);
        return result;
    }
    if (const auto* projection = std::get_if<Projection>(&operation)) {
        auto source = evaluate_node(projection->input, context, cache);
        if (!std::holds_alternative<Rows>(source)) return source;
        const auto& rows = std::get<Rows>(source);
        Rows result{{rows.vertices.rows, projection->coordinates.size(),
                        Vector(rows.vertices.rows * projection->coordinates.size())},
                    {rows.rays.rows, projection->coordinates.size(),
                        Vector(rows.rays.rows * projection->coordinates.size())}};
        const auto select = [&](const Matrix& input, Matrix& output) {
            for (std::size_t row = 0; row < input.rows; ++row) {
                if (stopped(context)) return false;
                for (std::size_t column = 0; column < output.cols; ++column)
                    output.values[row * output.cols + column] =
                        input.values[row * input.cols + projection->coordinates[column]];
            }
            return true;
        };
        if (!select(rows.vertices, result.vertices) || !select(rows.rays, result.rays)) return stop(context);
        cache.emplace(handle.payload.get(), result);
        return result;
    }
    if (const auto* sum = std::get_if<MinkowskiSum>(&operation)) {
        auto left = evaluate_node(sum->left, context, cache);
        if (!std::holds_alternative<Rows>(left)) return left;
        auto right = evaluate_node(sum->right, context, cache);
        if (!std::holds_alternative<Rows>(right)) return right;
        const auto& a = std::get<Rows>(left);
        const auto& b = std::get<Rows>(right);
        if (!a.vertices.rows || !b.vertices.rows) {
            Rows result{{0, handle.metadata.dimension, {}}, {0, handle.metadata.dimension, {}}};
            cache.emplace(handle.payload.get(), result);
            return result;
        }
        Rows result{{a.vertices.rows * b.vertices.rows, handle.metadata.dimension,
                        Vector(a.vertices.rows * b.vertices.rows * handle.metadata.dimension)},
                    {a.rays.rows + b.rays.rows, handle.metadata.dimension,
                        Vector((a.rays.rows + b.rays.rows) * handle.metadata.dimension)}};
        std::size_t output_row = 0;
        for (std::size_t i = 0; i < a.vertices.rows; ++i) {
            for (std::size_t j = 0; j < b.vertices.rows; ++j) {
                if (stopped(context)) return stop(context);
                for (std::size_t column = 0; column < result.vertices.cols; ++column) {
                    const double value = a.vertices.values[i * a.vertices.cols + column] +
                        b.vertices.values[j * b.vertices.cols + column];
                    if (!std::isfinite(value))
                        return Unsupported{error("lazy.arithmetic", "Summed vertex is nonfinite.")};
                    result.vertices.values[output_row * result.vertices.cols + column] = value;
                }
                ++output_row;
            }
        }
        std::copy(a.rays.values.begin(), a.rays.values.end(), result.rays.values.begin());
        std::copy(b.rays.values.begin(), b.rays.values.end(),
            result.rays.values.begin() + static_cast<std::ptrdiff_t>(a.rays.values.size()));
        cache.emplace(handle.payload.get(), result);
        return result;
    }
    return Unsupported{error("lazy.operation", "Expression has an unsupported operation.",
        DiagnosticCode::evidence_mismatch)};
}
RowResult evaluate(const SetHandle& handle, const ExecutionContext& context) {
    RowCache cache;
    return evaluate_node(handle, context, cache);
}

class Workspace final : public RepresentationConverterWorkspace {
    MaterializationBudget budget_;
public:
    explicit Workspace(MaterializationBudget budget) : budget_(budget) {}
    SetTransformOutcome convert(const ConversionRequest& request, const ExecutionContext& context) override {
        if (stopped(context)) return stop(context);
        if (auto failures = request_shape(request); !failures.empty()) return Unsupported{std::move(failures)};
        auto estimated = estimate(request.input);
        if (const auto* failure = std::get_if<Diagnostics>(&estimated)) return Unsupported{*failure};
        if (auto failures = check_budget(std::get<RepresentationGrowth>(estimated), budget_); !failures.empty())
            return Unsupported{std::move(failures)};
        auto rows = evaluate(request.input, context);
        if (const auto* failure = std::get_if<Unsupported>(&rows)) return *failure;
        if (const auto* interrupted = std::get_if<OperationStopped>(&rows)) return *interrupted;
        const auto& matrices = std::get<Rows>(rows);
        auto inspected = inspect_expression(request.input);
        if (const auto* failure = std::get_if<Diagnostics>(&inspected)) return Unsupported{*failure};
        const auto& labels = std::get<ExpressionDescription>(inspected).coordinate_labels;
        auto vertices = numeric::snapshot(matrices.vertices);
        if (const auto* failure = std::get_if<Diagnostic>(&vertices)) return Unsupported{{*failure}};
        auto rays = numeric::snapshot(matrices.rays);
        if (const auto* failure = std::get_if<Diagnostic>(&rays)) return Unsupported{{*failure}};
        auto data = sets::make_v({{request.identity.ideal_output.value}, request.input.metadata.dimension, labels},
            {std::get<numeric::MatrixView>(std::move(vertices)),
             std::get<numeric::MatrixView>(std::move(rays))});
        if (const auto* failure = std::get_if<Diagnostic>(&data)) return Unsupported{{*failure}};
        GeometryEvidence evidence{{request.identity, {request.input.id}}, GeometryClaimScope::set_relation,
            Unestablished{}, {"V enumeration follows the expression over binary64 values; rounding is not validated."}, {}};
        if (auto failures = check_geometry_evidence(evidence, request); !failures.empty())
            return Unsupported{std::move(failures)};
        if (stopped(context)) return stop(context);
        return OperationResult{std::get<sets::SetData>(std::move(data)).as_handle(),
            SetRelation::equivalent, std::move(evidence)};
    }
};

RequestProvenance provenance(const ConversionRequest& request,
        const registry::PreparedProvider<registry::ConversionPort>& provider) {
    const auto& selected = provider.provenance();
    return {request.identity.request, selected.port, selected.requested.id,
        selected.requested.version,
        selected.actual ? std::optional<ModuleId>{selected.actual->id} : std::nullopt,
        selected.actual ? std::optional<std::string>{selected.actual->version} : std::nullopt};
}
} // namespace

registry::Registration<registry::ConversionPort> make_materializer(MaterializationBudget budget) {
    return {{{module}, "1.0.0"},
        [budget](const ConversionRequest& request, const registry::Requirements& requirements)
            -> registry::Capability {
            if (auto failures = request_shape(request); !failures.empty()) return failures;
            if (requirements.output.assurance != Assurance::numerical)
                return error("lazy.assurance", "Validated lazy materialization is unavailable.");
            if (requirements.output.relation && *requirements.output.relation != SetRelation::equivalent)
                return error("lazy.relation", "Lazy materialization offers equivalent mathematical relation only.");
            auto growth = estimate(request.input);
            if (const auto* failure = std::get_if<Diagnostics>(&growth)) return *failure;
            if (auto failures = check_budget(std::get<RepresentationGrowth>(growth), budget); !failures.empty())
                return failures;
            registry::Output output;
            output.representation = request.output;
            output.relation = SetRelation::equivalent;
            return registry::Offer{output};
        },
        [budget](const ConversionRequest&) { return std::make_unique<Workspace>(budget); }};
}

MaterializationOutcome materialize_expression(const ConversionRequest& request,
        MaterializationBudget budget,
        const registry::PreparedProvider<registry::ConversionPort>& provider,
        const ExecutionContext& context) {
    RepresentationGrowth growth;
    std::vector<GeometryEvidence> lineage;
    if (auto estimated = estimate(request.input); std::holds_alternative<RepresentationGrowth>(estimated))
        growth = std::get<RepresentationGrowth>(estimated);
    collect_lineage(request.input, lineage);
    const auto selected = provenance(request, provider);
    const auto reference = GeometryReference{request.identity, {request.input.id}};
    const auto failure = [&](auto cause) -> MaterializationOutcome {
        return MaterializationFailure{reference, selected, lineage, growth, budget, std::move(cause)};
    };
    if (stopped(context)) return failure(stop(context));
    if (auto failures = check_budget(growth, budget); !failures.empty())
        return failure(Unsupported{std::move(failures)});
    auto admitted = provider.prepare(request);
    if (const auto* rejected = std::get_if<registry::Rejection>(&admitted))
        return failure(Unsupported{rejected->diagnostics});
    auto prepared = std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(admitted));
    auto outcome = std::get<0>(prepared.create())->run(context);
    if (const auto* rejected = std::get_if<Unsupported>(&outcome)) return failure(*rejected);
    if (const auto* interrupted = std::get_if<OperationStopped>(&outcome)) return failure(*interrupted);
    auto result = std::get<OperationResult>(std::move(outcome));
    if (result.relation != SetRelation::equivalent || result.output.metadata.representation != request.output ||
        result.output.metadata.dimension != request.input.metadata.dimension ||
        !check_geometry_evidence(result.evidence, request).empty())
        return failure(Unsupported{error("lazy.result", "Materializer changed the admitted relation or schema.",
            DiagnosticCode::evidence_mismatch)});
    auto data = sets::from_handle(result.output);
    if (const auto* rejected = std::get_if<Diagnostic>(&data)) return failure(Unsupported{{*rejected}});
    const auto native = std::get<sets::SetData>(std::move(data)).representation();
    const auto* v = std::get_if<sets::VRepresentation>(&native);
    if (!v) return failure(Unsupported{error("lazy.result", "Materializer returned a non-V payload.",
        DiagnosticCode::evidence_mismatch)});
    growth.realized_vertices = v->vertices.rows();
    growth.realized_rays = v->rays.rows();
    return MaterializationResult{std::move(result), selected, std::move(lineage), growth, budget};
}
} // namespace csl::geometry::lazy
