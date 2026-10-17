#include <csl/geometry/polyhedral_support.hpp>

#include "../exact_dyadic.hpp"

#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <utility>

namespace csl::geometry::polyhedral {
namespace {
using detail::exact_detail::Integer;
constexpr const char* module = "csl.geometry.polyhedral-support";

Diagnostics error(std::string field, std::string reason,
        DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{code, std::move(field), std::move(reason)}};
}

bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now() >= *context.deadline);
}

OperationStopped stop(const ExecutionContext& context) {
    return {context.cancellation.stop_requested() ? StopReason::cancelled : StopReason::deadline_expired,
        "Support query stopped before publishing a result."};
}

bool valid_identity(const GeometryRequestIdentity& identity) {
    return !identity.problem.value.empty() && !identity.request.value.empty() &&
        !identity.ideal_output.value.empty();
}

bool dot(const Vector& direction, const numeric::MatrixView& vectors,
        std::size_t row, Integer& result) {
    if (direction.size() != vectors.cols()) return false;
    result = {};
    for (std::size_t column = 0; column < direction.size(); ++column) {
        const double lhs = direction[column];
        const double rhs = vectors(row, column);
        if (!std::isfinite(lhs) || !std::isfinite(rhs) ||
            !detail::exact_detail::add_product(result,
                detail::exact_detail::decode(lhs), detail::exact_detail::decode(rhs))) return false;
    }
    return true;
}

int compare(const Integer& left, const Integer& right) {
    if (left.negative != right.negative) return left.negative ? -1 : 1;
    const int magnitude = detail::exact_detail::compare_magnitude(left, right);
    return left.negative ? -magnitude : magnitude;
}

std::optional<double> nearest_binary64(const Integer& exact) {
    if (detail::exact_detail::is_zero(exact)) return 0.0;
    std::size_t highest = detail::exact_detail::limb_count * 64;
    for (std::size_t limb = detail::exact_detail::limb_count; limb-- > 0;) {
        if (!exact.limbs[limb]) continue;
        highest = limb * 64 + (63U - static_cast<unsigned>(std::countl_zero(exact.limbs[limb])));
        break;
    }

    const bool subnormal = highest < 1126; // Exact value is below 2^-1022.
    const std::size_t shift = subnormal ? 1074 : highest - 52;
    auto significand = detail::exact_detail::shifted_low_bits(exact, shift);
    const bool half_bit = shift != 0 &&
        ((exact.limbs[(shift - 1) / 64] >> ((shift - 1) % 64)) & 1U) != 0;
    const bool below_half = shift > 1 && detail::exact_detail::has_bits_below(exact, shift - 1);
    if (half_bit && (below_half || (significand & 1U))) ++significand;
    std::uint64_t bits = 0;
    if (subnormal) {
        if (significand > (std::uint64_t{1} << 52)) return std::nullopt;
        bits = significand; // Includes rounding up to the smallest normal.
    } else {
        int exponent = static_cast<int>(highest) + detail::exact_detail::common_exponent;
        if (significand == (std::uint64_t{1} << 53)) {
            significand >>= 1;
            ++exponent;
        }
        if (exponent > 1023) return std::nullopt;
        bits = (static_cast<std::uint64_t>(exponent + 1023) << 52) |
            (significand - (std::uint64_t{1} << 52));
    }
    if (exact.negative) bits |= std::uint64_t{1} << 63;
    return std::bit_cast<double>(bits);
}

OperationOutcome unsupported(std::string field, std::string reason,
        DiagnosticCode code = DiagnosticCode::unsupported) {
    return Unsupported{error(std::move(field), std::move(reason), code)};
}

class SupportWorkspace final : public SetOperatorWorkspace {
    OperationRequest request_;
public:
    explicit SupportWorkspace(OperationRequest request) : request_(std::move(request)) {}

    OperationOutcome apply(const OperationRequest&, const ExecutionContext& context) override {
        if (stopped(context)) return stop(context);
        if (request_.assurance != Assurance::numerical)
            return unsupported("support.assurance", "Validated support evidence is not implemented.");
        if (!valid_identity(request_.identity))
            return unsupported("support.identity", "Complete immutable request identity required.", DiagnosticCode::invalid_input);
        const auto* query = std::get_if<SupportQuery>(&request_.operation);
        if (!query) return unsupported("support.operation", "Only SupportQuery is implemented.");
        if (const auto shape = check_operation_shape(request_); !shape.empty())
            return Unsupported{shape};
        if (std::any_of(query->direction.begin(), query->direction.end(),
                [](double value) { return !std::isfinite(value); }))
            return unsupported("support.direction", "Direction entries must be finite binary64 values.", DiagnosticCode::invalid_input);
        auto data_result = sets::from_handle(query->input);
        if (const auto* failure = std::get_if<Diagnostic>(&data_result)) return Unsupported{{*failure}};
        const auto data = std::get<sets::SetData>(std::move(data_result));
        const auto representation = data.representation();
        const GeometryReference reference{request_.identity, {query->input.id}};
        const auto evidence = [&](std::string assumptions) {
            return GeometryEvidence{reference, GeometryClaimScope::support_value,
                SymbolicArgument{"support over represented binary64 generators", std::move(assumptions)}, {}, {}};
        };
        if (std::holds_alternative<sets::EmptyRepresentation>(representation)) {
            const auto proof = evidence("Empty set has no support maximizer.");
            if (const auto errors = check_geometry_evidence(proof, request_); !errors.empty())
                return Unsupported{errors};
            if (stopped(context)) return stop(context);
            return SupportResult{EmptySupport{}, {}, proof};
        }
        const auto* v = std::get_if<sets::VRepresentation>(&representation);
        if (!v) return unsupported("support.representation", "Only native V and empty set representations are supported.");
        if (v->vertices.rows() == 0) {
            const auto proof = evidence("V={ }+cone(R) is empty because it has no vertices.");
            if (const auto errors = check_geometry_evidence(proof, request_); !errors.empty())
                return Unsupported{errors};
            if (stopped(context)) return stop(context);
            return SupportResult{EmptySupport{}, {}, proof};
        }

        for (std::size_t row = 0; row < v->rays.rows(); ++row) {
            if (stopped(context)) return stop(context);
            Integer ray_dot;
            if (!dot(query->direction, v->rays, row, ray_dot))
                return unsupported("support.ray_dot", "Exact dyadic ray dot product exceeded its checked arithmetic range.");
            if (!detail::exact_detail::is_zero(ray_dot) && !ray_dot.negative) {
                const auto proof = evidence(
                    "A ray has strictly positive exact dyadic direction dot product, so support is unbounded.");
                if (const auto errors = check_geometry_evidence(proof, request_); !errors.empty())
                    return Unsupported{errors};
                if (stopped(context)) return stop(context);
                return SupportResult{UnboundedSupport{}, {}, proof};
            }
        }

        Integer maximum;
        std::size_t maximizer_index = 0;
        for (std::size_t row = 0; row < v->vertices.rows(); ++row) {
            if (stopped(context)) return stop(context);
            Integer value;
            if (!dot(query->direction, v->vertices, row, value))
                return unsupported("support.vertex_dot", "Exact dyadic vertex dot product exceeded its checked arithmetic range.");
            if (row == 0 || compare(value, maximum) > 0) {
                maximum = value;
                maximizer_index = row;
            }
        }
        const auto scalar = nearest_binary64(maximum);
        if (!scalar || !std::isfinite(*scalar))
            return unsupported("support.value", "Finite exact support value has no finite binary64 representation.");
        Vector maximizer(v->vertices.cols());
        for (std::size_t column = 0; column < maximizer.size(); ++column)
            maximizer[column] = v->vertices(maximizer_index, column);
        const auto proof = evidence("The exact maximum of vertex dot products is returned rounded to nearest binary64; every ray has nonpositive exact dyadic direction dot product, so this maximum is attained and finite.");
        if (const auto errors = check_geometry_evidence(proof, request_); !errors.empty()) return Unsupported{errors};
        if (stopped(context)) return stop(context);
        return SupportResult{*scalar, std::move(maximizer), proof};
    }
};

registry::Capability capabilities(const OperationRequest& request,
        const registry::Requirements& requirements) {
    if (!std::holds_alternative<SupportQuery>(request.operation))
        return error("support.operation", "Only SupportQuery is implemented.");
    if (request.assurance != Assurance::numerical || requirements.output.assurance != Assurance::numerical)
        return error("support.assurance", "Validated support evidence is not implemented.");
    if (!valid_identity(request.identity))
        return error("support.identity", "Complete immutable request identity required.", DiagnosticCode::invalid_input);
    if (const auto shape = check_operation_shape(request); !shape.empty()) return shape;
    const auto& query = std::get<SupportQuery>(request.operation);
    if (std::any_of(query.direction.begin(), query.direction.end(),
            [](double value) { return !std::isfinite(value); }))
        return error("support.direction", "Direction entries must be finite binary64 values.", DiagnosticCode::invalid_input);
    const auto data = sets::from_handle(query.input);
    if (const auto* failure = std::get_if<Diagnostic>(&data)) return Diagnostics{*failure};
    const auto representation = std::get<sets::SetData>(data).representation();
    if (!std::holds_alternative<sets::VRepresentation>(representation) &&
        !std::holds_alternative<sets::EmptyRepresentation>(representation))
        return error("support.representation", "Only native V and empty set representations are supported.");
    registry::Output output;
    output.assurance = Assurance::numerical;
    return registry::Offer{output};
}
} // namespace

registry::Registration<registry::GeometryPort> make_support_registration() {
    return {{{module}, "1.0.0"}, capabilities,
        [](const OperationRequest& request) { return std::make_unique<SupportWorkspace>(request); }};
}
} // namespace csl::geometry::polyhedral
