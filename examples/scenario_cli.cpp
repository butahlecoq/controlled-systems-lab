#include <csl/input/scenario_loader.hpp>
#include <iostream>
#include <string_view>

namespace {
const char* category_name(csl::input::InputCategory category) {
    using csl::input::InputCategory;
    switch (category) {
    case InputCategory::syntax: return "syntax";
    case InputCategory::encoding: return "encoding";
    case InputCategory::schema: return "schema";
    case InputCategory::field: return "field";
    case InputCategory::io: return "io";
    case InputCategory::limit: return "limit";
    }
    return "unknown";
}
}

int main(int argc, char** argv) {
    if (argc != 3 || std::string_view(argv[1]) != "--validate-only") {
        std::cerr << "Usage: scenario_cli --validate-only <scenario.json>\n";
        return 2;
    }

    const auto loaded = csl::input::load_scenario_file(argv[2]);
    if (const auto* error = std::get_if<csl::input::InputFailure>(&loaded)) {
        std::cerr << "Input rejected: category=" << category_name(error->category)
                  << " path=" << error->path << " observed=" << error->observed
                  << "; expected " << error->expected << '\n';
        return 2;
    }
    if (const auto* unsupported = std::get_if<csl::input::UnsupportedInput>(&loaded)) {
        std::cerr << "Input unsupported: path=" << unsupported->path
                  << " feature=" << unsupported->feature << "; expected "
                  << unsupported->expected << '\n';
        return 2;
    }
    if (const auto* stopped = std::get_if<csl::OperationStopped>(&loaded)) {
        std::cerr << "Input stopped: " << stopped->diagnostics << '\n';
        return 2;
    }
    if (const auto* historical = std::get_if<csl::input::HistoricalScenario>(&loaded)) {
        const auto record = historical->record();
        std::cerr << "Input unsupported: historical scenario " << record->id
                  << " is non-executable; " << record->execution_gate << '\n';
        return 2;
    }

    const auto& scenario = std::get<csl::input::LoadedScenario>(loaded);
    const auto problem = scenario.problem();
    const auto source = scenario.source();
    const auto requested = scenario.requested_run();
    const auto dimensions = problem.model().dimensions();

    std::cout << "validation=valid schema=" << source->schema
              << " problem=" << problem.identity().value
              << " source_sha256=" << csl::problem::hex(source->content.digest())
              << " horizon=" << problem.model().horizon()
              << " state_dimension=" << dimensions.state
              << " control_dimension=" << dimensions.control
              << " requested=";
    if (std::holds_alternative<csl::input::ComparisonRequest>(requested->selection)) {
        std::cout << "comparison";
    } else {
        std::cout << "explicit_methods count="
                  << std::get<std::vector<csl::input::ModuleRequest>>(requested->selection).size();
    }
    std::cout << " mode=validate_only solvers=not_invoked\n";
    return 0;
}