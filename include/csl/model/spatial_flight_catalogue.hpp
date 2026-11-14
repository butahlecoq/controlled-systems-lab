#pragma once

#include <csl/model/catalogue.hpp>
#include <csl/model/discretization.hpp>
#include <csl/model/spatial_flight.hpp>

namespace csl::model::catalogue {

struct ReferenceIntegrationReceipt {
    std::string method;
    std::size_t intervals, substeps_per_interval, rhs_evaluations;
};

struct SpatialFlightCase {
    DiscreteReachabilityCase reachability;
    spatial_flight::Parameters parameters;
    std::vector<spatial_flight::State> reference;
    spatial_flight::Control nominal_control;
    DiscretizationReceipt discretization;
    ReferenceIntegrationReceipt reference_integration;
};

template <class T> using SpatialFlightResult = std::variant<T, Diagnostics, OperationStopped>;

std::span<const CaseInfo> spatial_flight_cases() noexcept;
SpatialFlightResult<SpatialFlightCase>
make_spatial_flight_case(std::string_view id, const IntegrationOptions &options = {});

} // namespace csl::model::catalogue
