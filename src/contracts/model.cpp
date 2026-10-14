#include <csl/model/contracts.hpp>
#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <utility>

namespace csl {
namespace {
using contracts_detail::Overloaded;
using contracts_detail::matrix_matches;
}
Diagnostics check_model_shape(const Dynamics& dynamics, std::size_t horizon) {
    Diagnostics result;
    auto check = [&](const LinearStage& stage) {
        const auto [n,m,p] = dynamics.dimensions;
        if (!matrix_matches(stage.A,n,n) || !matrix_matches(stage.B,n,m) ||
            !matrix_matches(stage.E,n,p) || stage.offset.size() != n)
            result.push_back({DiagnosticCode::invalid_input,"dynamics.stages","Coefficient shapes or storage do not match dimensions"});
    };
    if (auto constant = std::get_if<LinearStage>(&dynamics.stages)) check(*constant);
    else {
        const auto& stages = std::get<std::vector<LinearStage>>(dynamics.stages);
        if (stages.size() != horizon)
            result.push_back({DiagnosticCode::invalid_input,"dynamics.stages","Expected T stage coefficients"});
        for (const auto& stage : stages) check(stage);
    }
    return result;
}
} // namespace csl
