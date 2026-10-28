#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/comparison_manifest.hpp>

#include <fstream>
#include <string>

TEST_CASE("MPC-01 comparison records pass artifact manifest validation") {
    std::ifstream input(CSL_MPC01_COMPARISON_RECORDS_FILE, std::ios::binary);
    REQUIRE(input.good());

    std::size_t records = 0;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto decoded = csl::artifacts::decode_recorded_comparison(line);
        if (const auto* error = std::get_if<csl::artifacts::ArtifactError>(&decoded)) {
            FAIL("MPC-01 comparison record " << records << " rejected at " << error->path
                << ": " << error->message);
        }
        CHECK(std::holds_alternative<csl::artifacts::RecordedComparisonArtifact>(decoded));
        ++records;
    }
    REQUIRE(input.eof());
    CHECK(records == 7);
}
