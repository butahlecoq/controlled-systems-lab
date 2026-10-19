#pragma once

#include <csl/core/outcomes.hpp>
#include <csl/model/contracts.hpp>

#include <stop_token>
#include <variant>

namespace csl::model {

enum class HoldConvention { zero_order_hold };
enum class CoefficientVariation { constant_lti, piecewise_linear_ltv };
struct CoefficientEndpoints { LinearStage start, end; };
using ContinuousCoefficients = std::variant<LinearStage,std::vector<CoefficientEndpoints>>;

// Coefficients are rates per physical time. Indexed endpoints interpolate
// linearly within each interval; neighboring intervals may be discontinuous.
struct ContinuousAffineModel {
    Dimensions dimensions;
    Vector times;
    HoldConvention hold;
    ContinuousCoefficients coefficients;
};
struct IntegrationOptions {
    double absolute_tolerance{1e-10}, relative_tolerance{1e-10};
    std::size_t max_attempts_per_stage{100000};
    std::stop_token cancellation{};
};
struct StageIntegrationReceipt {
    double start_time, end_time;
    std::size_t accepted_steps, rejected_steps;
    double max_local_error_estimate;
};
struct DiscretizationReceipt {
    TimeDomain source_domain, output_domain;
    HoldConvention hold;
    CoefficientVariation variation;
    std::string method, error_scope;
    double absolute_tolerance, relative_tolerance;
    std::vector<StageIntegrationReceipt> stages;
};
struct DiscretizedModel {
    SystemModel model;
    Vector times;
    DiscretizationReceipt receipt;
};
using DiscretizationResult = std::variant<DiscretizedModel,Diagnostic,OperationStopped>;

DiscretizationResult discretize(const ContinuousAffineModel&,
                                const IntegrationOptions& = {});

} // namespace csl::model
