#include "native_catalogue_projection.hpp"

#include <csl/geometry/generators.hpp>
#include <csl/model/linear_system.hpp>

#include <cmath>
#include <iostream>
#include <numbers>

namespace {
using namespace csl;
using native_catalogue_example::CapturedCase;
using native_catalogue_example::Cloud;

template <class T, class... Errors> T take(std::variant<T, Errors...> result) {
    if (auto *value = std::get_if<T>(&result))
        return std::move(*value);
    throw std::runtime_error("Four-state native reachability operation failed");
}

Matrix own(const numeric::MatrixView &view) {
    Matrix result{view.rows(), view.cols(), {}};
    for (std::size_t i = 0; i < view.rows(); ++i)
        for (std::size_t j = 0; j < view.cols(); ++j)
            result.values.push_back(view(i, j));
    return result;
}

// Independent backward support recurrence, transcribed directly from the 2017
// comparison equations. It does not read the native model or its generators.
long double reference_support(std::size_t stage, const Vector &direction) {
    constexpr long double A[4][4]{{1, 0, 0.03L, 0},
                                  {0.014L, 1, 0.0001L, 0.03L},
                                  {0.114L, 0, 1, -0.0002L},
                                  {0.915L, 0, 0.014L, 1}};
    constexpr long double B[4]{-0.0024L, 0.0051L, -0.157L, 0.339L};
    constexpr long double radii[4]{0.052L, 5, 0.018L, 1};
    std::array<long double, 4> dual{direction[0], direction[1], direction[2], direction[3]};
    long double value = 0;
    for (std::size_t k = 0; k < stage; ++k) {
        long double input = 0;
        for (std::size_t j = 0; j < 4; ++j)
            input += B[j] * dual[j];
        value += 0.14L * std::abs(input);
        std::array<long double, 4> next{};
        for (std::size_t j = 0; j < 4; ++j)
            for (std::size_t i = 0; i < 4; ++i)
                next[j] += A[i][j] * dual[i];
        dual = next;
    }
    for (std::size_t j = 0; j < 4; ++j)
        value += radii[j] * std::abs(dual[j]);
    return value;
}

long double native_support(const sets::GeneratorSet &set, const Vector &direction) {
    long double value = 0;
    for (std::size_t i = 0; i < 4; ++i)
        value += direction[i] * set.center()[i];
    const auto &G = set.generators();
    for (std::size_t j = 0; j < G.cols; ++j) {
        long double projection = 0;
        for (std::size_t i = 0; i < 4; ++i)
            projection += direction[i] * G.values[i * G.cols + j];
        value += std::abs(projection);
    }
    return value;
}

// Retain full-state witnesses while taking a 2D hull after each generator
// segment is added. These are projection-boundary witnesses, not a 4D V set.
Cloud projection_witnesses(const sets::GeneratorSet &set, std::size_t first, std::size_t second) {
    Cloud witnesses{set.center()};
    const auto &G = set.generators();
    for (std::size_t j = 0; j < G.cols; ++j) {
        Cloud candidates, projected;
        for (const auto &point : witnesses)
            for (const double sign : {-1.0, 1.0}) {
                auto next = point;
                for (std::size_t i = 0; i < 4; ++i)
                    next[i] += sign * G.values[i * G.cols + j];
                projected.push_back({next[first], next[second]});
                candidates.push_back(std::move(next));
            }
        const auto hull = native_catalogue_example::projected_hull(projected);
        witnesses.clear();
        for (const auto index : hull.vertex_indices)
            witnesses.push_back(std::move(candidates[index]));
    }
    return witnesses;
}
}

int main(int argc, char **argv) try {
    if (argc > 2 || (argc == 2 && std::string_view(argv[1]).starts_with("--")))
        throw std::runtime_error("Usage: native_four_state_reachability [new-output-directory]");
    const auto data = take(model::catalogue::make_discrete_reachability_case(
        "archival-2017-4d-scalar-reachability/1"));
    const auto system = take(model::snapshot(data.model, data.time_grid));
    std::vector<sets::GeneratorSet> sets{data.initial};
    for (std::size_t k = 0; k < system.horizon(); ++k) {
        const auto stage = take(system.stage({k}));
        const auto prefix = std::string(data.info.id) + "/stage/" + std::to_string(k + 1);
        const auto state = take(geometry::generators::affine_image(
            sets.back(), own(stage.A),
            Vector(stage.offset.values().begin(), stage.offset.values().end()),
            {prefix + "/state-image"}));
        const auto control = take(geometry::generators::affine_image(
            data.controls[k], own(stage.B), Vector(4, 0), {prefix + "/control-image"}));
        sets.push_back(
            take(geometry::generators::minkowski_sum(state, control, {prefix + "/reachable"})));
    }
    std::ofstream support_csv, generators_csv, witnesses_csv;
    std::optional<std::filesystem::path> output;
    if (argc == 2) {
        output = std::filesystem::path(argv[1]);
        if (!std::filesystem::create_directory(*output))
            throw std::runtime_error("Output directory must be new");
        support_csv.open(*output / "full-state-support-checks.csv");
        generators_csv.open(*output / "full-state-generators.csv");
        witnesses_csv.open(*output / "projection-boundary-witnesses.csv");
        for (auto *stream : {&support_csv, &generators_csv, &witnesses_csv}) {
            stream->exceptions(std::ios::badbit | std::ios::failbit);
            *stream << std::setprecision(17);
        }
        support_csv << "stage,d1,d2,d3,d4,native_support,reference_support,absolute_difference\n";
        support_csv << std::setprecision(std::numeric_limits<long double>::max_digits10);
        generators_csv << "stage,kind,factor_id,x1,x2,x3,x4\n";
        witnesses_csv << "stage,point_id,x1,x2,x3,x4\n";
    }
    CapturedCase capture{data.info, {}, {{{0, 1}, {2, 3}}}};
    long double maximum_error = 0;
    std::size_t checks = 0, projection_checks = 0;
    for (std::size_t k = 0; k < sets.size(); ++k) {
        const auto &set = sets[k];
        if (set.factor_ids().size() != 4 + k)
            throw std::runtime_error("An independent input factor was lost");
        for (int ordinal = 0; ordinal < 81; ++ordinal) {
            int digits = ordinal;
            Vector direction(4);
            bool nonzero = false;
            for (auto &component : direction) {
                component = digits % 3 - 1;
                digits /= 3;
                nonzero = nonzero || component != 0;
            }
            if (!nonzero)
                continue;
            const auto actual = native_support(set, direction),
                       expected = reference_support(k, direction);
            const auto error = std::abs(actual - expected);
            maximum_error = std::max(maximum_error, error);
            if (error > 1e-11L * (1 + std::abs(expected)))
                throw std::runtime_error("Independent full-state support check failed");
            ++checks;
            if (output) {
                support_csv << k;
                for (const auto component : direction)
                    support_csv << ',' << component;
                support_csv << ',' << actual << ',' << expected << ',' << error << '\n';
            }
        }
        auto cloud = projection_witnesses(set, 0, 1);
        const auto other = projection_witnesses(set, 2, 3);
        for (std::size_t plane = 0; plane < 2; ++plane) {
            const auto &witnesses = plane == 0 ? cloud : other;
            for (std::size_t j = 0; j < 64; ++j) {
                Vector direction(4, 0);
                const double angle = 2 * std::numbers::pi * static_cast<double>(j) / 64;
                direction[2 * plane] = std::cos(angle);
                direction[2 * plane + 1] = std::sin(angle);
                long double actual = -std::numeric_limits<long double>::infinity();
                for (const auto &point : witnesses) {
                    long double value = 0;
                    for (std::size_t i = 0; i < 4; ++i)
                        value += direction[i] * point[i];
                    actual = std::max(actual, value);
                }
                const auto expected = reference_support(k, direction);
                if (std::abs(actual - expected) > 1e-11L * (1 + std::abs(expected)))
                    throw std::runtime_error(
                        "Independent projection-boundary support check failed");
                ++projection_checks;
            }
        }
        if (output) {
            generators_csv << k << ",center,none";
            for (const auto value : set.center())
                generators_csv << ',' << value;
            generators_csv << '\n';
            for (std::size_t j = 0; j < set.generators().cols; ++j) {
                generators_csv << k << ",generator," << set.factor_ids()[j].value;
                for (std::size_t i = 0; i < 4; ++i)
                    generators_csv << ',' << set.generators().values[i * set.generators().cols + j];
                generators_csv << '\n';
            }
            cloud.insert(cloud.end(), other.begin(), other.end());
            for (std::size_t i = 0; i < cloud.size(); ++i) {
                witnesses_csv << k << ',' << i;
                for (const auto value : cloud[i])
                    witnesses_csv << ',' << value;
                witnesses_csv << '\n';
            }
            capture.stages.push_back(std::move(cloud));
        }
    }
    if (output) {
        const std::vector<CapturedCase> figures{std::move(capture)};
        for (const bool print : {false, true}) {
            const std::string variant = print ? "print" : "screen";
            native_catalogue_example::write_svg(*output / ("four-state-stages-" + variant + ".svg"),
                                                figures, print);
            for (std::size_t column = 0; column < 2; ++column) {
                const auto name = column == 0 ? "stages-x1-x2-" : "stages-x3-x4-";
                native_catalogue_example::write_svg(*output / (name + variant + ".svg"), figures,
                                                    print, std::pair{std::size_t{0}, column});
            }
        }
    }
    std::cout
        << std::setprecision(17) << "case=" << data.info.id
        << " dimension=4 controls=1 transitions=15 stages=" << sets.size()
        << " terminal_generators=" << sets.back().generators().cols << " support_checks=" << checks
        << " projection_checks=" << projection_checks
        << " maximum_support_difference=" << maximum_error << '\n'
        << "scope=numerical support checks; projection witnesses are not a full 4D V representation\n"
        << "Native four-state reachability: fifteen transitions and 1280 support checks passed\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
