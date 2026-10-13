// Exercise the actual driver's variant boundary, without invoking measurement.
#define main geo05_report_main
#include "projection_predecessor_driver.cpp"
#undef main
#include <sstream>

int main() {
    int failures = 0;
    const auto check = [&](auto outcome, const std::string& status, const std::string& detail) {
        try {
            take(std::move(outcome));
            std::cerr << "expected non-success outcome\n";
            ++failures;
        } catch (const TrialFailure& error) {
            const std::string observed = error.what();
            if (error.status != status || observed.find(status + ":") != 0 || observed.find(detail) == std::string::npos) {
                std::cerr << "expected " << status << " with " << detail << "; got " << observed << '\n';
                ++failures;
            }
            const auto trial = execute_attempt("singular_a", 0, "measurement", [&](Trial&) { throw error; });
            if (trial.status != status || trial.end_to_end_scope != "through_failure_unwind") {
                std::cerr << "attempt flattened typed status or lost unwind scope\n";
                ++failures;
            }
            std::ostringstream output;
            auto* original = std::cout.rdbuf(output.rdbuf());
            emit(trial);
            std::cout.rdbuf(original);
            if (output.str().find("\"status\":\"" + status + "\"") == std::string::npos ||
                output.str().find(json_escape(detail)) == std::string::npos) {
                std::cerr << "emitted raw row lost classification or detail\n";
                ++failures;
            }
        } catch (const std::exception& error) {
            std::cerr << "untyped failure: " << error.what() << '\n';
            ++failures;
        }
    };
    check(SetTransformOutcome{Unsupported{{{DiagnosticCode::unsupported,
        "projection.rows", "configured row limit exceeded"}}}}, "unsupported",
        "unsupported: projection.rows: configured row limit exceeded");
    check(SetTransformOutcome{OperationStopped{StopReason::cancelled, "cancel token requested"}},
        "cancelled", "cancel token requested");
    check(SetTransformOutcome{OperationStopped{StopReason::deadline_expired, "deadline reached"}},
        "cancelled", "deadline_expired: deadline reached");
    check(SetTransformOutcome{OperationStopped{StopReason::resource_limit, "workspace limit"}},
        "failed", "resource_limit: workspace limit");
    check(SetTransformOutcome{OperationStopped{StopReason::numerical_failure, "invalid residual"}},
        "failed", "numerical_failure: invalid residual");
    reachability::NominalPredecessorFailure nested;
    nested.cause = OperationStopped{StopReason::cancelled, "child projection cancelled"};
    check(reachability::NominalPredecessorOutcome{nested}, "cancelled", "child projection cancelled");
    nested.cause = Unsupported{{{DiagnosticCode::unsupported, "projection.representation", "unsupported source"}}};
    check(reachability::NominalPredecessorOutcome{nested}, "unsupported",
        "unsupported: projection.representation: unsupported source");
    check(std::variant<int, Diagnostics>{Diagnostics{{DiagnosticCode::invalid_input, "A", "wrong dimensions"}}},
        "failed", "invalid_input: A: wrong dimensions");
    check(std::variant<int, registry::Rejection>{registry::Rejection{{},
        {{DiagnosticCode::unsupported, "provider", "representation unavailable"}}}},
        "unsupported", "unsupported: provider: representation unavailable");
    for (const auto& scenario : {"integrator_predecessor", "unknown"}) {
        const auto trial = execute(scenario, 0, "smoke");
        std::ostringstream output;
        auto* original = std::cout.rdbuf(output.rdbuf());
        emit(trial);
        std::cout.rdbuf(original);
        const auto expected_scope = std::string{scenario} == "unknown"
            ? "through_failure_unwind" : "through_verification_and_fixture_teardown";
        if (output.str().find(expected_scope) == std::string::npos) {
            std::cerr << "missing end-to-end scope " << expected_scope << '\n';
            ++failures;
        }
    }
    return failures ? 1 : 0;
}
