#include <csl/contracts.hpp>
#include <csl/model/linear_system.hpp>
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

void literal_affine_fixture(const Dynamics& dynamics) {
    require(check_model_shape(dynamics, 2).empty(), "Fixture must have valid shape");
    const Vector times{0,1,2};
    const auto snapshot = csl::model::snapshot({dynamics,{}}, times);
    require(std::holds_alternative<csl::model::LinearSystem>(snapshot),
        "Affine fixture must snapshot successfully");
    const auto& system = std::get<csl::model::LinearSystem>(snapshot);
    Vector state{2,-1};
    Vector control{2};
    const Vector external{};
    const auto first = system.step({0}, state, control, external);
    require(std::holds_alternative<Vector>(first), "First affine step must succeed");
    state = std::get<Vector>(first);
    require(state == Vector{5,1}, "First affine state must equal literal [5,1]");
    control = {-1};
    const auto second = system.step({1}, state, control, external);
    require(std::holds_alternative<Vector>(second), "Second affine step must succeed");
    require(std::get<Vector>(second) == Vector{6,4},
        "Second affine state must equal literal [6,4]");
}
}

int main() try {
    using namespace csl;
    const LinearStage stage{{2,2,{1,2,0,0}}, {2,1,{2,-1}}, {2,0,{}}, {1,3}};
    const Dynamics constant{{2,1,0}, TimeDomain::discrete, stage};
    const Dynamics stagewise{{2,1,0}, TimeDomain::discrete,
        std::vector<LinearStage>{stage,stage}};
    literal_affine_fixture(constant);
    literal_affine_fixture(stagewise);

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
    std::cout << "Public contract client: shape guards and literal affine fixture passed\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
