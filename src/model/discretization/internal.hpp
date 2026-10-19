#pragma once

#include <csl/model/discretization.hpp>

namespace csl::model::detail {

struct IntegratedStage { LinearStage coefficients; StageIntegrationReceipt receipt; };
using IntegrationResult = std::variant<IntegratedStage,OperationStopped>;
IntegrationResult integrate_stage(const LinearStage& start,const LinearStage& end,
                                  Dimensions dimensions,double t0,double t1,
                                  const IntegrationOptions& options);

} // namespace csl::model::detail
