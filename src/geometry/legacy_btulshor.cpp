#include <csl/geometry/legacy_btulshor.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace csl::geometry::legacy_btulshor {
namespace {

std::optional<Stopped> interruption(const Limits &limits) {
    if (limits.cancellation.stop_requested())
        return Stopped{StopReason::cancelled,
                       "BTULSHOR execution cancelled at cooperative checkpoint"};
    if (limits.deadline && std::chrono::steady_clock::now() >= *limits.deadline)
        return Stopped{StopReason::deadline_expired,
                       "BTULSHOR deadline expired at cooperative checkpoint"};
    return std::nullopt;
}

Stopped stopped(StopReason reason, const char *message) { return {reason, message}; }

bool checked_product(std::size_t a, std::size_t b, std::size_t &result) {
    if (a != 0 && b > std::numeric_limits<std::size_t>::max() / a)
        return false;
    result = a * b;
    return true;
}

bool checked_sum(std::size_t a, std::size_t b, std::size_t &result) {
    if (b > std::numeric_limits<std::size_t>::max() - a)
        return false;
    result = a + b;
    return true;
}

bool finite(const Vector &values) {
    return std::all_of(values.begin(), values.end(), [](double x) { return std::isfinite(x); });
}

bool valid_selection(std::span<const Vector> input, const KpabepResult &output,
                     std::size_t dimension) {
    if (output.points.size() != output.retained_indices.size() ||
        output.points.size() > input.size())
        return false;
    std::vector<bool> seen(input.size(), false);
    for (std::size_t i = 0; i < output.points.size(); ++i) {
        const auto index = output.retained_indices[i];
        if (index >= input.size() || seen[index] || output.points[i].size() != dimension ||
            !finite(output.points[i]) || output.points[i] != input[index])
            return false;
        seen[index] = true;
    }
    return true;
}

Outcome<ModifResult> run_modif(const ModifRequest &request, const Limits &limits) {
    const auto m = request.a.rows;
    const auto n = request.a.cols;
    std::size_t entries{};
    if (!checked_product(m, n, entries))
        return stopped(StopReason::capacity_limit, "MODIF matrix dimensions overflow");
    std::size_t basis_entries{};
    if (!checked_product(m, m, basis_entries))
        return stopped(StopReason::capacity_limit, "MODIF basis dimensions overflow");
    if (m < 3 || m > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        n > static_cast<std::size_t>(std::numeric_limits<int>::max()) || request.x.size() != m ||
        request.a.values.size() != entries || !finite(request.a.values) || !finite(request.x) ||
        !std::isfinite(request.epsilon) ||
        (request.initial_status != 0 && request.initial_status != 1)) {
        return stopped(StopReason::invalid_input,
                       "MODIF requires rows >= 3, matching finite data, and status 0 or 1");
    }
    if (entries > limits.max_dense_entries || basis_entries > limits.max_dense_entries) {
        return stopped(StopReason::capacity_limit,
                       "MODIF dense matrix exceeds configured capacity");
    }

    // Pascal A is column-major and passed by value. Build that private copy.
    Vector a(entries);
    for (std::size_t i = 0; i < m; ++i) {
        if (auto stop = interruption(limits))
            return *stop;
        for (std::size_t j = 0; j < n; ++j)
            a[i + m * j] = request.a.values[i * n + j];
    }
    Vector x = request.x;
    Vector u(m * m, 0.0);
    Vector xk(m, 0.0);
    std::vector<int> nb(m);
    if (request.initial_status == 1)
        for (std::size_t j = 0; j < n; ++j)
            a[(m - 2) + m * j] = -a[(m - 2) + m * j];

    for (std::size_t i = 0; i < m; ++i) {
        u[i + m * i] = 1.0;
        nb[i] = -static_cast<int>(i + 1);
    }

    int ne = 1;
    int p = request.initial_status;
    std::size_t pivots = 0;
    std::vector<PivotStep> trace;
    std::vector<int> phases;
    bool truncated = false;
    std::size_t trace_events = 0;
    auto record_phase = [&](int phase) {
        if (!limits.capture_trace)
            return;
        if (trace_events < limits.max_trace_events) {
            phases.push_back(phase);
            ++trace_events;
        } else
            truncated = true;
    };
    auto record_pivot = [&](PivotStep step) {
        if (!limits.capture_trace)
            return;
        if (trace_events < limits.max_trace_events) {
            trace.push_back(step);
            ++trace_events;
        } else
            truncated = true;
    };
    record_phase(ne);

    for (;;) {
        if (auto stop = interruption(limits))
            return *stop;
        double minimum = 0.0;
        std::size_t k = 0;
        // Literal MODIF entering-column scan. Strict comparisons keep first ties.
        for (std::size_t j = 0; j < n; ++j) {
            if (auto stop = interruption(limits))
                return *stop;
            bool basic = false;
            for (std::size_t i = 0; i < m - 2; ++i)
                if (nb[i] == static_cast<int>(j + 1)) {
                    basic = true;
                    break;
                }
            if (basic)
                continue;
            double delta = 0.0;
            if (ne == 1 || ne == 3) {
                for (std::size_t i = 0; i < m; ++i)
                    delta += u[m * (i + 1) - 1] * a[i + m * j];
            } else {
                for (std::size_t i = 0; i < m; ++i)
                    delta += u[(m - 2) + m * i] * a[i + m * j];
            }
            if (!std::isfinite(delta))
                return stopped(StopReason::non_finite_arithmetic,
                               "MODIF entering scan became nonfinite");
            if (ne == 3 && std::abs(delta) >= request.epsilon) {
                continue;
            } else if (ne == 3) {
                double second = 0.0;
                for (std::size_t i = 0; i < m; ++i)
                    second += u[(m - 2) + m * i] * a[i + m * j];
                if (!std::isfinite(second))
                    return stopped(StopReason::non_finite_arithmetic,
                                   "MODIF phase scan became nonfinite");
                delta = second;
            }
            if (delta < minimum) {
                minimum = delta;
                k = j;
            }
        }

        if (!std::isfinite(minimum))
            return stopped(StopReason::non_finite_arithmetic,
                           "MODIF entering scan became nonfinite");
        if (minimum >= -request.epsilon) {
            if (ne > 1) {
                if (p != 1)
                    x[m - 2] = -x[m - 2];
                p = 1;
                break;
            }
            ne = 2;
            record_phase(ne);
            for (std::size_t i = 0; i < m - 2; ++i)
                if (nb[i] < 0)
                    ne = 3;
            if (ne == 3)
                record_phase(ne);
            if (ne == 3 && x[m - 1] < -request.epsilon) {
                p = 2;
                break;
            }
            continue;
        }

        for (std::size_t i = 0; i < m; ++i) {
            if (auto stop = interruption(limits))
                return *stop;
            double delta = 0.0;
            for (std::size_t j = 0; j < m; ++j)
                delta += u[i + m * j] * a[j + m * k];
            if (!std::isfinite(delta))
                return stopped(StopReason::non_finite_arithmetic,
                               "MODIF pivot column became nonfinite");
            xk[i] = delta;
        }
        double theta = 1E11;
        std::size_t l = 0;
        for (std::size_t i = 0; i < m - 2; ++i) {
            if (auto stop = interruption(limits))
                return *stop;
            if (xk[i] >= request.epsilon) {
                const double delta = x[i] / xk[i];
                if (!std::isfinite(delta))
                    return stopped(StopReason::non_finite_arithmetic,
                                   "MODIF ratio became nonfinite");
                if (delta < theta) {
                    theta = delta;
                    l = i;
                }
            }
        }
        if (theta == 1E11) {
            p = 3;
            break;
        }
        if (pivots == limits.max_pivots)
            return stopped(StopReason::pivot_limit, "MODIF pivot budget exhausted");

        const double pivot = xk[l];
        for (std::size_t j = 0; j < m - 2; ++j)
            u[l + m * j] /= pivot;
        for (std::size_t i = 0; i < m; ++i) {
            if (auto stop = interruption(limits))
                return *stop;
            if (i == l)
                x[i] = theta;
            else {
                const double delta = xk[i];
                x[i] -= theta * delta;
                for (std::size_t j = 0; j < m - 2; ++j)
                    u[i + m * j] -= u[l + m * j] * delta;
            }
        }
        nb[l] = static_cast<int>(k + 1);
        ++pivots;
        record_pivot({k + 1, l + 1, ne, theta});
        if (!finite(x) || !finite(u) || !finite(xk))
            return stopped(StopReason::non_finite_arithmetic, "MODIF arithmetic became nonfinite");
    }

    return ModifResult{
        p, std::move(x), std::move(nb), pivots, std::move(trace), std::move(phases), truncated};
}

} // namespace

Outcome<ModifResult> modif(const ModifRequest &request, const Limits &limits) {
    return run_modif(request, limits);
}

ModifPort source_modif_port() {
    return {
        "csl.legacy.btulshor.modif.source-v1",
        [](const ModifRequest &request, const Limits &limits) { return modif(request, limits); }};
}

Outcome<KpabepResult> kpabep(std::span<const Vector> points, const ModifPort &modif_port,
                             const Limits &limits) {
    if (points.empty())
        return KpabepResult{};
    const std::size_t n = points.front().size();
    const std::size_t m = points.size();
    if (n == 0 || !modif_port.run || modif_port.id.empty())
        return stopped(StopReason::invalid_input,
                       "KPABEP requires nonempty point dimensions and a named MODIF port");
    for (const auto &point : points) {
        if (auto stop = interruption(limits))
            return *stop;
        if (point.size() != n || !finite(point))
            return stopped(StopReason::invalid_input,
                           "KPABEP points must have one finite shared dimension");
    }
    std::size_t stride{};
    if (!checked_sum(n, 3, stride) ||
        m > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        n > static_cast<std::size_t>(std::numeric_limits<int>::max()))
        return stopped(StopReason::capacity_limit,
                       "KPABEP source dimensions exceed integer indexing");
    std::size_t columns{};
    if (!checked_sum(m, 1, columns))
        return stopped(StopReason::capacity_limit,
                       "KPABEP candidate count overflows its source layout");
    std::size_t cells{};
    if (!checked_product(stride, columns, cells) || cells > limits.max_dense_entries)
        return stopped(StopReason::capacity_limit,
                       "KPABEP working matrix exceeds configured capacity");

    // Pascal's A is private and column-major with n+3 rows. Point identities
    // move with each column; this does not participate in any numeric choice.
    Vector a(cells, 0.0);
    std::vector<std::size_t> ids(m + 1);
    std::iota(ids.begin(), ids.end(), 0);
    for (std::size_t col = 0; col < m; ++col) {
        if (auto stop = interruption(limits))
            return *stop;
        for (std::size_t row = 0; row < n; ++row)
            a[row + stride * col] = points[col][row];
    }
    const auto at = [&](std::size_t row, std::size_t col) -> double & {
        return a[row + stride * col];
    };

    const std::size_t n1 = n, n2 = n + 1, n3 = n + 2;
    Vector k(n, 0.0);
    for (std::size_t j = 0; j < m; ++j) {
        at(n1, j) = 1.0;
        at(n2, j) = 1.0;
        at(n3, j) = 1.0;
        for (std::size_t i = 0; i < n; ++i)
            at(n3, j) += at(i, j);
        at(n3, j) = -at(n3, j);
    }

    std::size_t retained = 0;
    std::size_t j = m;
    std::size_t modif_calls = 0, pivot_count = 0;
    std::vector<KpabepCandidateStep> candidate_trace;
    bool trace_truncated = false;
    auto trace_candidate = [&](std::size_t candidate, int status, std::size_t pivots) {
        if (!limits.capture_trace)
            return;
        if (candidate_trace.size() < limits.max_trace_events)
            candidate_trace.push_back({candidate, status, pivots});
        else
            trace_truncated = true;
    };

    while (j >= 1) {
        if (auto stop = interruption(limits))
            return *stop;
        // Label 1: the source rechecks the column swapped into this position.
        for (;;) {
            for (std::size_t i = 0; i < n; ++i) {
                if (at(i, j - 1) < 0.0) {
                    for (std::size_t ii = 0; ii < j; ++ii) {
                        at(i, ii) = -at(i, ii);
                        at(n3, ii) = at(n3, ii) - 2.0 * at(i, ii);
                    }
                    k[i] = k[i] == 0.0 ? 1.0 : 0.0;
                }
            }

            Vector x(stride, 0.0);
            for (std::size_t i = 0; i < n; ++i)
                x[i] = at(i, j - 1);
            x[n1] = 1.0;
            x[n2] = 0.0;
            x[n3] = at(n3, j - 1);
            Matrix matrix{stride, j - 1, Vector(stride * (j - 1))};
            for (std::size_t row = 0; row < stride; ++row)
                for (std::size_t col = 0; col < j - 1; ++col)
                    matrix.values[row * (j - 1) + col] = at(row, col);
            const ModifRequest request{std::move(matrix), std::move(x), 0.00001, 0};
            auto decision = modif_port.run(request, limits);
            ++modif_calls;
            if (std::holds_alternative<Stopped>(decision))
                return std::get<Stopped>(std::move(decision));
            const auto &outcome = std::get<ModifResult>(decision);
            if ((outcome.original_status != 1 && outcome.original_status != 2 &&
                 outcome.original_status != 3) ||
                outcome.x.size() != stride || outcome.basis.size() != stride ||
                !finite(outcome.x) || outcome.pivots > limits.max_pivots)
                return stopped(StopReason::invalid_dependency_result,
                               "MODIF port returned a malformed result");
            std::size_t next_pivots{};
            if (!checked_sum(pivot_count, outcome.pivots, next_pivots))
                return stopped(StopReason::capacity_limit, "KPABEP pivot counter overflowed");
            pivot_count = next_pivots;
            trace_candidate(ids[j - 1], outcome.original_status, outcome.pivots);
            if (outcome.original_status == 2) {
                ++retained;
                if (j != retained) {
                    for (std::size_t i = 0; i < stride; ++i)
                        std::swap(at(i, j - 1), at(i, retained - 1));
                    std::swap(ids[j - 1], ids[retained - 1]);
                    continue;
                }
                break;
            }
            if (retained == 0 && j == 2)
                retained = 1;
            break;
        }
        if (j <= retained + 1)
            break;
        --j;
    }

    for (std::size_t i = 0; i < n; ++i)
        if (k[i] != 0.0)
            for (std::size_t col = 0; col < retained; ++col)
                at(i, col) = -at(i, col);

    KpabepResult result;
    result.points.reserve(retained);
    result.retained_indices.reserve(retained);
    for (std::size_t col = 0; col < retained; ++col) {
        Vector point(n);
        for (std::size_t row = 0; row < n; ++row)
            point[row] = at(row, col);
        result.points.push_back(std::move(point));
        result.retained_indices.push_back(ids[col]);
    }
    result.modif_calls = modif_calls;
    result.pivots = pivot_count;
    result.candidate_trace = std::move(candidate_trace);
    result.trace_truncated = trace_truncated;
    return result;
}

KpabepPort source_kpabep_port() {
    return {"csl.legacy.btulshor.kpabep.source-v1",
            [](std::span<const Vector> points, const ModifPort &port, const Limits &limits) {
                return kpabep(points, port, limits);
            }};
}

Outcome<ReachResult> reach(const ReachRequest &request, const KpabepPort &kpabep_port,
                           const ModifPort &modif_port, const Limits &limits) {
    const auto n = request.a.rows;
    const auto nr = request.b.cols;
    const auto np = request.control_points.size();
    auto nx = request.initial_points.size();
    std::size_t a_entries{}, b_entries{};
    if (n == 0 || n > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        nr > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        nx > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        np > static_cast<std::size_t>(std::numeric_limits<int>::max()) || request.a.cols != n ||
        request.b.rows != n || !checked_product(n, n, a_entries) ||
        !checked_product(n, nr, b_entries) || request.a.values.size() != a_entries ||
        request.b.values.size() != b_entries || nr > n || !kpabep_port.run ||
        kpabep_port.id.empty() || !modif_port.run || modif_port.id.empty())
        return stopped(StopReason::invalid_input,
                       "REACH dimensions, ports, or literal BEP stride are invalid");
    for (const auto &point : request.initial_points)
        if (point.size() != n || !finite(point))
            return stopped(StopReason::invalid_input,
                           "REACH initial points have invalid coordinates");
    for (const auto &point : request.control_points)
        if (point.size() != nr || !finite(point))
            return stopped(StopReason::invalid_input,
                           "REACH control points have invalid coordinates");
    if (!finite(request.a.values) || !finite(request.b.values))
        return stopped(StopReason::invalid_input, "REACH matrices must be finite");

    std::size_t initial_count{}, control_count{};
    if (!checked_product(n, nx, initial_count) || !checked_product(n, np, control_count) ||
        initial_count > limits.max_dense_entries || control_count > limits.max_dense_entries)
        return stopped(StopReason::capacity_limit,
                       "REACH working arrays exceed configured capacity");

    // Pascal BEP has n rows and n stride even when B has only nr columns.
    Vector bep(n * np, 0.0), berg(n * nx, 0.0);
    for (std::size_t point = 0; point < np; ++point) {
        for (std::size_t row = 0; row < n; ++row) {
            double sum = 0.0;
            for (std::size_t col = 0; col < nr; ++col)
                sum += request.b.values[row * nr + col] * request.control_points[point][col];
            if (!std::isfinite(sum))
                return stopped(StopReason::non_finite_arithmetic,
                               "REACH control transform became nonfinite");
            bep[row + n * point] = sum;
        }
    }
    for (std::size_t point = 0; point < nx; ++point) {
        for (std::size_t row = 0; row < n; ++row) {
            double sum = 0.0;
            for (std::size_t col = 0; col < n; ++col)
                sum += request.a.values[row * n + col] * request.initial_points[point][col];
            if (!std::isfinite(sum))
                return stopped(StopReason::non_finite_arithmetic,
                               "REACH initial transform became nonfinite");
            berg[row + n * point] = sum;
        }
    }

    ReachResult result;
    std::vector<std::size_t> initial_ids(nx);
    std::iota(initial_ids.begin(), initial_ids.end(), 0);
    if (nx > 2) {
        std::vector<Vector> transformed;
        transformed.reserve(nx);
        for (std::size_t point = 0; point < nx; ++point) {
            Vector value(n);
            for (std::size_t row = 0; row < n; ++row)
                value[row] = berg[row + n * point];
            transformed.push_back(std::move(value));
        }
        auto filtered = kpabep_port.run(transformed, modif_port, limits);
        ++result.kpabep_calls;
        if (std::holds_alternative<Stopped>(filtered))
            return std::get<Stopped>(std::move(filtered));
        const auto &output = std::get<KpabepResult>(filtered);
        if (!valid_selection(transformed, output, n))
            return stopped(StopReason::invalid_dependency_result,
                           "KPABEP port returned malformed points");
        std::size_t next_modif_calls{}, next_pivots{}, filtered_entries{};
        if (!checked_sum(result.modif_calls, output.modif_calls, next_modif_calls) ||
            !checked_sum(result.pivots, output.pivots, next_pivots))
            return stopped(StopReason::capacity_limit, "REACH dependency counters overflowed");
        result.modif_calls = next_modif_calls;
        result.pivots = next_pivots;
        nx = output.points.size();
        if (!checked_product(n, nx, filtered_entries) ||
            filtered_entries > limits.max_dense_entries)
            return stopped(StopReason::capacity_limit,
                           "REACH filtered vertices exceed configured capacity");
        initial_ids = output.retained_indices;
        berg.assign(filtered_entries, 0.0);
        for (std::size_t point = 0; point < nx; ++point)
            for (std::size_t row = 0; row < n; ++row)
                berg[row + n * point] = output.points[point][row];
    }

    std::size_t reach_count{}, reach_entries{};
    if (!checked_product(nx, np, reach_count) || reach_count > limits.max_dense_entries ||
        !checked_product(n, reach_count, reach_entries) || reach_entries > limits.max_dense_entries)
        return stopped(StopReason::capacity_limit,
                       "REACH translated vertices exceed configured capacity");
    berg.resize(reach_entries);
    const std::size_t working_nx = nx;
    for (std::size_t control = 0; control < np; ++control) {
        const std::size_t base = control + 1 == np ? 0 : (control + 1) * working_nx;
        for (std::size_t point = 0; point < working_nx; ++point)
            for (std::size_t row = 0; row < n; ++row) {
                const double sum = berg[row + n * point] + bep[row + n * control];
                if (!std::isfinite(sum))
                    return stopped(StopReason::non_finite_arithmetic,
                                   "REACH translation became nonfinite");
                berg[row + n * (base + point)] = sum;
            }
    }
    result.points.reserve(reach_count);
    result.source_vertices.reserve(reach_count);
    for (std::size_t index = 0; index < reach_count; ++index) {
        const std::size_t block = index / working_nx;
        const std::size_t point = index % working_nx;
        const std::size_t control = block == 0 ? np - 1 : block - 1;
        Vector value(n);
        for (std::size_t row = 0; row < n; ++row)
            value[row] = berg[row + n * index];
        result.points.push_back(std::move(value));
        result.source_vertices.push_back({initial_ids[point], control});
    }
    if (reach_count > 2) {
        auto filtered = kpabep_port.run(result.points, modif_port, limits);
        ++result.kpabep_calls;
        if (std::holds_alternative<Stopped>(filtered))
            return std::get<Stopped>(std::move(filtered));
        const auto &output = std::get<KpabepResult>(filtered);
        if (!valid_selection(result.points, output, n))
            return stopped(StopReason::invalid_dependency_result,
                           "KPABEP port returned malformed points");
        std::size_t next_modif_calls{}, next_pivots{}, filtered_entries{};
        if (!checked_sum(result.modif_calls, output.modif_calls, next_modif_calls) ||
            !checked_sum(result.pivots, output.pivots, next_pivots) ||
            !checked_product(n, output.points.size(), filtered_entries) ||
            filtered_entries > limits.max_dense_entries)
            return stopped(StopReason::capacity_limit,
                           "REACH filtered result exceeds configured bounds");
        result.modif_calls = next_modif_calls;
        result.pivots = next_pivots;
        result.points = output.points;
        result.source_vertices.clear();
        for (auto index : output.retained_indices) {
            const auto block = index / working_nx;
            const auto control = block == 0 ? np - 1 : block - 1;
            result.source_vertices.push_back({initial_ids[index % working_nx], control});
        }
    }
    return result;
}

} // namespace csl::geometry::legacy_btulshor
