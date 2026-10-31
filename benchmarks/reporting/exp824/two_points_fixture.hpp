#pragma once

#include <csl/optimization/finite_action_minimax.hpp>

#include <stdexcept>

namespace csl::issue824::fixture {

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

inline sets::SetData vertices(std::string id, std::size_t dimension, Matrix points) {
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(points))),
         take(numeric::snapshot(Matrix{0,dimension,{}}))}));
}

inline optimization::FiniteActionMinimaxRequest two_points_request(std::string request_id) {
    constexpr std::size_t horizon = 3;
    const SystemModel source_model{{{4,1,1}, TimeDomain::discrete,
        LinearStage{{4,4,{1.0,0.01,0.0,0.0, 0.0,0.0,0.0,0.0,
                          0.0,0.0,1.0,0.1, 0.0,0.0,0.0,1.0}},
                    {4,1,{0.09,1.0,0.0,0.0}}, {4,1,{0.0,0.0,0.0045,0.1}},
                    {0.0,0.0,0.0,0.0}}}, {}};
    const auto system = take(model::snapshot(source_model, Vector{0.0,0.1,0.2,0.3}));
    std::vector<sets::SetData> disturbances(horizon,
        vertices("disturbances", 1, Matrix{3,1,{-1.0,0.0,1.0}}));
    std::vector<sets::SetData> safe;
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal({{"unconstrained-" + std::to_string(stage)},4,{}})));
    const auto objective = std::get<optimization::Objective>(optimization::snapshot(QuadraticTerminal{
        {4,4,{2.0,0.0,-2.0,0.0, 0.0,0.0,0.0,0.0,
              -2.0,0.0,2.0,0.0, 0.0,0.0,0.0,0.0}}, {0.0,0.0,0.0,0.0}, 0.0}));
    return {{"env717-two-points-short-horizon-v1"}, {std::move(request_id)}, system,
        vertices("initial", 4, Matrix{1,4,{4.5,0.0,0.0,0.0}}),
        {1,{{-2.5},{0.0},{2.5}}}, std::move(disturbances), std::move(safe), objective};
}

} // namespace csl::issue824::fixture
