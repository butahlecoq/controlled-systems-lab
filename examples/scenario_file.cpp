#include <csl/input/scenario_loader.hpp>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) try {
    using namespace csl;
    if (argc != 2) {
        std::cerr << "Usage: scenario_file <two-stage-integrator.json>\n";
        return 2;
    }
    const auto loaded = input::load_scenario_file(argv[1]);
    if (const auto* error = std::get_if<input::InputFailure>(&loaded)) {
        std::cerr << "Input rejected: " << error->path << " observed " << error->observed
                  << "; expected " << error->expected << '\n';
        return 2;
    }
    if (const auto* unsupported = std::get_if<input::UnsupportedInput>(&loaded)) {
        std::cerr << "Input unsupported: " << unsupported->path << " feature " << unsupported->feature
                  << "; expected " << unsupported->expected << '\n';
        return 2;
    }
    if (std::holds_alternative<input::HistoricalScenario>(loaded)) {
        std::cerr << "Historical scenario is not executable; unresolved restoration gates remain.\n";
        return 2;
    }
    if (const auto* stopped = std::get_if<OperationStopped>(&loaded)) {
        std::cerr << "Input stopped: " << stopped->diagnostics << '\n';
        return 2;
    }
    const auto& scenario = std::get<input::LoadedScenario>(loaded);
    const auto resolved = scenario.problem();
    const auto dimensions = resolved.model().dimensions();
    if (dimensions.state != 1 || dimensions.control != 1 || dimensions.external != 0 ||
        resolved.model().horizon() != 2)
        throw std::runtime_error("This example evaluates only the scalar two-stage teaching history; use the supplied template");
    const auto* initial = std::get_if<KnownInitial>(&resolved.description()->initial);
    if (!initial || initial->point != Vector{0})
        throw std::runtime_error("The teaching history requires known x0=0");
    const Vector u0{0.25}, u1{0.75};
    const auto x1 = std::get<Vector>(resolved.model().step({0}, initial->point, u0, {}));
    const auto x2 = std::get<Vector>(resolved.model().step({1}, x1, u1, {}));
    const auto cost = std::get<double>(optimization::evaluate(resolved.objective(), x2));
    if (x1 != Vector{0.25} || x2 != Vector{1} || cost != 0)
        throw std::runtime_error("Independent teaching-history oracle differs; this is not a general scenario runner");
    std::cout << "source=" << scenario.source()->location.string() << '\n'
              << "source_sha256=" << problem::hex(scenario.source()->content.digest()) << '\n'
              << "problem=" << resolved.identity().value << '\n'
              << "state_dimension=" << dimensions.state << " control_dimension=" << dimensions.control
              << " horizon=" << resolved.model().horizon() << '\n'
              << "states=" << initial->point[0] << ',' << x1[0] << ',' << x2[0]
              << " controls=" << u0[0] << ',' << u1[0] << " original_cost=" << cost << '\n';
    if (std::holds_alternative<input::ComparisonRequest>(scenario.requested_run()->selection))
        std::cout << "requested=comparison (intent only; no strategies resolved or executed)\n";
    else
        std::cout << "requested=explicit methods (intent only; no strategies resolved or executed)\n";
    std::cout << "Scope: file intake and stated-history evaluation; constraint verification and full-family synthesis remain pending.\n";
} catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
