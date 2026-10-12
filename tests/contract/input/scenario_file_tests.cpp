#define DOCTEST_CONFIG_IMPLEMENT
#include <doctest/doctest.h>
#include <csl/input/scenario_loader.hpp>
#include <fstream>
#include <iterator>
using namespace csl;
using namespace csl::input;
namespace {
std::filesystem::path source,output;
template<class T> T accepted(LoadResult value) {REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));}
std::string read(const std::filesystem::path& path) {std::ifstream stream(path,std::ios::binary);REQUIRE(stream.good());return {std::istreambuf_iterator<char>(stream),{}};}
std::filesystem::path write(const char* name,std::string_view data) {const auto path=output/name;std::ofstream stream(path,std::ios::binary);stream.write(data.data(),static_cast<std::streamsize>(data.size()));REQUIRE(stream.good());return path;}
LoadResult bytes(std::string_view text) {return load_scenario(std::as_bytes(std::span(text.data(),text.size())));}
}
TEST_CASE("actual fixture files translate to the same owned mathematics as their bytes") {
    auto path=source/"tests/fixtures/input/minimal-integrator.json";auto text=read(path);
    auto file=accepted<LoadedScenario>(load_scenario_file(path));auto memory=accepted<LoadedScenario>(bytes(text));
    CHECK(file.problem().identity()==memory.problem().identity());CHECK(file.source()->location==path);CHECK(memory.source()->location.empty());
    CHECK(file.source()->content.digest()==memory.source()->content.digest());
    CHECK(file.problem().model().horizon()==2);
    auto affine=accepted<LoadedScenario>(load_scenario_file(source/"tests/fixtures/input/affine-ltv.json"));
    CHECK(std::get<Vector>(affine.problem().model().step({0},Vector{2},Vector{1},{}))==Vector{7});
    CHECK(std::get<Vector>(affine.problem().model().step({1},Vector{7},Vector{-2},{}))==Vector{16});
    const auto ownedpath=write("owned.json",text);auto retained=accepted<LoadedScenario>(load_scenario_file(ownedpath)).source();
    write("owned.json","{}");CHECK(retained->content.digest()==memory.source()->content.digest());
    CHECK(accepted<LoadedScenario>(load_scenario(retained->content.bytes())).problem().identity()==memory.problem().identity());
}
TEST_CASE("all four continuous forms reject at both actual byte and file loader boundaries") {
    for(const auto kind:{"linear_continuous","linear_continuous_ltv","affine_continuous","affine_continuous_ltv"}) {
        const auto text=std::string(R"({"schema":"csl.scenario/1","horizon":1,"model":{"kind":")")+kind+R"("},"initial_state":[0],"controls":{"kind":"universal"},"objective":{"kind":"linear","coefficients":[1]}})";
        auto a=accepted<UnsupportedInput>(bytes(text));auto b=accepted<UnsupportedInput>(load_scenario_file(write("continuous.json",text)));
        CHECK(a.path=="/model/kind");CHECK(b.path=="/model/kind");CHECK(a.feature==kind);CHECK(b.feature==kind);
        CHECK(a.expected=="a discrete transition model; continuous-time input is not supported in v1");CHECK(b.expected==a.expected);
    }
    constexpr auto typo=R"({"schema":"csl.scenario/1","horizon":1,"model":{"kind":"linear_continous"},"initial_state":[0],"controls":{"kind":"universal"},"objective":{"kind":"linear","coefficients":[1]}})";
    CHECK(accepted<InputFailure>(bytes(typo)).path=="/model/kind");CHECK(accepted<InputFailure>(load_scenario_file(write("typo.json",typo))).path=="/model/kind");
}
TEST_CASE("bounded local reads distinguish absence malformed data and cancellation before IO") {
    CHECK(accepted<InputFailure>(load_scenario_file(output/"not-created.json")).observed=="not_found");
    CHECK(accepted<InputFailure>(load_scenario_file(write("malformed.json","{"))).category==InputCategory::syntax);
    const auto text=read(source/"tests/fixtures/input/minimal-integrator.json");LoadOptions options;options.limits.input_bytes=text.size();
    CHECK(std::holds_alternative<LoadedScenario>(load_scenario_file(write("exact.json",text),options)));
    CHECK(accepted<InputFailure>(load_scenario_file(write("oversize.json",text+" "),options)).category==InputCategory::limit);
    std::stop_source stop;stop.request_stop();options.cancellation=stop.get_token();
    CHECK(accepted<OperationStopped>(load_scenario_file(output/"not-created.json",options)).reason==StopReason::cancelled);
}
TEST_CASE("actual B04 archive remains owning historical data with all unresolved inputs") {
    const auto path=source/"benchmarks/scenarios/b04-historical.json";const auto text=read(path);
    auto value=accepted<HistoricalScenario>(load_scenario_file(path));CHECK(value.record()->unresolved.size()==4);
    CHECK(value.record()->restoration_status=="incomplete_and_inconsistent");CHECK(value.source()->content.bytes().size()==text.size());
    CHECK(value.record()->execution_gate.find("Do not solve")!=std::string::npos);
    CHECK(value.source()->content.digest()==accepted<HistoricalScenario>(bytes(text)).source()->content.digest());
}
int main(int argc,char** argv) {
    if(argc!=3) return 2;
    source=argv[1];output=argv[2];std::filesystem::create_directories(output);
    return doctest::Context{}.run();
}
