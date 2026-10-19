#include <csl/geometry/lazy.hpp>
#include <csl/geometry/polyhedral_support.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>

#include <array>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <variant>

using namespace csl;
using namespace csl::registry;

namespace {
template<class T, class... Alternatives> T take(std::variant<T, Alternatives...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("GEO-08 fixture failed");
    return std::get<T>(std::move(value));
}

struct Providers {
    PreparedProvider<GeometryPort> expressions;
    PreparedProvider<GeometryPort> support;
    PreparedProvider<ConversionPort> materializer;
};

Providers providers() {
    Registry<GeometryPort> expressions;
    if (expressions.add(geometry::lazy::make_expression_registration()))
        throw std::runtime_error("Expression registration failed");
    Requirements expression_requirements;
    expression_requirements.output.representation = {"csl.geometry.lazy-v"};
    expression_requirements.output.relation = SetRelation::equivalent;
    auto expression = take(prepare_provider(select_provider(expressions,
        {{"csl.geometry.lazy-expression"}, {}}, expression_requirements)));

    Registry<GeometryPort> leaves;
    if (leaves.add(geometry::polyhedral::make_support_registration()))
        throw std::runtime_error("Leaf registration failed");
    auto leaf = take(prepare_provider(select_provider(leaves,
        {{"csl.geometry.polyhedral-support"}, {}})));
    Registry<GeometryPort> support;
    if (support.add(geometry::lazy::make_support_registration(std::move(leaf))))
        throw std::runtime_error("Support registration failed");
    auto support_provider = take(prepare_provider(select_provider(support,
        {{"csl.geometry.lazy-support"}, {}})));

    Registry<ConversionPort> materializers;
    if (materializers.add(geometry::lazy::make_materializer({16, 0})))
        throw std::runtime_error("Materializer registration failed");
    Requirements conversion_requirements;
    conversion_requirements.output.representation = {"csl.polyhedron.v"};
    conversion_requirements.output.relation = SetRelation::equivalent;
    auto materializer = take(prepare_provider(select_provider(materializers,
        {{"csl.geometry.lazy-materializer"}, {}}, conversion_requirements)));
    return {std::move(expression), std::move(support_provider), std::move(materializer)};
}

SetHandle square() {
    return take(sets::make_v({{"geo08-square"}, 2, {}},
        {take(numeric::snapshot(Matrix{4, 2, {0, 0, 1, 0, 0, 1, 1, 1}})),
         take(numeric::snapshot(Matrix{0, 2, {}}))})).as_handle();
}

bool checked_call(const SetHandle& source, const Providers& selected) {
    OperationRequest affine{{{"geo08-report"}, {"affine"}, {"geo08-mapped"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{source, {2, 2, {2, 0, 0, 1}}, {1, -1}},
        SetRelation::equivalent, Assurance::numerical};
    auto mapped_pipeline = take(selected.expressions.prepare(affine));
    const auto mapped = take<OperationResult>(std::get<0>(mapped_pipeline.create())->run({})).output;

    OperationRequest sum{{{"geo08-report"}, {"sum"}, {"geo08-sum"}},
        {"csl.geometry.lazy-expression"}, MinkowskiSum{mapped, source},
        SetRelation::equivalent, Assurance::numerical};
    auto sum_pipeline = take(selected.expressions.prepare(sum));
    const auto expression = take<OperationResult>(std::get<0>(sum_pipeline.create())->run({})).output;

    OperationRequest query{{{"geo08-report"}, {"support"}, {"geo08-answer"}},
        {"csl.geometry.lazy-support"}, SupportQuery{expression, {1, 1}},
        SetRelation::equivalent, Assurance::numerical};
    auto support_pipeline = take(selected.support.prepare(query));
    const auto support_outcome = std::get<0>(support_pipeline.create())->run({});
    if (!std::holds_alternative<SupportResult>(support_outcome)) return false;
    const auto& answer = std::get<SupportResult>(support_outcome);
    if (!std::holds_alternative<double>(answer.value) || std::get<double>(answer.value) != 5.0 ||
        answer.maximizer != Vector{4, 1} ||
        !std::holds_alternative<Unestablished>(answer.evidence.support)) return false;

    ConversionRequest conversion{{{"geo08-report"}, {"materialize"}, {"geo08-v"}},
        expression, {"csl.polyhedron.v"}, Assurance::numerical};
    const auto output = take<geometry::lazy::MaterializationResult>(
        geometry::lazy::materialize_expression(conversion, {16, 0}, selected.materializer, {}));
    if (output.growth.source_vertices != 8 || output.growth.estimated_vertices != 16 ||
        output.growth.realized_vertices != 16 || output.growth.realized_rays != 0 ||
        output.result.relation != SetRelation::equivalent ||
        !std::holds_alternative<Unestablished>(output.result.evidence.support)) return false;
    const auto native = take(sets::from_handle(output.result.output)).representation();
    const auto* v = std::get_if<sets::VRepresentation>(&native);
    if (!v || v->vertices.rows() != 16 || v->vertices.cols() != 2) return false;
    constexpr std::array<std::array<double, 2>, 4> corners{{
        {{0, 0}}, {{1, 0}}, {{0, 1}}, {{1, 1}}}};
    std::size_t row = 0;
    for (const auto& mapped_corner : corners)
        for (const auto& source_corner : corners) {
            const double x = 1 + 2 * mapped_corner[0] + source_corner[0];
            const double y = -1 + mapped_corner[1] + source_corner[1];
            if (v->vertices(row, 0) != x || v->vertices(row, 1) != y) return false;
            ++row;
        }
    return true;
}

bool batch(const SetHandle& source, const Providers& selected,
        std::string_view phase, int repetition, int calls) {
    std::chrono::nanoseconds elapsed{};
    bool verified = true;
    for (int call = 0; call < calls; ++call) {
        const auto start = std::chrono::steady_clock::now();
        try { verified = checked_call(source, selected); }
        catch (const std::exception&) { verified = false; }
        const auto end = std::chrono::steady_clock::now();
        elapsed += std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
        if (!verified) break;
    }
    std::cout << phase << ',' << repetition << ',' << calls << ','
              << (verified ? "completed" : "failed") << ','
              << (verified ? "true" : "false") << ',' << elapsed.count() << ','
              << (verified ? "5,16,0" : "unavailable,unavailable,unavailable") << '\n';
    return verified;
}
} // namespace

int main(int argc, char** argv) {
    if (argc != 2 || (std::string_view(argv[1]) != "smoke" &&
            std::string_view(argv[1]) != "measure")) return EXIT_FAILURE;
    const auto selected = providers();
    const auto source = square();
    std::cout << "phase,repetition,calls,status,verified,elapsed_ns,support,vertices,rays\n";
    if (std::string_view(argv[1]) == "smoke")
        return batch(source, selected, "smoke", 0, 1) ? EXIT_SUCCESS : EXIT_FAILURE;
    if (!batch(source, selected, "warmup", 0, 100)) return EXIT_FAILURE;
    for (int repetition = 0; repetition < 7; ++repetition)
        if (!batch(source, selected, "trial", repetition, 100)) return EXIT_FAILURE;
    return EXIT_SUCCESS;
}
