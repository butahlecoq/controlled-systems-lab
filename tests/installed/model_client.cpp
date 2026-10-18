#include <csl/model/linear_system.hpp>
#include <csl/model/hybrid_system.hpp>

#include <iostream>
#include <stdexcept>
#include <utility>

using namespace csl;
using namespace csl::model;
template<class T, class... Errors> T accepted(std::variant<T, Errors...> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("Model operation failed");
    return std::get<T>(std::move(result));
}
int main() {
    try {
        const Vector times{0,1,2};
        const LinearStage maps{{1,1,{3}}, {1,1,{2}}, {1,0,{}}, {-1}};
        for (const auto& provider : {Coefficients{maps}, Coefficients{std::vector{maps,maps}}}) {
            const auto model = accepted(snapshot({{{1,1,0},TimeDomain::discrete,provider},{}},times));
            auto x = accepted(model.step({0},Vector{2},Vector{1},{}));
            if (x != Vector{7} || accepted(model.step({1},x,Vector{-2},{})) != Vector{16})
                throw std::runtime_error("Literal trajectory failed");
        }
        const auto model = [&] {
            const ObservationPoint post{{0},ObservationTiming::after_decision};
            SystemModel producer{{{1,1,1},TimeDomain::discrete,
                LinearStage{{1,1,{3}},{1,1,{2}},{1,1,{4}},{-1}}},
                {{ObservationStage{{1,1,{2}},{1,1,{3}},{1,1,{5}},{1,1,{7}},{11}},
                    {{{0},post,post,StageIndex{0}}}}}};
            auto result = accepted(snapshot(producer,times));
            std::get<ObservationStage>(producer.observations[0].coefficients).state_map.values[0] = 99;
            return result;
        }();
        const auto value = accepted(model.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1}));
        if (value.values != Vector{21} || value.metadata.state_time != 0 || value.metadata.available_time != 1)
            throw std::runtime_error("Literal observation or retained metadata failed");
        const auto invalid = model.stage({2});
        if (!std::holds_alternative<Diagnostic>(invalid) || std::get<Diagnostic>(invalid).code != DiagnosticCode::invalid_input)
            throw std::runtime_error("Stage bound guard failed");
        HybridMode parked;
        parked.id={"parked"};
        const HybridSystem hybrid{0,{parked},{}};
        const auto paths = enumerate_hybrid_paths(hybrid,{"parked"},{{"parked"}},{0,1});
        if (!std::holds_alternative<std::vector<HybridPath>>(paths) ||
            std::get<std::vector<HybridPath>>(paths).size()!=1 ||
            !std::get<std::vector<HybridPath>>(paths).front().edges.empty())
            throw std::runtime_error("Installed hybrid model client failed");
        std::cout << "Installed model client: immutable LTI/LTV and scheduled observation literals passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
