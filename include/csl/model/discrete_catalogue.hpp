#pragma once

#include <csl/model/catalogue_metadata.hpp>
#include <csl/model/contracts.hpp>

#include <optional>
#include <span>
#include <string_view>
#include <variant>
#include <vector>

namespace csl::model::catalogue {

struct DiscreteModelInfo {
    std::string_view id, title;
    Source source;
};

struct ModelTimeStep {
    double value;
    std::string_view unit;
};

// Supplied discrete model data, without a horizon, objective, admissible sets
// or observation contract. E preserves the source's G channel. Coordinate names
// are indexed; the source qualification retains the authored physical ordering.
struct DiscreteModelData {
    DiscreteModelInfo info;
    LinearStage coefficients;
    Vector initial_state;
    std::optional<Vector> nominal_external;
    ModelTimeStep time_step;
    std::vector<Coordinate> states, controls, external;

    SystemModel system_model() const;
};

std::span<const DiscreteModelInfo> discrete_models();
std::variant<DiscreteModelData, Diagnostics> make_discrete_model(std::string_view id);

} // namespace csl::model::catalogue
