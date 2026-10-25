#include <csl/artifacts/plot_request.hpp>

int main() {
    const auto request = csl::artifacts::PlotRequest::trajectory_pair({1, 3});
    return std::holds_alternative<csl::artifacts::TrajectoryPairRequest>(request.source) ? 0 : 1;
}
