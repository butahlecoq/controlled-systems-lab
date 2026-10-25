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

TEST_CASE("completed finite pair projections can be persisted without recomputing geometry") {
    PlotData data;
    data.problem={"scenario-1"};data.run={"run-1"};data.strategy={"strategy-a"};data.strategy_version="2";
    data.state_axis.points={0,1};data.control_axis.points={0};data.control_axis.interval_ends={1};
    data.states.coordinates={CoordinateAnnotation{std::string("position"),std::string("m")},
        CoordinateAnnotation{std::string("velocity"),std::string("m/s")}};
    data.controls.coordinates={CoordinateAnnotation{std::string("force"),std::string("N")}};
    PlotEvidence evidence{verification::CheckStatus::numerical_pass,verification::CheckStatus::numerical_pass,
        verification::CheckStatus::numerical_pass,verification::CheckStatus::unsupported,
        verification::CheckStatus::unsupported,verification::CheckStatus::unsupported,{}};
    data.paths.push_back(PlotPath{data.run,0,data.strategy,"2",{{0,0},{1,1}},{{.5}},3.0,evidence});

    auto vertex_matrix=numeric::snapshot(Matrix{3,2,{-1,0,0,1,2,0}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertex_matrix));
    auto ray_matrix=numeric::snapshot(Matrix{0,2,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ray_matrix));
    auto set=sets::make_v({SetId{"projected"},2,{"position","velocity"}},
        {std::get<numeric::MatrixView>(vertex_matrix),std::get<numeric::MatrixView>(ray_matrix)});
    REQUIRE(std::holds_alternative<sets::SetData>(set));
    GeometryReference reference{{data.problem,RequestId{"projection-request"},ReferenceId{"ideal-projection"}},
        {SetId{"source-relation"}}};
    registry::Provenance provider{"geometry",registry::Method{ModuleId{"hull"},std::string("1")},
        registry::Identity{ModuleId{"hull"},"1"}};
    PlotSetProjection projection{data.problem,PlotSourceOwner{data.problem,SetId{"source-relation"}},StageIndex{1},
        reference,std::get<sets::SetData>(set).as_handle(),
        {data.states.coordinates[0],data.states.coordinates[1]},SetRelation::equivalent,
        EvidenceSupport{Unestablished{}},{"finite fixture"},provider,{},PlotQueryCost{std::chrono::nanoseconds{17}}};
    PlotOutcome outcome{projection};
    auto encoded=encode_plot_document_json(data,outcome,"csl.run-statistics/6",std::string(64,'b'));
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto& json=std::get<std::string>(encoded);
    CHECK(json.find("Saved 2D set projection at stage 1")!=std::string::npos);
    CHECK(json.find("\"relation\": \"equivalent\"")!=std::string::npos);
    CHECK(json.find("\"points\": [")!=std::string::npos);
    CHECK(json.find("geometry_operation_elapsed_ns")!=std::string::npos);
    CHECK(json.find("not applicable to a set projection")!=std::string::npos);

    PlotSupportSamples samples{data.problem,PlotSourceOwner{data.problem,SetId{"source-relation"}},StageIndex{1},
        {data.states.coordinates[0],data.states.coordinates[1]},PlotSampleKind::support_samples,
        {PlotSupportSample{{1,0},4.0,std::array<double,2>{2,0},reference,EvidenceSupport{Unestablished{}},{"finite fixture"}},
         PlotSupportSample{{-1,0},EmptySupport{},std::nullopt,reference,EvidenceSupport{Unestablished{}},{}}},
        provider,{},PlotQueryCost{std::chrono::nanoseconds{23}}};
    PlotOutcome sample_outcome{samples};
    auto sample_document=encode_plot_document_json(data,sample_outcome,"csl.run-statistics/6",std::string(64,'b'));
    REQUIRE(std::holds_alternative<std::string>(sample_document));
    const auto& sample_json=std::get<std::string>(sample_document);
    CHECK(sample_json.find("\"kind\": \"support_samples\"")!=std::string::npos);
    CHECK(sample_json.find("\"kind\": \"unbounded\"")==std::string::npos);
    CHECK(sample_json.find("\"kind\": \"empty\"")!=std::string::npos);
    CHECK(sample_json.find("\"direction\": [")!=std::string::npos);
}
