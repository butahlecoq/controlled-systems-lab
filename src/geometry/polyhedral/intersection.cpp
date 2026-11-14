#include <csl/geometry/polyhedral_intersection.hpp>

#include <chrono>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>

namespace csl::geometry::polyhedral {
namespace {
Diagnostic invalid(const char *field, const char *explanation) {
    return {DiagnosticCode::invalid_input, field, explanation};
}
std::optional<sets::SetData> make_h(const SetId &id, std::size_t dimension,
                                    std::vector<std::string> labels, const Matrix &a,
                                    const Vector &b, const Matrix &e, const Vector &f) {
    auto av = numeric::snapshot(a);
    auto bv = numeric::snapshot_vector(b);
    auto ev = numeric::snapshot(e);
    auto fv = numeric::snapshot_vector(f);
    if (!std::holds_alternative<numeric::MatrixView>(av) ||
        !std::holds_alternative<numeric::VectorView>(bv) ||
        !std::holds_alternative<numeric::MatrixView>(ev) ||
        !std::holds_alternative<numeric::VectorView>(fv))
        return {};
    auto made =
        sets::make_h({id, dimension, std::move(labels)},
                     {std::get<numeric::MatrixView>(av), std::get<numeric::VectorView>(bv),
                      std::get<numeric::MatrixView>(ev), std::get<numeric::VectorView>(fv)});
    if (auto *set = std::get_if<sets::SetData>(&made))
        return *set;
    return {};
}
} // namespace

SetResult intersect_h(const sets::SetData &left, const sets::SetData &right, SetId output_id) {
    if (output_id.value.empty())
        return Diagnostics{
            invalid("geometry.intersection.id", "Output set identity must be nonempty.")};
    const auto left_metadata = left.metadata();
    const auto right_metadata = right.metadata();
    if (left_metadata->set.dimension != right_metadata->set.dimension)
        return Diagnostics{invalid("geometry.intersection.dimension",
                                   "H operands must have the same ambient dimension.")};
    if (left_metadata->coordinate_labels != right_metadata->coordinate_labels)
        return Diagnostics{invalid("geometry.intersection.coordinates",
                                   "H operands must use the same coordinate labels and ordering.")};
    const auto left_representation = left.representation();
    const auto right_representation = right.representation();
    const auto *a = std::get_if<sets::HRepresentation>(&left_representation);
    const auto *b = std::get_if<sets::HRepresentation>(&right_representation);
    if (!a || !b)
        return Diagnostics{
            {DiagnosticCode::unsupported, "geometry.intersection.representation",
             "This operation accepts native H representations; convert other representations first."}};
    if (a->inequalities.rows() > std::numeric_limits<std::size_t>::max() - b->inequalities.rows() ||
        a->equalities.rows() > std::numeric_limits<std::size_t>::max() - b->equalities.rows())
        return Diagnostics{
            invalid("geometry.intersection.capacity", "Combined row count overflows size_t.")};
    const auto dimension = left_metadata->set.dimension;
    const auto inequality_count = a->inequalities.rows() + b->inequalities.rows();
    const auto equality_count = a->equalities.rows() + b->equalities.rows();
    if (dimension && inequality_count > std::numeric_limits<std::size_t>::max() / dimension)
        return Diagnostics{invalid("geometry.intersection.capacity",
                                   "Combined inequality matrix size overflows size_t.")};
    if (dimension && equality_count > std::numeric_limits<std::size_t>::max() / dimension)
        return Diagnostics{invalid("geometry.intersection.capacity",
                                   "Combined equality matrix size overflows size_t.")};

    Matrix inequalities{inequality_count, dimension, {}};
    inequalities.values.reserve(inequality_count * dimension);
    Vector bounds;
    bounds.reserve(inequality_count);
    for (const auto *h : {a, b}) {
        for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
            for (std::size_t j = 0; j < dimension; ++j)
                inequalities.values.push_back(h->inequalities(i, j));
            bounds.push_back(h->upper_bounds[i]);
        }
    }
    Matrix equalities{equality_count, dimension, {}};
    equalities.values.reserve(equality_count * dimension);
    Vector values;
    values.reserve(equality_count);
    for (const auto *h : {a, b}) {
        for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
            for (std::size_t j = 0; j < dimension; ++j)
                equalities.values.push_back(h->equalities(i, j));
            values.push_back(h->equality_values[i]);
        }
    }
    auto result = make_h(output_id, dimension, left_metadata->coordinate_labels, inequalities,
                         bounds, equalities, values);
    if (!result)
        return Diagnostics{invalid("geometry.intersection.storage",
                                   "Could not create immutable intersection data.")};
    return *result;
}
namespace {
constexpr const char *intersection_module = "csl.geometry.polyhedral-intersection";

Diagnostics registration_error(std::string field, std::string explanation,
                               DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{code, std::move(field), std::move(explanation)}};
}

bool complete_identity(const GeometryRequestIdentity &identity) {
    return !identity.problem.value.empty() && !identity.request.value.empty() &&
           !identity.ideal_output.value.empty();
}

bool stopped(const ExecutionContext &context) {
    return context.cancellation.stop_requested() ||
           (context.deadline && std::chrono::steady_clock::now() >= *context.deadline);
}

OperationStopped stop_reason(const ExecutionContext &context) {
    if (context.cancellation.stop_requested())
        return {StopReason::cancelled,
                "Native H intersection cancelled before publishing its result."};
    return {StopReason::deadline_expired,
            "Native H intersection deadline expired before publishing its result."};
}

Diagnostics h_operands(const Intersection &operation) {
    const auto left = sets::from_handle(operation.left);
    if (const auto *failure = std::get_if<Diagnostic>(&left))
        return {*failure};
    const auto right = sets::from_handle(operation.right);
    if (const auto *failure = std::get_if<Diagnostic>(&right))
        return {*failure};
    const auto &left_data = std::get<sets::SetData>(left);
    const auto &right_data = std::get<sets::SetData>(right);
    if (!std::holds_alternative<sets::HRepresentation>(left_data.representation()) ||
        !std::holds_alternative<sets::HRepresentation>(right_data.representation()))
        return registration_error(
            "geometry.intersection.representation",
            "Registered native intersection accepts H operands; convert other representations explicitly.");
    if (left_data.metadata()->set.dimension != right_data.metadata()->set.dimension)
        return registration_error("geometry.intersection.dimension",
                                  "H operands must have the same ambient dimension.",
                                  DiagnosticCode::invalid_input);
    if (left_data.metadata()->coordinate_labels != right_data.metadata()->coordinate_labels)
        return registration_error("geometry.intersection.coordinates",
                                  "H operands must use the same coordinate labels and ordering.",
                                  DiagnosticCode::invalid_input);
    return {};
}

registry::Capability intersection_capabilities(const OperationRequest &request,
                                               const registry::Requirements &requirements) {
    if (!std::holds_alternative<Intersection>(request.operation))
        return registration_error("geometry.intersection.operation",
                                  "Only native H Intersection is supported.");
    if (!complete_identity(request.identity))
        return registration_error("geometry.intersection.identity",
                                  "Complete immutable request identity required.",
                                  DiagnosticCode::invalid_input);
    if (request.assurance != Assurance::numerical ||
        requirements.output.assurance != Assurance::numerical)
        return registration_error("geometry.intersection.assurance",
                                  "Validated intersection arithmetic is not implemented.");
    if (request.required_relation != SetRelation::equivalent ||
        (requirements.output.relation && *requirements.output.relation != SetRelation::equivalent))
        return registration_error("geometry.intersection.relation",
                                  "Only equivalent numerical H intersections are supported.");
    if (requirements.output.representation.value != "csl.polyhedron.h")
        return registration_error("geometry.intersection.output",
                                  "Registered intersection produces native H.");
    if (const auto shape = check_operation_shape(request); !shape.empty())
        return shape;
    const auto diagnostics = h_operands(std::get<Intersection>(request.operation));
    if (!diagnostics.empty())
        return diagnostics;
    registry::Output output;
    output.representation = {"csl.polyhedron.h"};
    output.assurance = Assurance::numerical;
    output.relation = SetRelation::equivalent;
    return registry::Offer{output};
}

class IntersectionWorkspace final : public SetOperatorWorkspace {
    OperationRequest request_;

  public:
    explicit IntersectionWorkspace(OperationRequest request) : request_(std::move(request)) {}

    OperationOutcome apply(const OperationRequest &, const ExecutionContext &context) override {
        if (stopped(context))
            return stop_reason(context);
        if (request_.assurance != Assurance::numerical ||
            request_.required_relation != SetRelation::equivalent)
            return Unsupported{
                registration_error("geometry.intersection.policy",
                                   "Only equivalent numerical intersection is implemented.")};
        if (const auto shape = check_operation_shape(request_); !shape.empty())
            return Unsupported{shape};
        const auto *operation = std::get_if<Intersection>(&request_.operation);
        if (!operation)
            return Unsupported{registration_error("geometry.intersection.operation",
                                                  "Only native H Intersection is supported.")};
        if (const auto diagnostics = h_operands(*operation); !diagnostics.empty())
            return Unsupported{diagnostics};
        try {
            auto result = intersect_h(std::get<sets::SetData>(sets::from_handle(operation->left)),
                                      std::get<sets::SetData>(sets::from_handle(operation->right)),
                                      {request_.identity.ideal_output.value});
            if (const auto *failure = std::get_if<Diagnostics>(&result))
                return Unsupported{*failure};
            if (stopped(context))
                return stop_reason(context);
            auto output = std::get<sets::SetData>(std::move(result)).as_handle();
            GeometryEvidence evidence{geometry_reference(request_),
                                      GeometryClaimScope::set_relation,
                                      Unestablished{},
                                      {},
                                      {}};
            evidence.assumptions.push_back(
                "The output concatenates the two represented H row systems as a conjunction; numerical relation is scoped to the stored binary64 rows, not validated arithmetic.");
            if (const auto errors = check_geometry_evidence(evidence, request_); !errors.empty())
                return Unsupported{errors};
            return OperationResult{std::move(output), SetRelation::equivalent, std::move(evidence)};
        } catch (const std::bad_alloc &) {
            return OperationStopped{
                StopReason::resource_limit,
                "Allocation failed while assembling native H intersection rows."};
        } catch (const std::length_error &) {
            return OperationStopped{StopReason::resource_limit,
                                    "Native H intersection rows exceed container capacity."};
        }
    }
};
} // namespace

registry::Registration<registry::GeometryPort> make_intersection_registration() {
    return {{{intersection_module}, "1.0.0"},
            intersection_capabilities,
            [](const OperationRequest &request) {
                return std::make_unique<IntersectionWorkspace>(request);
            }};
}
} // namespace csl::geometry::polyhedral
