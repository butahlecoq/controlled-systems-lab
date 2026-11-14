#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/comparison_manifest.hpp>

#include <fstream>
#include <iterator>
#include <string>

TEST_CASE("MPC-01 comparison records pass artifact manifest validation") {
    std::ifstream input(CSL_MPC01_COMPARISON_RECORDS_FILE, std::ios::binary);
    REQUIRE(input.good());

    std::size_t records = 0;
    std::string line;
    while (std::getline(input, line)) {
        // Treat CRLF as JSONL framing; the carriage return is not record content.
        if (!line.empty() && line.back() == '\r')
            line.pop_back();
        if (line.empty())
            continue;
        const auto decoded = csl::artifacts::decode_recorded_comparison(line);
        if (const auto *error = std::get_if<csl::artifacts::ArtifactError>(&decoded)) {
            FAIL("MPC-01 comparison record " << records << " rejected at " << error->path << ": "
                                             << error->message);
        }
        CHECK(std::holds_alternative<csl::artifacts::RecordedComparisonArtifact>(decoded));
        ++records;
    }
    REQUIRE(input.eof());
    CHECK(records == 7);
}

void check_strategy_ab_record(const char *path) {
    std::ifstream input(path, std::ios::binary);
    REQUIRE(input.good());
    const std::string wire{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
    CHECK_FALSE(input.bad());
    REQUIRE_FALSE(wire.empty());
    CHECK(wire.back() != '\n');

    const auto decoded = csl::artifacts::decode_recorded_comparison(wire);
    if (const auto *error = std::get_if<csl::artifacts::ArtifactError>(&decoded)) {
        FAIL("MPC-01 Strategy A/B comparison rejected at " << error->path << ": "
                                                           << error->message);
    }
    CHECK(std::holds_alternative<csl::artifacts::RecordedComparisonArtifact>(decoded));
}

TEST_CASE("MPC-01 Strategy A/B record passes the artifact codec") {
    check_strategy_ab_record(CSL_MPC01_STRATEGY_AB_RECORD_FILE);
}

TEST_CASE("MPC-01 resource-limited Strategy A/B record passes the artifact codec") {
    check_strategy_ab_record(CSL_MPC01_LIMITED_STRATEGY_AB_RECORD_FILE);
}

TEST_CASE("MPC-01 resource-limited T-S02 Strategy A/B record passes the artifact codec") {
    check_strategy_ab_record(CSL_MPC01_TS02_LIMITED_STRATEGY_AB_RECORD_FILE);
}
