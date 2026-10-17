#include <csl/artifacts/bounded_hull_check.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <limits>
#include <stdexcept>

namespace csl::artifacts {
namespace {
using Json = nlohmann::json;

ArtifactError invalid(std::string message) {
    return {ArtifactErrorCode::invalid_input, "bounded_hull_check", std::move(message)};
}

std::string status_name(geometry::HullCheckStatus status) {
    switch (status) {
    case geometry::HullCheckStatus::verified: return "verified";
    case geometry::HullCheckStatus::incorrect: return "incorrect";
    case geometry::HullCheckStatus::inconclusive: return "inconclusive";
    }
    return {};
}

geometry::HullCheckStatus parse_status(const std::string& text) {
    if (text == "verified") return geometry::HullCheckStatus::verified;
    if (text == "incorrect") return geometry::HullCheckStatus::incorrect;
    if (text == "inconclusive") return geometry::HullCheckStatus::inconclusive;
    throw std::invalid_argument("Unknown checker status");
}

std::optional<problem::ContentDigest> parse_digest(const Json& value) {
    if (value.is_null()) return std::nullopt;
    const auto text = value.get<std::string>();
    if (text.size() != 64) throw std::invalid_argument("Invalid input digest length");
    problem::ContentDigest digest{};
    for (std::size_t i = 0; i < digest.bytes.size(); ++i) {
        const auto digit = [](char ch) -> unsigned {
            if (ch >= '0' && ch <= '9') return static_cast<unsigned>(ch - '0');
            if (ch >= 'a' && ch <= 'f') return static_cast<unsigned>(ch - 'a' + 10);
            throw std::invalid_argument("Invalid input digest hex");
        };
        digest.bytes[i] = static_cast<std::byte>((digit(text[2*i]) << 4) | digit(text[2*i+1]));
    }
    return digest;
}

void validate(const geometry::HullCheckRecord& record) {
    if (status_name(record.status).empty() || record.budget.wall.count() < 0 ||
        record.elapsed.count() < 0 || record.reason.empty() || record.reason.size() > 512 ||
        record.evidence_scope != "exact represented binary64 2D finite hull" ||
        (record.status != geometry::HullCheckStatus::inconclusive && !record.input_digest) ||
        (record.status == geometry::HullCheckStatus::verified && record.counterexample_index) ||
        (record.status != geometry::HullCheckStatus::incorrect && record.counterexample_index))
        throw std::invalid_argument("Inconsistent checker fields");
}
} // namespace

ArtifactResult<std::string> encode_bounded_hull_check(const geometry::HullCheckRecord& record) {
    try {
        validate(record);
        Json wire{{"schema", "csl.bounded-hull-check/1"},
            {"status", status_name(record.status)},
            {"input_digest", record.input_digest ? Json(problem::hex(*record.input_digest)) : Json(nullptr)},
            {"budget_ms", record.budget.wall.count()},
            {"max_points", record.budget.max_points},
            {"elapsed_ns", record.elapsed.count()},
            {"evidence_scope", record.evidence_scope},
            {"reason", record.reason},
            {"counterexample_index", record.counterexample_index ? Json(*record.counterexample_index) : Json(nullptr)}};
        return wire.dump();
    } catch (const std::bad_alloc&) {
        return ArtifactError{ArtifactErrorCode::allocation, "bounded_hull_check", "Allocation failed"};
    } catch (const std::exception& failure) {
        return invalid(failure.what());
    }
}

ArtifactResult<geometry::HullCheckRecord> decode_bounded_hull_check(std::string_view text) {
    if (text.size() > 4096) return ArtifactError{ArtifactErrorCode::limit,
        "bounded_hull_check", "Record exceeds byte capacity"};
    try {
        auto wire = Json::parse(text.begin(), text.end());
        if (!wire.is_object() || wire.size() != 9 || wire.dump() != text ||
            wire.at("schema") != "csl.bounded-hull-check/1")
            return invalid("Checker record is not canonical schema /1");
        geometry::HullCheckRecord record;
        record.status = parse_status(wire.at("status").get<std::string>());
        record.input_digest = parse_digest(wire.at("input_digest"));
        const auto budget_ms = wire.at("budget_ms").get<std::int64_t>();
        const auto max_points = wire.at("max_points").get<std::uint64_t>();
        const auto elapsed_ns = wire.at("elapsed_ns").get<std::int64_t>();
        if (max_points > std::numeric_limits<std::size_t>::max())
            return invalid("Checker point capacity exceeds platform size");
        record.budget = {std::chrono::milliseconds{budget_ms}, static_cast<std::size_t>(max_points)};
        record.elapsed = std::chrono::nanoseconds{elapsed_ns};
        record.evidence_scope = wire.at("evidence_scope").get<std::string>();
        record.reason = wire.at("reason").get<std::string>();
        if (!wire.at("counterexample_index").is_null()) {
            const auto index = wire.at("counterexample_index").get<std::uint64_t>();
            if (index > std::numeric_limits<std::size_t>::max())
                return invalid("Counterexample index exceeds platform size");
            record.counterexample_index = static_cast<std::size_t>(index);
        }
        validate(record);
        return record;
    } catch (const std::bad_alloc&) {
        return ArtifactError{ArtifactErrorCode::allocation, "bounded_hull_check", "Allocation failed"};
    } catch (const std::exception&) {
        return invalid("Malformed checker record");
    }
}

} // namespace csl::artifacts
