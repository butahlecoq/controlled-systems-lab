#pragma once

#include <csl/input/scenario_loader.hpp>
#include <csl/model/discretization.hpp>

namespace csl::input {

struct ContinuousModelInput {
    model::ContinuousAffineModel model;
    model::IntegrationOptions integration;
    problem::ResolvedContent source;
    std::string schema;
};
using ContinuousModelLoadResult =
    std::variant<ContinuousModelInput,InputFailure,UnsupportedInput,OperationStopped>;

ContinuousModelLoadResult load_continuous_model(std::span<const std::byte>,
                                                const LoadOptions& = {});

} // namespace csl::input
