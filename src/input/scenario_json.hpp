#pragma once
#include <csl/input/scenario_loader.hpp>
#include <nlohmann/json.hpp>
#include <initializer_list>
#include <string_view>
namespace csl::input::detail {
using Json=nlohmann::json;
struct ScenarioStorage {
    problem::ResolvedProblem problem;
    RequestedRun run;
    std::vector<DefaultRecord> defaults;
    ScenarioMetadata metadata;
    SourceProvenance source;
};
struct HistoricalStorage { HistoricalRecord record; SourceProvenance source; };
struct Access {
    static LoadedScenario scenario(ScenarioStorage s) {return LoadedScenario(std::make_shared<const ScenarioStorage>(std::move(s)));}
    static HistoricalScenario historical(HistoricalStorage s) {return HistoricalScenario(std::make_shared<const HistoricalStorage>(std::move(s)));}
};
void poll(const LoadOptions&);
void validate_options(const LoadOptions&);
Json parse(std::span<const std::byte>,const LoadOptions&);
std::string child(std::string_view,std::string_view);
[[noreturn]] void fail(std::string path,std::string observed,std::string expected,InputCategory = InputCategory::field);
const Json& member(const Json&,std::string_view key,std::string_view path);
void object(const Json&,const std::string& path,std::initializer_list<std::string_view> allowed);
std::string string(const Json&,const std::string& path);
std::size_t count(const Json&,const std::string& path);
double number(const Json&,const std::string& path);
LoadResult load_bytes(std::span<const std::byte>,const LoadOptions&,const std::filesystem::path&);
template<class T,class... R> T canonical(std::variant<T,R...> value,const std::string& path) {
    if(auto* result=std::get_if<T>(&value)) return std::move(*result);
    if constexpr((std::is_same_v<R,OperationStopped> || ...))
        if(auto* stopped=std::get_if<OperationStopped>(&value)) throw *stopped;
    const auto& diagnostic=std::get<Diagnostic>(value);
    throw InputFailure{InputCategory::field,path,diagnostic.explanation,"valid canonical data",{},diagnostic};
}
} // namespace csl::input::detail
