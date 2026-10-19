#include <csl/geometry/lazy.hpp>
#include <csl/geometry/polyhedral_support.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>

#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::registry;
    const auto vertices = numeric::snapshot(Matrix{4, 2, {0, 0, 1, 0, 0, 1, 1, 1}});
    const auto rays = numeric::snapshot(Matrix{0, 2, {}});
    if (!std::holds_alternative<numeric::MatrixView>(vertices) ||
        !std::holds_alternative<numeric::MatrixView>(rays)) return 1;
    const auto source = sets::make_v({{"installed-square"}, 2, {}},
        {std::get<numeric::MatrixView>(vertices), std::get<numeric::MatrixView>(rays)});
    if (!std::holds_alternative<sets::SetData>(source)) return 2;

    Registry<GeometryPort> expressions;
    if (expressions.add(geometry::lazy::make_expression_registration())) return 3;
    Requirements expression_requirements;
    expression_requirements.output.representation = {"csl.geometry.lazy-v"};
    expression_requirements.output.relation = SetRelation::equivalent;
    auto expression_provider = prepare_provider(select_provider(expressions,
        {{"csl.geometry.lazy-expression"}, {}}, expression_requirements));
    if (!std::holds_alternative<PreparedProvider<GeometryPort>>(expression_provider)) return 4;
    OperationRequest expression_request{{{"installed"}, {"image"}, {"mapped"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{std::get<sets::SetData>(source).as_handle(), {2, 2, {2, 0, 0, 1}}, {1, -1}},
        SetRelation::equivalent, Assurance::numerical};
    auto expression = std::get<PreparedProvider<GeometryPort>>(expression_provider).prepare(expression_request);
    if (!std::holds_alternative<PreparedPipeline<GeometryPort>>(expression)) return 5;
    auto [expression_workspace] = std::get<PreparedPipeline<GeometryPort>>(expression).create();
    auto created = expression_workspace->run({});
    if (!std::holds_alternative<OperationResult>(created)) return 6;
    const auto lazy = std::get<OperationResult>(created).output;

    Registry<GeometryPort> leaves;
    if (leaves.add(geometry::polyhedral::make_support_registration())) return 7;
    auto leaf_provider = prepare_provider(select_provider(leaves,
        {{"csl.geometry.polyhedral-support"}, {}}));
    if (!std::holds_alternative<PreparedProvider<GeometryPort>>(leaf_provider)) return 8;
    Registry<GeometryPort> support_methods;
    if (support_methods.add(geometry::lazy::make_support_registration(
            std::get<PreparedProvider<GeometryPort>>(leaf_provider)))) return 9;
    auto support_provider = prepare_provider(select_provider(support_methods,
        {{"csl.geometry.lazy-support"}, {}}));
    if (!std::holds_alternative<PreparedProvider<GeometryPort>>(support_provider)) return 10;
    auto samples = geometry::lazy::sample_support(
        std::get<PreparedProvider<GeometryPort>>(support_provider), lazy,
        {{1, 1}}, {{"installed"}, {"sample"}, {"support"}}, {});
    if (!std::holds_alternative<geometry::lazy::SupportSamples>(samples)) return 11;
    const auto& sampled = std::get<geometry::lazy::SupportSamples>(samples);
    if (sampled.coverage != geometry::lazy::SampleCoverage::directions_only ||
        sampled.samples.size() != 1 ||
        !std::holds_alternative<double>(sampled.samples[0].answer.value) ||
        std::get<double>(sampled.samples[0].answer.value) != 3.0) return 12;

    Registry<ConversionPort> materializers;
    if (materializers.add(geometry::lazy::make_materializer({4, 0}))) return 13;
    Requirements materialization_requirements;
    materialization_requirements.output.representation = {"csl.polyhedron.v"};
    materialization_requirements.output.relation = SetRelation::equivalent;
    auto materializer = prepare_provider(select_provider(materializers,
        {{"csl.geometry.lazy-materializer"}, {}}, materialization_requirements));
    if (!std::holds_alternative<PreparedProvider<ConversionPort>>(materializer)) return 14;
    ConversionRequest conversion{{{"installed"}, {"materialize"}, {"mapped-v"}},
        lazy, {"csl.polyhedron.v"}, Assurance::numerical};
    const auto output = geometry::lazy::materialize_expression(conversion, {4, 0},
        std::get<PreparedProvider<ConversionPort>>(materializer), {});
    if (!std::holds_alternative<geometry::lazy::MaterializationResult>(output)) return 15;
    const auto& growth = std::get<geometry::lazy::MaterializationResult>(output).growth;
    if (growth.estimated_vertices != 4 || growth.realized_vertices != 4) return 16;
    std::cout << "Installed lazy geometry client: sampled support and budgeted V output passed\n";
}
