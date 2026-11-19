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

// Variables at each stage are (next position, next velocity, applied acceleration).
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
        cost.dim_ = 3 * stages;
        cost.format_ = HessianFormat::kTriangular;
        // HiGHS stores 0.5 * x' H x. Its default Hessian starts with one zero.
        cost.start_.clear();
        for (int k = 0; k < stages; ++k) {
            require(solver_.addVar(-3, 3));
            require(solver_.addVar(-2, 2));
            require(solver_.addVar(-1, 1));
            for (int coordinate = 0; coordinate < 3; ++coordinate) {
                cost.start_.push_back(static_cast<HighsInt>(cost.value_.size()));
                if (coordinate == 2 || k + 1 == stages) {
                    cost.index_.push_back(3 * k + coordinate);
                    cost.value_.push_back(coordinate == 2 ? 0.5 : 2.0);
                }
            }
        }
        cost.start_.push_back(static_cast<HighsInt>(cost.value_.size()));
        require(solver_.passHessian(std::move(cost)));

        add_row(0, 0, {0}, {1});
        add_row(0, 0, {1, 2}, {1, -1});
        for (int k = 1; k < stages; ++k) {
            const int i = 3 * k;
            add_row(0, 0, {i, i - 3, i - 2}, {1, -1, -1});
            add_row(0, 0, {i + 1, i - 2, i + 2}, {1, -1, -1});
        }
        const int endpoint = 3 * (stages - 1);
        add_row(-1, 1, {endpoint, endpoint + 1}, {1, 1});
        add_row(-1, 1, {endpoint, endpoint + 1}, {1, 2});
    }

    std::optional<std::vector<double>> decide(State x,
                                              const std::vector<double> &warm_controls = {}) {
        if (!std::isfinite(x[0]) || !std::isfinite(x[1]))
            throw std::invalid_argument("state must be finite");
        if (std::abs(x[0]) > 3 || std::abs(x[1]) > 2)
            return std::nullopt;
        require(solver_.changeRowBounds(0, x[0] + x[1], x[0] + x[1]));
        require(solver_.changeRowBounds(1, x[1], x[1]));
        if (!warm_controls.empty()) {
            if (warm_controls.size() != static_cast<std::size_t>(stages_))
                throw std::invalid_argument("warm start dimension");
            HighsSolution start;
            for (double u : warm_controls) {
                x = {x[0] + x[1], x[1] + u};
                start.col_value.insert(start.col_value.end(), {x[0], x[1], u});
            }
            start.value_valid = true;
            require(solver_.setSolution(start));
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
        std::vector<double> controls;
        for (int i = 0; i < stages_; ++i)
            controls.push_back(solver_.getSolution().col_value[3 * i + 2]);
        return controls;
    }

    int cold_retries() const { return cold_retries_; }

    HighsInt scheduler_threads() const { return solver_.getNumSchedulerThreads(); }

  private:
    static void require(HighsStatus status, std::source_location where = std::source_location::current()) {
        if (status != HighsStatus::kOk)
            throw std::runtime_error("HiGHS status " + std::to_string(static_cast<int>(status)) + " at line " + std::to_string(where.line()));
    }
    void add_row(double lo, double hi, const std::vector<HighsInt> &indices,
                 const std::vector<double> &coefficients) {
        require(solver_.addRow(lo, hi, static_cast<HighsInt>(indices.size()), indices.data(),
                               coefficients.data()));
    }

    int stages_;
    Highs solver_;
    int cold_retries_{};
};

} // namespace mpc_crossover
