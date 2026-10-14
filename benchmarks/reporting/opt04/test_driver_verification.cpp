#define main opt04_report_main
#include "phase_one_driver.cpp"
#undef main

int main() {
    const auto& fixture = fixtures.front();
    auto result = run_side(fixture, "phase-one-bland", [] {
        throw std::runtime_error("injected post-run verification failure");
    });
    const auto& detail = result.detail;
    if (result.passed || detail["status"] != "failed" ||
        detail["error"] != "injected post-run verification failure" ||
        detail["observed_status"] != "optimal" || detail["termination"] != "completed" ||
        detail["result"]["outcome"] != "optimal" || detail["primal"] != json(fixture.expected) ||
        detail["original_rows_max_violation"].is_null() ||
        detail["auxiliary_residual"].is_null() || detail["auxiliary_value"].is_null() ||
        detail["result"]["pivots"].is_null() || detail["result"]["factorizations"].is_null() ||
        detail["work_observed"] != true) {
        std::cerr << "post-run verification failure discarded returned result evidence: " << detail.dump() << '\n';
        return 1;
    }
    auto interrupted = run_side(fixture, "phase-one-bland", {}, [] {
        throw std::runtime_error("injected failure before diagnostics");
    });
    const auto& partial = interrupted.detail;
    if (interrupted.passed || partial["error"] != "injected failure before diagnostics" ||
        partial["observed_status"] != "optimal" || partial["termination"] != "completed" ||
        partial["primal"] != json(fixture.expected) ||
        !partial["original_rows_max_violation"].is_null() ||
        !partial["auxiliary_residual"].is_null() || !partial["auxiliary_value"].is_null() ||
        !partial["result"]["pivots"].is_null() || !partial["result"]["factorizations"].is_null()) {
        std::cerr << "unavailable post-run diagnostics were not retained as unavailable: " << partial.dump() << '\n';
        return 1;
    }
    return 0;
}
