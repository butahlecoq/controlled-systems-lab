#include <csl/problem/validator.hpp>
#include <csl/sets/data.hpp>
#include <iostream>
#include <stdexcept>

int main() try {
    using namespace csl;
    // Publish 0 <= u <= 1 as original H rows: -u <= 0, u <= 1.
    const auto H = std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2, 1, {-1, 1}}));
    const auto h = std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{0, 1}));
    const auto E = std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0, 1, {}}));
    const auto e = std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{}));
    const auto controls = std::get<sets::SetData>(sets::make_h({{"/controls"}, 1, {}}, {H, h, E, e}));
    const auto system = std::make_shared<const SystemModel>(SystemModel{
        {{1, 1, 0}, TimeDomain::discrete, LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}});
    const Problem authored{{"two-stage-integrator"}, system, {0, 1, 2}, KnownInitial{{0}},
        ContinuousDomain{{controls.as_handle(), controls.as_handle()}},
        {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}}, {}, {}, InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1, 1, {2}}, {-2}, 1}}; // 1/2 * 2*x^2 - 2*x + 1 = (x-1)^2
    const auto publication = problem::resolve(authored, {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    if (const auto* diagnostic = std::get_if<Diagnostic>(&publication))
        throw std::runtime_error(diagnostic->field + ": " + diagnostic->explanation);
    const auto resolved = std::get<problem::ResolvedProblem>(publication);

    // Evaluate a stated history. No synthesis method chose these controls.
    const Vector x0{0}, u0{0.25}, u1{0.75};
    const auto x1 = std::get<Vector>(resolved.model().step({0}, x0, u0, {}));
    const auto x2 = std::get<Vector>(resolved.model().step({1}, x1, u1, {}));
    const auto cost = std::get<double>(optimization::evaluate(resolved.objective(), x2));
    if (x1 != Vector{0.25} || x2 != Vector{1} || cost != 0)
        throw std::runtime_error("Independent teaching-history oracle differs");
    const auto dimensions = resolved.model().dimensions();
    std::cout << "problem=" << resolved.identity().value << '\n'
              << "state_dimension=" << dimensions.state << " control_dimension=" << dimensions.control
              << " horizon=" << resolved.model().horizon() << '\n'
              << "states=" << x0[0] << ',' << x1[0] << ',' << x2[0]
              << " controls=" << u0[0] << ',' << u1[0] << " original_cost=" << cost << '\n'
              << "Scope: immutable publication and stated-history evaluation, no synthesis or full-family result.\n";
} catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
