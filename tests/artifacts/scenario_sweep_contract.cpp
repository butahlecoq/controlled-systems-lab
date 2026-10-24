#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/scenario_sweep.hpp>
#include <nlohmann/json.hpp>

#include <fstream>
#include <iterator>

using namespace csl;
using namespace csl::artifacts;

namespace {
std::string read_file(const char* path) {
    std::ifstream input(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

problem::ResolvedContent content(std::string_view text) {
    std::vector<std::byte> bytes;
    bytes.reserve(text.size());
    for (const unsigned char value : text) bytes.push_back(static_cast<std::byte>(value));
    auto result = problem::snapshot_content(bytes);
    REQUIRE(std::holds_alternative<problem::ResolvedContent>(result));
    return std::get<problem::ResolvedContent>(std::move(result));
}

RecordedRunArtifact run() {
    auto decoded = decode_run(read_file(CSL_SWEEP_RUN_FIXTURE));
    REQUIRE(std::holds_alternative<RunStatistics>(decoded));
    auto recorded = encode_recorded_run(std::get<RunStatistics>(std::move(decoded)));
    REQUIRE(std::holds_alternative<RecordedRunArtifact>(recorded));
    return std::get<RecordedRunArtifact>(std::move(recorded));
}

SweepCaseInput one_case() {
    const auto fixture = nlohmann::json::parse(read_file(CSL_SWEEP_RUN_FIXTURE));
    return {"scenario-a", {fixture.at("configuration").at("id").get<std::string>()}, run(), {2, 1e-9, {{1.0}, {-1.0}}, 7},
        SweepQueryNotRun{SweepNotRunReason::family_unavailable}};
}

SweepPhaseResources resources() {
    SweepPhaseResources result{{4, 2, 2, 1024}, 2, 2, {}, 512, 0, 1024, {},
        SweepMemorySupport::active_and_retained_reservations, "executor reservations"};
    return result;
}
} // namespace

TEST_CASE("scenario sweep embeds validated runs and round-trips canonically") {
    const auto spec = content("{\"scenario_ids\":[\"scenario-a\"],\"schema\":\"csl.scenario-sweep-spec/1\"}");
    auto item = one_case();
    item.query = run();
    const auto encoded = encode_recorded_sweep(spec, "sweep-1", {item}, resources(), resources());
    REQUIRE(std::holds_alternative<RecordedSweepArtifact>(encoded));
    const auto& artifact = std::get<RecordedSweepArtifact>(encoded);
    const auto bytes = artifact.content().bytes();
    const std::string text(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    const auto decoded = decode_recorded_sweep(text);
    REQUIRE(std::holds_alternative<RecordedSweepArtifact>(decoded));
    CHECK(std::get<RecordedSweepArtifact>(decoded).identity() == artifact.identity());
    CHECK(std::get<RecordedSweepArtifact>(decoded).content().bytes().size() == bytes.size());
}

TEST_CASE("scenario sweep refuses duplicate identities, invalid selection, and unsupported resource claims") {
    const auto spec = content("{\"schema\":\"csl.scenario-sweep-spec/1\"}");
    auto item = one_case();
    CHECK(std::holds_alternative<ArtifactError>(encode_recorded_sweep(spec, "sweep-1", {item, item}, resources(), resources())));
    item.configuration.value = "config-does-not-match-embedded-run";
    CHECK(std::holds_alternative<ArtifactError>(encode_recorded_sweep(spec, "sweep-1", {item}, resources(), resources())));
    item = one_case();
    item.selection.distinctness_tolerance = -1.0;
    CHECK(std::holds_alternative<ArtifactError>(encode_recorded_sweep(spec, "sweep-1", {item}, resources(), resources())));
    item = one_case();
    auto claimed = resources();
    claimed.memory_support = SweepMemorySupport::process_observation;
    claimed.observed_process_memory_bytes = 2048;
    claimed.memory_observation_scope.clear();
    CHECK(std::holds_alternative<ArtifactError>(encode_recorded_sweep(spec, "sweep-1", {item}, claimed, resources())));
}

TEST_CASE("scenario sweep decoder enforces canonical and structural input") {
    const auto spec = content("{\"schema\":\"csl.scenario-sweep-spec/1\"}");
    const auto encoded = encode_recorded_sweep(spec, "sweep-1", {one_case()}, resources(), resources());
    REQUIRE(std::holds_alternative<RecordedSweepArtifact>(encoded));
    const auto bytes = std::get<RecordedSweepArtifact>(encoded).content().bytes();
    std::string text(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    CHECK(std::holds_alternative<ArtifactError>(decode_recorded_sweep(" " + text)));
    CHECK(std::holds_alternative<ArtifactError>(decode_recorded_sweep(text, {32, 100, 16, 64})));
    const auto duplicate_key = text.find("\"run_id\":");
    REQUIRE(duplicate_key != std::string::npos);
    text.insert(duplicate_key, "\"run_id\":\"forged\",");
    CHECK(std::holds_alternative<ArtifactError>(decode_recorded_sweep(text)));
}
