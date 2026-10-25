#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/artifacts/plot_document_json.hpp>
#include <doctest/doctest.h>

using namespace csl;
using namespace csl::artifacts;

TEST_CASE("PlotData encodes selected trajectories into the offline figure document") {
    PlotData data;
    data.problem={"scenario-1"};data.run={"run-1"};data.strategy={"strategy-a"};data.strategy_version="2";
    data.state_axis.points={0,1};data.control_axis.points={0};data.control_axis.interval_ends={1};
    data.states.coordinates={CoordinateAnnotation{std::string("position"),std::string("m")}};
    data.controls.coordinates={CoordinateAnnotation{std::string("force"),std::string("N")}};
    PlotEvidence evidence{verification::CheckStatus::numerical_pass,verification::CheckStatus::numerical_pass,
        verification::CheckStatus::numerical_pass,verification::CheckStatus::unsupported,
        verification::CheckStatus::unsupported,verification::CheckStatus::unsupported,{}};
    data.paths.push_back(PlotPath{data.run,0,data.strategy,"2",{{0},{1}},{{.5}},3.0,evidence});

    auto encoded=encode_plot_document_json(data,"csl.run-statistics/6",std::string(64,'a'));
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto& json=std::get<std::string>(encoded);
    CHECK(json.find("csl.plot-document/1")!=std::string::npos);
    CHECK(json.find("witness-0")!=std::string::npos);
    CHECK(json.find("interval_ends")!=std::string::npos);
    CHECK(json.find("selected witness only; not the full feasible or optimal family")!=std::string::npos);
    CHECK(json.find("3.0")!=std::string::npos);
}

TEST_CASE("PlotData figure encoding rejects an unbound source record") {
    PlotData data;
    auto encoded=encode_plot_document_json(data,"csl.run-statistics/6","not-a-digest");
    REQUIRE(std::holds_alternative<ArtifactError>(encoded));
    CHECK(std::get<ArtifactError>(encoded).path=="source_record_sha256");
}
