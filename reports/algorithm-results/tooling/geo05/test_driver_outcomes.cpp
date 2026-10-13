// Exercise the actual driver's variant boundary, without invoking measurement.
#define main geo05_report_main
#include "projection_predecessor_driver.cpp"
#undef main
#include <sstream>
#include <nlohmann/json.hpp>

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
    nested.predecessor = {{{"nested-problem"}, {"predecessor-request"}, {"predecessor-ideal"}}, {{"X"}, {"U"}, {"S"}}};
    nested.projection = {{{"nested-problem"}, {"projection-request"}, {"projection-ideal"}}, {{"joint-set"}}};
    nested.projection_provider = {{"projection-request"}, "geometry", {"requested-projection"}, "requested-v1",
        ModuleId{"actual-projection"}, "actual-v2"};
    nested.completed_lineage = {
        {nested.predecessor, GeometryClaimScope::set_relation, Unestablished{}, {"unestablished assumption"}, {}},
        {nested.projection, GeometryClaimScope::support_value, NumericalCheck{0.125, 0.25, 0.5, {"numeric-verifier"}},
            {"numerical assumption"}, GeometryErrorBound{{"distance-metric"}, 0.75, "meters"}},
        {nested.predecessor, GeometryClaimScope::containment, SymbolicArgument{"symbolic-reference", "symbolic conditions"},
            {"symbolic assumption"}, {}},
        {nested.projection, GeometryClaimScope::set_relation, CertificateReference{"certificate-artifact", "certificate-verifier"},
            {"certificate assumption"}, {}}
    };
    nested.cause = OperationStopped{StopReason::cancelled, "child projection cancelled"};
    const auto populated_trial = execute_attempt("singular_a", 0, "measurement", [&](Trial&) {
        take(reachability::NominalPredecessorOutcome{nested});
    });
    std::ostringstream nested_output;
    auto* original_output = std::cout.rdbuf(nested_output.rdbuf());
    emit(populated_trial);
    std::cout.rdbuf(original_output);
    const auto emitted = nlohmann::json::parse(nested_output.str());
    const auto expected_failure = nlohmann::json::parse(R"json({
      "predecessor": {"identity": {"problem":"nested-problem","request":"predecessor-request","ideal_output":"predecessor-ideal"}, "inputs":["X","U","S"]},
      "projection": {"identity": {"problem":"nested-problem","request":"projection-request","ideal_output":"projection-ideal"}, "inputs":["joint-set"]},
      "projection_provider": {"request":"projection-request","port":"geometry","requested_module":"requested-projection","requested_version":"requested-v1","actual_module":"actual-projection","actual_version":"actual-v2"},
      "completed_lineage": [
        {"reference":{"identity":{"problem":"nested-problem","request":"predecessor-request","ideal_output":"predecessor-ideal"},"inputs":["X","U","S"]},"scope":"set_relation","support":{"kind":"unestablished"},"assumptions":["unestablished assumption"],"error_bound":null},
        {"reference":{"identity":{"problem":"nested-problem","request":"projection-request","ideal_output":"projection-ideal"},"inputs":["joint-set"]},"scope":"support_value","support":{"kind":"numerical_check","absolute_tolerance":0.125,"relative_tolerance":0.25,"max_residual":0.5,"verifier":"numeric-verifier"},"assumptions":["numerical assumption"],"error_bound":{"metric":"distance-metric","bound":0.75,"units":"meters"}},
        {"reference":{"identity":{"problem":"nested-problem","request":"predecessor-request","ideal_output":"predecessor-ideal"},"inputs":["X","U","S"]},"scope":"containment","support":{"kind":"symbolic_argument","reference":"symbolic-reference","assumptions":"symbolic conditions"},"assumptions":["symbolic assumption"],"error_bound":null},
        {"reference":{"identity":{"problem":"nested-problem","request":"projection-request","ideal_output":"projection-ideal"},"inputs":["joint-set"]},"scope":"set_relation","support":{"kind":"certificate_reference","artifact":"certificate-artifact","verifier":"certificate-verifier"},"assumptions":["certificate assumption"],"error_bound":null}
      ],
      "cause":{"kind":"operation_stopped","reason":"cancelled","diagnostics":"child projection cancelled"}
    })json");
    if (!emitted.contains("predecessor_failure") || emitted["predecessor_failure"] != expected_failure) {
        std::cerr << "emitted nested failure lost available references, provider provenance, lineage, or cause\n";
        ++failures;
    }
    nested.cause = Unsupported{{{DiagnosticCode::unsupported, "projection.rows", "configured limit"}}};
    nested.projection_provider.requested_version.reset();
    nested.projection_provider.actual_module.reset();
    nested.projection_provider.actual_version.reset();
    const auto unsupported_trial = execute_attempt("singular_a", 0, "measurement", [&](Trial&) {
        take(reachability::NominalPredecessorOutcome{nested});
    });
    nested_output.str("");
    original_output = std::cout.rdbuf(nested_output.rdbuf());
    emit(unsupported_trial);
    std::cout.rdbuf(original_output);
    auto expected_unsupported = expected_failure;
    expected_unsupported["cause"] = nlohmann::json::parse(R"json({"kind":"unsupported","diagnostics":[
        {"code":"unsupported","field":"projection.rows","explanation":"configured limit"}]})json");
    expected_unsupported["projection_provider"]["requested_version"] = nullptr;
    expected_unsupported["projection_provider"]["actual_module"] = nullptr;
    expected_unsupported["projection_provider"]["actual_version"] = nullptr;
    const auto emitted_unsupported = nlohmann::json::parse(nested_output.str());
    if (!emitted_unsupported.contains("predecessor_failure") || emitted_unsupported["predecessor_failure"] != expected_unsupported) {
        std::cerr << "emitted nested unsupported failure lost diagnostics or nullable provider provenance\n";
        ++failures;
    }
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
