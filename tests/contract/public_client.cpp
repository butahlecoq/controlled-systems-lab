#include <csl/contracts.hpp>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
void require_shape_rejection(const Dynamics& dynamics, std::size_t horizon) {
    const auto diagnostics = check_model_shape(dynamics, horizon);
    require(diagnostics.size() == 1, "Expected one shape diagnostic");
    require(diagnostics.front().code == DiagnosticCode::invalid_input,
        "Malformed shape must be invalid input");
    require(diagnostics.front().field == "dynamics.stages",
        "Shape diagnostic must identify the stages field");
}

}

int main() try {
    using namespace csl;
    const LinearStage stage{{2,2,{1,2,0,0}}, {2,1,{2,-1}}, {2,0,{}}, {1,3}};
    const Dynamics constant{{2,1,0}, TimeDomain::discrete, stage};
    const Dynamics stagewise{{2,1,0}, TimeDomain::discrete,
        std::vector<LinearStage>{stage,stage}};
    require(check_model_shape(constant, 2).empty(), "Constant model shape must be valid");
    require(check_model_shape(stagewise, 2).empty(), "Stagewise model shape must be valid");
    auto malformed = constant;
    malformed.dimensions.control = 2;
    require_shape_rejection(malformed, 2);
    malformed = constant;
    std::get<LinearStage>(malformed.stages).A.values.pop_back();
    require_shape_rejection(malformed, 2);
    malformed = constant;
    std::get<LinearStage>(malformed.stages).offset.pop_back();
    require_shape_rejection(malformed, 2);
    for (const std::size_t count : {0u,1u,3u}) {
        malformed = stagewise;
        malformed.stages = std::vector<LinearStage>(count, stage);
        require_shape_rejection(malformed, 2);
    }
    std::cout << "Public contract client: shape guards passed\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
