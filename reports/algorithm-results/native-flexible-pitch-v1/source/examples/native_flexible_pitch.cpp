#include "native_catalogue_projection.hpp"

#include <csl/geometry/generators.hpp>
#include <csl/model/flexible_pitch.hpp>
#include <csl/model/linear_system.hpp>

#include <cmath>
#include <iostream>
#include <numbers>

namespace {
using namespace csl;
using native_catalogue_example::Cloud;
template<class T, class... Errors> T take(std::variant<T, Errors...> result) {
    if (auto* value = std::get_if<T>(&result)) return std::move(*value);
    throw std::runtime_error("Native flexible-pitch operation failed");
}
Matrix own(const numeric::MatrixView& view) {
    Matrix result{view.rows(), view.cols(), {}};
    for (std::size_t i = 0; i < view.rows(); ++i)
        for (std::size_t j = 0; j < view.cols(); ++j) result.values.push_back(view(i, j));
    return result;
}
long double support(const sets::GeneratorSet& set, const Vector& direction) {
    long double result = 0;
    for (std::size_t i = 0; i < direction.size(); ++i) result += direction[i] * set.center()[i];
    const auto& G = set.generators();
    for (std::size_t j = 0; j < G.cols; ++j) {
        long double component = 0;
        for (std::size_t i = 0; i < direction.size(); ++i)
            component += direction[i] * G.values[i * G.cols + j];
        result += std::abs(component);
    }
    return result;
}
// Boundary witnesses retain every physical coordinate. Hull reduction happens
// only in the displayed plane; no high-dimensional vertex conversion is claimed.
Cloud projection(const sets::GeneratorSet& set, std::size_t a, std::size_t b) {
    Cloud witnesses{set.center()};
    const auto n = set.center().size();
    const auto& G = set.generators();
    for (std::size_t j = 0; j < G.cols; ++j) {
        Cloud candidates, points;
        for (const auto& previous : witnesses) for (const double sign : {-1.0, 1.0}) {
            auto next = previous;
            for (std::size_t i = 0; i < n; ++i) next[i] += sign * G.values[i * G.cols + j];
            points.push_back({next[a], next[b]});
            candidates.push_back(std::move(next));
        }
        const auto hull = native_catalogue_example::projected_hull(points);
        witnesses.clear();
        for (const auto index : hull.vertex_indices) witnesses.push_back(std::move(candidates[index]));
    }
    return witnesses;
}
// Independent augmented exponential and backward support recurrence. This does
// not use the discretizer's RK4 implementation or the propagated generators.
struct Reference {
    std::size_t n;
    std::vector<long double> A, B, radii;
    explicit Reference(const model::catalogue::FlexiblePitchCase& data)
        : n(data.reachability.info.states.size()), A(n * n), B(n), radii(n) {
        const auto m = n + 1;
        std::vector<long double> H(m * m, 0), term(m * m, 0), sum(m * m, 0);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j)
                H[i * m + j] = 0.1L * data.descriptor.rates.A.values[i * n + j];
            H[i * m + n] = 0.1L * data.descriptor.rates.B.values[i];
            radii[i] = data.reachability.initial.generators().values[i * n + i];
        }
        for (std::size_t i = 0; i < m; ++i) term[i * m + i] = sum[i * m + i] = 1;
        for (std::size_t order = 1; order <= 40; ++order) {
            std::vector<long double> next(m * m, 0);
            for (std::size_t i = 0; i < m; ++i)
                for (std::size_t j = 0; j < m; ++j)
                    for (std::size_t k = 0; k < m; ++k)
                        next[i * m + j] += term[i * m + k] * H[k * m + j] / static_cast<long double>(order);
            term = std::move(next);
            for (std::size_t i = 0; i < sum.size(); ++i) sum[i] += term[i];
        }
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) A[i * n + j] = sum[i * m + j];
            B[i] = sum[i * m + n];
        }
    }
    long double support(std::size_t stage, const Vector& direction) const {
        std::vector<long double> dual(direction.begin(), direction.end());
        long double result = 0;
        for (std::size_t k = 0; k < stage; ++k) {
            long double input = 0;
            for (std::size_t i = 0; i < n; ++i) input += B[i] * dual[i];
            result += (4 * std::numbers::pi_v<long double> / 180) * std::abs(input);
            std::vector<long double> next(n, 0);
            for (std::size_t j = 0; j < n; ++j)
                for (std::size_t i = 0; i < n; ++i) next[j] += A[i * n + j] * dual[i];
            dual = std::move(next);
        }
        for (std::size_t i = 0; i < n; ++i) result += radii[i] * std::abs(dual[i]);
        return result;
    }
};
}

int main(int argc, char** argv) try {
    if (argc > 2) throw std::runtime_error("Usage: native_flexible_pitch [new-output-directory]");
    std::optional<std::filesystem::path> output;
    if (argc == 2) {
        output = argv[1];
        if (!std::filesystem::create_directory(*output)) throw std::runtime_error("Output directory must be new");
    }
    std::size_t support_checks = 0, projection_checks = 0;
    long double maximum_error = 0;
    for (const auto& info : model::catalogue::flexible_pitch_cases()) {
        const auto data = take(model::catalogue::make_flexible_pitch_case(info.id));
        const auto& reach = data.reachability;
        const auto n = info.states.size();
        const auto system = take(model::snapshot(reach.model, reach.time_grid));
        const Reference reference(data);
        std::vector<sets::GeneratorSet> reachable{reach.initial};
        for (std::size_t k = 0; k < system.horizon(); ++k) {
            const auto stage = take(system.stage({k}));
            const auto prefix = std::string(info.id) + "/reachable/" + std::to_string(k + 1);
            const auto image = take(geometry::generators::affine_image(reachable.back(), own(stage.A),
                Vector(n, 0), {prefix + "/state"}));
            const auto input = take(geometry::generators::affine_image(reach.controls[k], own(stage.B),
                Vector(n, 0), {prefix + "/input"}));
            reachable.push_back(take(geometry::generators::minkowski_sum(image, input, {prefix})));
        }
        std::ofstream raw, checks, matrices, witnesses;
        if (output) {
            raw.open(*output / (std::to_string(n) + "-state-generators.csv"));
            checks.open(*output / (std::to_string(n) + "-state-support.csv"));
            matrices.open(*output / (std::to_string(n) + "-state-matrices.csv"));
            witnesses.open(*output / (std::to_string(n) + "-state-projection-witnesses.csv"));
            for (auto* stream : {&raw, &checks, &matrices, &witnesses}) {
                stream->exceptions(std::ios::badbit | std::ios::failbit);
                *stream << std::setprecision(std::numeric_limits<long double>::max_digits10);
            }
            raw << "stage,time_s,kind,factor_id";
            checks << "stage,time_s";
            for (const auto& coordinate : info.states) {
                raw << ',' << coordinate.name;
                checks << ",d_" << coordinate.name;
            }
            raw << '\n'; checks << ",native_support,exponential_reference,absolute_difference\n";
            witnesses << "stage,time_s,plane,point";
            for (const auto& coordinate : info.states) witnesses << ',' << coordinate.name;
            witnesses << '\n';
            matrices << "kind,stage,row,column,value\n";
            const auto write_matrix = [&](std::string_view kind, std::size_t stage, const Matrix& matrix) {
                for (std::size_t i = 0; i < matrix.rows; ++i)
                    for (std::size_t j = 0; j < matrix.cols; ++j)
                        matrices << kind << ',' << stage << ',' << i << ',' << j << ',' << matrix.values[i * matrix.cols + j] << '\n';
            };
            write_matrix("descriptor_E", 0, data.descriptor.mass);
            write_matrix("implicit_A", 0, data.descriptor.implicit_state);
            write_matrix("implicit_B", 0, data.descriptor.implicit_input);
            write_matrix("rate_A", 0, data.descriptor.rates.A);
            write_matrix("rate_B", 0, data.descriptor.rates.B);
            for (std::size_t k = 0; k < system.horizon(); ++k) {
                const auto stage = take(system.stage({k}));
                write_matrix("discrete_A", k, own(stage.A));
                write_matrix("discrete_B", k, own(stage.B));
            }
        }
        std::vector<std::pair<std::size_t, std::size_t>> planes;
        for (std::size_t j = 0; j < n; j += 2) planes.push_back({j, j + 1});
        std::vector<native_catalogue_example::CapturedCase> pictures;
        for (const auto [a, b] : planes) pictures.push_back({info, {}, {{{a, b}, {a, b}}}, true});
        for (std::size_t k = 0; k < reachable.size(); ++k) {
            const auto& set = reachable[k];
            if (set.factor_ids().size() != n + k) throw std::runtime_error("Independent control factor lost");
            for (std::size_t ordinal = 0; ordinal < 2 * n + 16; ++ordinal) {
                Vector direction(n, 0);
                if (ordinal < 2 * n) direction[ordinal / 2] = ordinal % 2 ? -1 : 1;
                else for (std::size_t i = 0; i < n; ++i)
                    direction[i] = std::sin(static_cast<double>((ordinal + 1) * (i + 1)));
                const auto actual = support(set, direction), expected = reference.support(k, direction);
                const auto error = std::abs(actual - expected);
                maximum_error = std::max(maximum_error, error);
                if (error > 2e-8L * (1 + std::abs(expected))) throw std::runtime_error("Full-state independent support failed");
                ++support_checks;
                if (output) {
                    checks << k << ',' << reach.time_grid[k];
                    for (const auto d : direction) checks << ',' << d;
                    checks << ',' << actual << ',' << expected << ',' << error << '\n';
                }
            }
            for (std::size_t plane = 0; plane < planes.size(); ++plane) {
                const auto [a, b] = planes[plane];
                auto boundary = projection(set, a, b);
                for (std::size_t ordinal = 0; ordinal < 64; ++ordinal) {
                    const auto angle = 2 * std::numbers::pi * static_cast<double>(ordinal) / 64;
                    Vector direction(n, 0); direction[a] = std::cos(angle); direction[b] = std::sin(angle);
                    long double actual = -std::numeric_limits<long double>::infinity();
                    for (const auto& point : boundary)
                        actual = std::max(actual, static_cast<long double>(direction[a]) * point[a] +
                            static_cast<long double>(direction[b]) * point[b]);
                    if (std::abs(actual - support(set, direction)) > 1e-11L * (1 + std::abs(actual)))
                        throw std::runtime_error("Projection boundary support failed");
                    ++projection_checks;
                }
                if (output) for (std::size_t point = 0; point < boundary.size(); ++point) {
                    witnesses << k << ',' << reach.time_grid[k] << ',' << plane << ',' << point;
                    for (const auto value : boundary[point]) witnesses << ',' << value;
                    witnesses << '\n';
                }
                pictures[plane].stages.push_back(std::move(boundary));
            }
            if (output) {
                raw << k << ',' << reach.time_grid[k] << ",center,";
                for (const auto value : set.center()) raw << ',' << value;
                raw << '\n';
                const auto& G = set.generators();
                for (std::size_t j = 0; j < G.cols; ++j) {
                    raw << k << ',' << reach.time_grid[k] << ",generator," << set.factor_ids()[j].value;
                    for (std::size_t i = 0; i < n; ++i) raw << ',' << G.values[i * G.cols + j];
                    raw << '\n';
                }
            }
        }
        if (output) for (std::size_t plane = 0; plane < planes.size(); ++plane) {
            const auto stem = std::to_string(n) + "-state-plane-" + std::to_string(plane);
            native_catalogue_example::write_svg(*output / (stem + ".svg"), pictures, false, std::pair{plane, std::size_t{0}});
            native_catalogue_example::write_svg(*output / (stem + "-print.svg"), pictures, true, std::pair{plane, std::size_t{0}});
        }
    }
    std::cout << "Native flexible pitch: 3 synthetic physical models; support_checks=" << support_checks
        << " projection_checks=" << projection_checks << " maximum_absolute_support_difference=" << maximum_error
        << "; independent amplitude inputs, no stabilization objective\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
}
