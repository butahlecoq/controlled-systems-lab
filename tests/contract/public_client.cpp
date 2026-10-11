// Backend-neutral acceptance client; no numerical model module exists yet.
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

// Test-local arithmetic over neutral values, NOT a product model/numeric API.
// The boundary guard is called before this helper; validated shapes are trusted.
Vector fixture_step(const LinearStage& stage, const Vector& state, double control) {
    Vector result = stage.offset;
    for (std::size_t row = 0; row < stage.A.rows; ++row) {
        for (std::size_t col = 0; col < stage.A.cols; ++col)
            result[row] += stage.A.values[row * stage.A.cols + col] * state[col];
        result[row] += stage.B.values[row] * control;
    }
    return result;
}
void literal_affine_fixture(const Dynamics& dynamics) {
    require(check_model_shape(dynamics, 2).empty(), "Fixture must have valid shape");
    const auto stage_at = [&](std::size_t index) -> const LinearStage& {
        if (const auto* constant = std::get_if<LinearStage>(&dynamics.stages)) return *constant;
        return std::get<std::vector<LinearStage>>(dynamics.stages)[index];
    };
    // Independently derived for A=[[1,2],[0,0]], B=[[2],[-1]], a=[1,3]:
    // x0=[2,-1], u0=2 => x1=[2-2+4+1, -2+3]=[5,1].
    // u1=-1 => x2=[5+2-2+1, 1+3]=[6,4]. Singular A needs no inverse.
    const auto first = fixture_step(stage_at(0), {2,-1}, 2);
    require(first == Vector{5,1}, "First affine state must equal literal [5,1]");
    require(fixture_step(stage_at(1), first, -1) == Vector{6,4},
        "Second affine state must equal literal [6,4]");
}
} // namespace

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
