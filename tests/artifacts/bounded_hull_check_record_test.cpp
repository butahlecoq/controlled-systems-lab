#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/bounded_hull_check.hpp>

#include <chrono>
#include <string>
#include <vector>

using csl::Vector;
using namespace csl;

namespace {
std::string replace_json_field(std::string text, const std::string& field,
                               const std::string& value) {
    const auto key = text.find("\"" + field + "\":");
    REQUIRE(key != std::string::npos);
    const auto begin = key + field.size() + 3;
    const auto end = text.find_first_of(",}", begin);
    REQUIRE(end != std::string::npos);
    text.replace(begin, end - begin, value);
    return text;
}
} // namespace

TEST_CASE("bounded checker statuses and evidence survive canonical record encoding") {
    const std::vector<Vector> square{{0,0}, {2,0}, {2,2}, {0,2}, {1,1}};
    const auto digest = std::get<geometry::HullInputDigest>(geometry::digest_hull_input(square));
    for (const auto& indices : std::vector<std::vector<std::size_t>>{{0,1,2,3}, {0,1,2}}) {
        const auto checked = geometry::check_source_index_hull(square, {digest, indices},
            {std::chrono::milliseconds{30}, 8});
        const auto encoded = artifacts::encode_bounded_hull_check(checked);
        REQUIRE(std::holds_alternative<std::string>(encoded));
        const auto decoded = artifacts::decode_bounded_hull_check(std::get<std::string>(encoded));
        REQUIRE(std::holds_alternative<geometry::HullCheckRecord>(decoded));
        const auto& record = std::get<geometry::HullCheckRecord>(decoded);
        CHECK(record.status == checked.status);
        CHECK(record.input_digest == digest);
        CHECK(record.budget.wall == std::chrono::milliseconds{30});
        CHECK(record.budget.max_points == 8);
        CHECK(record.elapsed == checked.elapsed);
        CHECK(record.evidence_scope == "exact represented binary64 2D finite hull");
        CHECK(record.reason == checked.reason);
        CHECK(record.counterexample_index == checked.counterexample_index);
    }
    const auto timeout = geometry::check_source_index_hull(square, {digest, {0,1,2,3}},
        {std::chrono::milliseconds{0}, 8});
    CHECK(timeout.status == geometry::HullCheckStatus::inconclusive);
    const auto encoded = artifacts::encode_bounded_hull_check(timeout);
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto decoded = artifacts::decode_bounded_hull_check(std::get<std::string>(encoded));
    REQUIRE(std::holds_alternative<geometry::HullCheckRecord>(decoded));
    CHECK(std::get<geometry::HullCheckRecord>(decoded).status == geometry::HullCheckStatus::inconclusive);
}

TEST_CASE("malformed status and forged evidence are refused by record contract") {
    auto smoke = geometry::run_bounded_square_smoke().checker;
    const auto encoded = artifacts::encode_bounded_hull_check(smoke);
    REQUIRE(std::holds_alternative<std::string>(encoded));
    std::string forged = std::get<std::string>(encoded);
    const auto at = forged.find("verified");
    REQUIRE(at != std::string::npos);
    forged.replace(at, 8, "unknown!");
    CHECK(std::holds_alternative<artifacts::ArtifactError>(
        artifacts::decode_bounded_hull_check(forged)));
    smoke.input_digest.reset();
    CHECK(std::holds_alternative<artifacts::ArtifactError>(
        artifacts::encode_bounded_hull_check(smoke)));

    const std::vector<Vector> square{{0,0}, {2,0}, {2,2}, {0,2}, {1,1}};
    auto incorrect = geometry::check_source_index_hull(square,
        {std::get<geometry::HullInputDigest>(geometry::digest_hull_input(square)), {0,1,2}});
    REQUIRE(incorrect.status == geometry::HullCheckStatus::incorrect);
    incorrect.input_digest.reset();
    CHECK(std::holds_alternative<artifacts::ArtifactError>(
        artifacts::encode_bounded_hull_check(incorrect)));
}

TEST_CASE("record decoder rejects negative and fractional integer fields") {
    auto checked = geometry::run_bounded_square_smoke().checker;
    const auto encoded = artifacts::encode_bounded_hull_check(checked);
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto& base = std::get<std::string>(encoded);
    for (const auto& [field, bad_value] : std::vector<std::pair<std::string, std::string>>{
             {"max_points", "-1"}, {"max_points", "1.5"}, {"budget_ms", "1.5"},
             {"elapsed_ns", "-1"}, {"elapsed_ns", "0.5"}}) {
        const auto malformed = replace_json_field(base, field, bad_value);
        CHECK(std::holds_alternative<artifacts::ArtifactError>(
            artifacts::decode_bounded_hull_check(malformed)));
    }
}
