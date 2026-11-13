#include "native_catalogue_projection.hpp"

#include <csl/geometry/generator_adapter.hpp>
#include <csl/geometry/generators.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/model/catalogue.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/registry/provider.hpp>

#include <algorithm>
#include <cmath>
#include <array>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace {
using namespace csl;
using Point = std::array<double, 3>;
using native_catalogue_example::Cloud;
using native_catalogue_example::CapturedCase;
using native_catalogue_example::write_svg;

template <class T, class... Errors> T take(std::variant<T, Errors...> result) {
    if (auto *value = std::get_if<T>(&result))
        return std::move(*value);
    throw std::runtime_error("Native catalogue operation rejected the source case");
}

template <class Port>
registry::PreparedProvider<Port> prepare(registry::Registration<Port> registration,
                                         RepresentationId output) {
    registry::Registry<Port> registry;
    const registry::Method method{registration.identity.id, registration.identity.version};
    if (registry.add(std::move(registration)))
        throw std::runtime_error("Provider registration failed");
    registry::Requirements requirements;
    requirements.output.representation = output;
    requirements.output.relation = SetRelation::equivalent;
    return take(
        registry::prepare_provider(registry::select_provider(registry, method, requirements)));
}

Matrix own(const numeric::MatrixView &view) {
    Matrix result{view.rows(), view.cols(), {}};
    for (std::size_t i = 0; i < view.rows(); ++i)
        for (std::size_t j = 0; j < view.cols(); ++j)
            result.values.push_back(view(i, j));
    return result;
}

// Independent literal recurrence from slide 50. The initial eight corners
// belong to our authored box; the manuscript's 78 initial vertices are unknown.
std::array<long double, 3> literal_point(std::size_t stage, std::size_t mask) {
    std::array<long double, 3> x{mask & 1 ? 0.5L : -0.5L, mask & 2 ? 1.0L : -1.0L,
                                 mask & 4 ? 1.0L : -1.0L};
    for (std::size_t k = 0; k < stage; ++k) {
        const long double u1 = mask & (std::size_t{1} << (3 + 2 * k)) ? 1 : -1;
        const long double u2 = mask & (std::size_t{1} << (4 + 2 * k)) ? 1 : -1;
        x = {0.1L * x[0] - 0.1L * x[1] + 0.8L * x[2], -1.8L * x[0] + 0.12L * x[2] + 0.2L * u1,
             0.64L * x[1] + 0.35L * x[2] + u2};
    }
    return x;
}

CapturedCase run_case(const model::catalogue::CaseInfo &info) {
    const auto data = take(model::catalogue::make_discrete_reachability_case(info.id));
    const auto system = take(model::snapshot(data.model, data.time_grid));
    auto converter =
        prepare(geometry::generators::make_v_conversion_registration(32768), {"csl.polyhedron.v"});
    auto operations =
        prepare(geometry::generators::make_operation_registration(), {"csl.zonotope"});
    ExecutionContext context;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    context.run_id = std::string(info.id);
    std::size_t serial = 0;
    auto identity = [&] {
        const auto name = std::string(info.id) + "/operation/" + std::to_string(serial++);
        return GeometryRequestIdentity{{std::string(info.id)}, {name}, {name + "/result"}};
    };
    auto apply = [&](GeometryOperation operation) {
        const OperationRequest request{identity(),
                                       {"csl.geometry.generators.operations"},
                                       std::move(operation),
                                       SetRelation::equivalent,
                                       Assurance::numerical};
        auto plan = take(operations.prepare(request));
        auto [work] = plan.create();
        const auto result = take(work->run(context));
        if (!check_geometry_evidence(result.evidence, request).empty())
            throw std::runtime_error("Generator operation evidence differs from the request");
        return take(sets::from_generator_handle(result.output));
    };
    CapturedCase capture{info, {}};
    auto reachable = data.initial;
    for (std::size_t k = 0; k <= system.horizon(); ++k) {
        const ConversionRequest request{
            identity(), reachable.as_handle(), {"csl.polyhedron.v"}, Assurance::numerical};
        auto plan = take(converter.prepare(request));
        auto [work] = plan.create();
        const auto result = take(work->run(context));
        if (!check_geometry_evidence(result.evidence, request).empty())
            throw std::runtime_error("V conversion evidence differs from the request");
        const auto vertices = take(sets::from_handle(result.output));
        const auto representation = vertices.representation();
        const auto &v = std::get<sets::VRepresentation>(representation);
        const auto expected_count = std::size_t{1} << (3 + 2 * k);
        if (v.vertices.rows() != expected_count || v.vertices.cols() != 3)
            throw std::runtime_error("Mapped cube-corner count differs from independent factors");
        if (reachable.factor_ids().size() != 3 + 2 * k)
            throw std::runtime_error("Independent stage input factors were lost");
        Cloud cloud;
        for (std::size_t row = 0; row < v.vertices.rows(); ++row) {
            Point point{v.vertices(row, 0), v.vertices(row, 1), v.vertices(row, 2)};
            const auto expected = literal_point(k, row);
            for (std::size_t j = 0; j < 3; ++j) {
                if (!std::isfinite(point[j]) ||
                    std::abs(static_cast<long double>(point[j]) - expected[j]) >
                        1e-11L * (1 + std::abs(expected[j])))
                    throw std::runtime_error(
                        "Full-state corner differs from independent source recurrence");
            }
            cloud.push_back({point[0], point[1], point[2]});
        }
        capture.stages.push_back(std::move(cloud));
        if (k == system.horizon())
            break;
        const auto stage = take(system.stage({k}));
        const auto state_image =
            apply(AffineImage{reachable.as_handle(), own(stage.A),
                              Vector(stage.offset.values().begin(), stage.offset.values().end())});
        const auto control_image =
            apply(AffineImage{data.controls[k].as_handle(), own(stage.B), Vector(3, 0)});
        reachable = apply(MinkowskiSum{state_image.as_handle(), control_image.as_handle()});
    }
    std::cout << "case=" << info.id << " dimension=3 controls=2 transitions=" << info.transitions
              << " verified_full_state_stages=" << capture.stages.size()
              << " terminal_cube_corners=" << capture.stages.back().size() << '\n';
    return capture;
}

}

int main(int argc, char **argv) try {
    const auto entries = csl::model::catalogue::discrete_reachability_cases();
    if (argc == 2 && std::string_view(argv[1]) == "--list") {
        for (const auto &info : entries)
            std::cout << info.id << " | " << info.title << '\n';
        return 0;
    }
    if (argc > 2 || (argc == 2 && std::string_view(argv[1]).starts_with("--")))
        throw std::runtime_error(
            "Usage: native_slide50_reachability [new-output-directory | --list]");
    std::vector<CapturedCase> cases;
    for (const auto &info : entries)
        if (info.id.starts_with("bulaev-2016-slide50/"))
            cases.push_back(run_case(info));
    if (cases.size() != 2)
        throw std::runtime_error("Both authored-box horizon variants must be discoverable");
    if (argc == 2) {
        const std::filesystem::path output(argv[1]);
        if (!std::filesystem::create_directory(output))
            throw std::runtime_error("Output directory must be new");
        std::ofstream provenance(output / "model-provenance.txt");
        provenance.exceptions(std::ios::badbit | std::ios::failbit);
        provenance
            << "scope=forward reachability; binary64 algebra, no validated rounding enclosure\n"
            << "initial_set=authored box [-0.5,0.5] x [-1,1] x [-1,1]; eight corners\n"
            << "original_initial_set=78 vertices, coordinates unavailable; no historical-set reproduction claim\n"
            << "controls=independent u1,u2 in [-1,1] each stage\n";
        for (const auto &data : cases)
            provenance << "case=" << data.info.id << " source_sha256=" << data.info.source.sha256
                       << " locator=" << data.info.source.locator << '\n'
                       << "qualification=" << data.info.source.qualification << '\n';
        std::ofstream csv(output / "full-state-v-points.csv");
        csv.exceptions(std::ios::badbit | std::ios::failbit);
        csv << std::setprecision(17) << "case_id,stage,point_id,x1,x2,x3\n";
        for (const auto &data : cases)
            for (std::size_t k = 0; k < data.stages.size(); ++k)
                for (std::size_t i = 0; i < data.stages[k].size(); ++i) {
                    const auto &p = data.stages[k][i];
                    csv << data.info.id << ',' << k << ',' << i << ',' << p[0] << ',' << p[1] << ','
                        << p[2] << '\n';
                }
        write_svg(output / "slide50-authored-box-screen.svg", cases, false);
        write_svg(output / "slide50-authored-box-print.svg", cases, true);
        for (std::size_t row = 0; row < cases.size(); ++row)
            for (std::size_t column = 0; column < 2; ++column) {
                const auto name = "stages-" + std::to_string(cases[row].info.transitions) +
                                  "-x1-x" + std::to_string(column + 2);
                write_svg(output / (name + "-screen.svg"), cases, false, std::pair{row, column});
                write_svg(output / (name + "-print.svg"), cases, true, std::pair{row, column});
            }
    }
    std::cout
        << "Slide50 authored box: both horizon variants and all full-state corner checks passed\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
