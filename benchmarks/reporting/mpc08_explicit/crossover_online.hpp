#pragma once

#include <Highs.h>

#include <array>
#include <cmath>
#include <optional>
#include <source_location>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace mpc_crossover {

using State = std::array<double, 2>;

// Eliminate the linear dynamics. The decision vector contains the remaining accelerations.
// A distinct model per remaining horizon keeps its factorization eligible for reuse.
class OnlineController {
  public:
    explicit OnlineController(int stages) : stages_(stages) {
        if (stages < 1 || stages > 3)
            throw std::invalid_argument("horizon must be 1, 2 or 3");
        require(solver_.setOptionValue("output_flag", false));
        require(solver_.setOptionValue("threads", 1));
        require(solver_.setOptionValue("primal_feasibility_tolerance", 1e-9));
        require(solver_.setOptionValue("dual_feasibility_tolerance", 1e-9));
        HighsHessian cost;
        cost.dim_ = stages;
        cost.format_ = HessianFormat::kTriangular;
        cost.start_.clear();
        for (int j = 0; j < stages; ++j) {
            require(solver_.addVar(-1, 1));
            cost.start_.push_back(static_cast<HighsInt>(cost.value_.size()));
            for (int i = j; i < stages; ++i) {
                cost.index_.push_back(i);
                cost.value_.push_back(2.0 * ((stages - 1 - i) * (stages - 1 - j) + 1) +
                                      (i == j ? 0.5 : 0));
            }
        }
        cost.start_.push_back(static_cast<HighsInt>(cost.value_.size()));
        require(solver_.passHessian(std::move(cost)));
        for (int k = 1; k <= stages; ++k) {
            // p1 is fixed even before choosing u. Check it directly in decide().
            if (k > 1)
                bound_state(k, 1, 0, 3);
            bound_state(k, 0, 1, 2);
        }
        bound_state(stages, 1, 1, 1);
        bound_state(stages, 1, 2, 1);
    }

    std::optional<std::vector<double>> decide(State x,
                                              const std::vector<double> &warm_controls = {}) {
        if (!std::isfinite(x[0]) || !std::isfinite(x[1]))
            throw std::invalid_argument("state must be finite");
        if (std::abs(x[0]) > 3 || std::abs(x[1]) > 2)
            return std::nullopt;
        if (std::abs(x[0] + x[1]) > 3 + 1e-10)
            return std::nullopt;
        for (int j = 0; j < stages_; ++j) {
            const double gradient = 2 * ((stages_ - 1 - j) * (x[0] + stages_ * x[1]) + x[1]);
            require(solver_.changeColCost(j, gradient));
        }
        for (std::size_t i = 0; i < rows_.size(); ++i) {
            const auto &row = rows_[i];
            const double offset = row.p * x[0] + row.v * x[1];
            require(solver_.changeRowBounds(static_cast<HighsInt>(i), -row.limit - offset,
                                            row.limit - offset));
        }
        if (!warm_controls.empty()) {
            if (warm_controls.size() != static_cast<std::size_t>(stages_))
                throw std::invalid_argument("warm start dimension");
            HighsSolution start;
            start.col_value = warm_controls;
            start.value_valid = true;
            require(solver_.setSolution(start));
            // The QP initializer accepts a feasible point only alongside a basis.
            // Basic slack rows supply an identity basis. Nonbasic columns remain
            // inactive directions, so an interior acceleration is permitted.
            HighsBasis basis;
            basis.alien = false;
            basis.row_status.assign(rows_.size(), HighsBasisStatus::kBasic);
            basis.col_status.assign(stages_, HighsBasisStatus::kNonbasic);
            require(solver_.setBasis(basis, "shifted control history"));
            if (!solver_.getBasis().valid || !solver_.getSolution().value_valid)
                throw std::runtime_error("warm primal or logical basis rejected");
            ++supplied_warm_starts_;
        }
        auto run_status = solver_.run();
        if (run_status == HighsStatus::kError) {
            // A carried basis can fail the solver's own primal check at a new state.
            // Charge a cold retry to the same decision and retain its occurrence.
            ++cold_retries_;
            require(solver_.clearSolver());
            run_status = solver_.run();
        }
        require(run_status);
        const auto status = solver_.getModelStatus();
        if (status == HighsModelStatus::kInfeasible)
            return std::nullopt;
        if (status != HighsModelStatus::kOptimal)
            throw std::runtime_error(solver_.modelStatusToString(status));
        return solver_.getSolution().col_value;
    }

    int supplied_warm_starts() const { return supplied_warm_starts_; }
    int cold_retries() const { return cold_retries_; }

    HighsInt scheduler_threads() const { return solver_.getNumSchedulerThreads(); }

  private:
    static void require(HighsStatus status,
                        std::source_location where = std::source_location::current()) {
        if (status != HighsStatus::kOk)
            throw std::runtime_error("HiGHS status " + std::to_string(static_cast<int>(status)) +
                                     " at line " + std::to_string(where.line()));
    }
    struct StateBound {
        int p, v, limit;
    };
    std::vector<StateBound> rows_;
    void bound_state(int stage, int a, int b, int limit) {
        std::vector<HighsInt> ids;
        std::vector<double> values;
        for (int j = 0; j < stage; ++j) {
            const int coefficient = a * (stage - 1 - j) + b;
            if (coefficient) {
                ids.push_back(j);
                values.push_back(coefficient);
            }
        }
        require(solver_.addRow(-limit, limit, static_cast<HighsInt>(ids.size()), ids.data(),
                               values.data()));
        rows_.push_back({a, stage * a + b, limit});
    }

    int stages_;
    Highs solver_;
    int cold_retries_{};
    int supplied_warm_starts_{};
};

} // namespace mpc_crossover
