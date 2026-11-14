#include <csl/reachability/fixed_tail_policy.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace csl::reachability {
namespace {
constexpr double inf = std::numeric_limits<double>::infinity();
struct Rejected {
    Diagnostic error;
};
Diagnostic invalid(std::string text) {
    return {DiagnosticCode::invalid_input, "fixed_tail", std::move(text)};
}
template <class T, class... E> T take(std::variant<T, E...> result) {
    if (auto *value = std::get_if<T>(&result))
        return std::move(*value);
    std::string reason = "native fixed-tail preparation failed";
    std::visit(
        [&](const auto &value) {
            using V = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<V, Diagnostic>)
                reason = value.field + ": " + value.explanation;
            if constexpr (std::is_same_v<V, Diagnostics>)
                if (!value.empty())
                    reason = value[0].field + ": " + value[0].explanation;
            if constexpr (std::is_same_v<V, OperationStopped>)
                reason = value.diagnostics;
        },
        result);
    throw Rejected{invalid(std::move(reason))};
}
bool finite_values(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(),
                       [](double value) { return std::isfinite(value); });
}
constexpr double log_exp_initial_readback_roundoff_units = 64;
bool initial_readback_matches(std::span<const double> expected, std::span<const double> actual,
                              std::span<const std::size_t> positive_coordinates = {}) {
    for (std::size_t i = 0; i < expected.size(); ++i) {
        if (expected[i] == actual[i])
            continue;
        if (std::find(positive_coordinates.begin(), positive_coordinates.end(), i) ==
                positive_coordinates.end() ||
            expected[i] <= 0 || actual[i] <= 0)
            return false;
        const auto allowance =
            log_exp_initial_readback_roundoff_units * std::numeric_limits<double>::epsilon() *
                (1 + std::abs(std::log(expected[i]))) * std::abs(expected[i]) +
            log_exp_initial_readback_roundoff_units * std::numeric_limits<double>::denorm_min();
        if (std::abs(expected[i] - actual[i]) > allowance)
            return false;
    }
    return true;
}
bool matrix_shape(const Matrix &A, std::size_t rows, std::size_t cols) {
    return (!rows || cols <= std::numeric_limits<std::size_t>::max() / rows) && A.rows == rows &&
           A.cols == cols && A.values.size() == rows * cols && finite_values(A.values);
}
bool row_shape(const FixedTailHRows &h, std::size_t dimension) {
    return matrix_shape(h.inequalities, h.upper_bounds.size(), dimension) &&
           matrix_shape(h.equalities, h.equality_values.size(), dimension) &&
           finite_values(h.upper_bounds) && finite_values(h.equality_values);
}
std::size_t history_size(const JointCoordinates &coordinates) {
    const auto n = coordinates.dimensions.state, m = coordinates.dimensions.control,
               T = coordinates.horizon;
    const auto maximum = std::numeric_limits<std::size_t>::max();
    if (!n || coordinates.dimensions.external != 0 || T == maximum || n > maximum / (T + 1) ||
        (T && m > (maximum - (T + 1) * n) / T))
        throw Rejected{invalid("canonical history dimensions are invalid or overflow")};
    return (T + 1) * n + T * m;
}
Matrix identity(std::size_t n) {
    Matrix out{n, n, Vector(n * n, 0)};
    for (std::size_t i = 0; i < n; ++i)
        out.values[i * n + i] = 1;
    return out;
}
Matrix copy(numeric::MatrixView A) {
    Matrix out{A.rows(), A.cols(), {}};
    for (std::size_t i = 0; i < A.rows(); ++i)
        for (std::size_t j = 0; j < A.cols(); ++j)
            out.values.push_back(A(i, j));
    return out;
}
Vector copy(numeric::VectorView v) { return Vector(v.values().begin(), v.values().end()); }
Vector image(const Matrix &A, std::span<const double> x, const Vector &c = {}) {
    if (A.cols != x.size())
        throw Rejected{invalid("affine image dimension differs")};
    Vector out = c.empty() ? Vector(A.rows, 0) : c;
    for (std::size_t i = 0; i < A.rows; ++i)
        for (std::size_t j = 0; j < A.cols; ++j)
            out[i] += A.values[i * A.cols + j] * x[j];
    if (!std::all_of(out.begin(), out.end(), [](double v) { return std::isfinite(v); }))
        throw Rejected{invalid("affine history overflowed")};
    return out;
}
Matrix multiply(const Matrix &A, const Matrix &B) {
    if (A.cols != B.rows)
        throw Rejected{invalid("affine maps have incompatible dimensions")};
    Matrix out{A.rows, B.cols, Vector(A.rows * B.cols, 0)};
    for (std::size_t i = 0; i < A.rows; ++i)
        for (std::size_t j = 0; j < B.cols; ++j)
            for (std::size_t k = 0; k < A.cols; ++k)
                out.values[i * B.cols + j] += A.values[i * A.cols + k] * B.values[k * B.cols + j];
    if (!std::all_of(out.values.begin(), out.values.end(),
                     [](double v) { return std::isfinite(v); }))
        throw Rejected{invalid("affine map overflowed")};
    return out;
}
FixedTailHRows empty_rows(std::size_t n) { return {{0, n, {}}, {}, {0, n, {}}, {}}; }
void append(FixedTailHRows &out, Vector row, double bound, bool equality = false) {
    if (row.size() != out.inequalities.cols || !std::isfinite(bound))
        throw Rejected{invalid("nonfinite or malformed H row")};
    auto &A = equality ? out.equalities : out.inequalities;
    auto &b = equality ? out.equality_values : out.upper_bounds;
    ++A.rows;
    A.values.insert(A.values.end(), row.begin(), row.end());
    b.push_back(bound);
}
FixedTailHRows rows(const sets::SetData &set) {
    const auto n = set.metadata()->set.dimension;
    auto out = empty_rows(n);
    const auto data = set.representation();
    if (const auto *h = std::get_if<sets::HRepresentation>(&data))
        return {copy(h->inequalities), copy(h->upper_bounds), copy(h->equalities),
                copy(h->equality_values)};
    if (const auto *point = std::get_if<sets::SingletonRepresentation>(&data)) {
        for (std::size_t j = 0; j < n; ++j) {
            Vector row(n, 0);
            row[j] = 1;
            append(out, std::move(row), point->point[j], true);
        }
    } else if (std::holds_alternative<sets::EmptyRepresentation>(data))
        append(out, Vector(n, 0), -1);
    else if (!std::holds_alternative<sets::UniversalRepresentation>(data))
        throw Rejected{invalid("native H, point or universal domains required")};
    return out;
}
FixedTailHRows rows(const AdmissibleSet &set, std::size_t n) {
    return std::visit(
        [&](const auto &value) -> FixedTailHRows {
            using T = std::decay_t<decltype(value)>;
            if constexpr (std::is_same_v<T, SetHandle>)
                return rows(take(sets::from_handle(value)));
            auto out = empty_rows(n);
            if constexpr (std::is_same_v<T, EmptySet>)
                append(out, Vector(n, 0), -1);
            if constexpr (std::is_same_v<T, Singleton>)
                for (std::size_t j = 0; j < n; ++j) {
                    Vector row(n, 0);
                    row[j] = 1;
                    append(out, std::move(row), value.point[j], true);
                }
            return out;
        },
        set);
}
std::vector<Interval> axis_bounds(const FixedTailHRows &h, bool require_finite = true) {
    std::vector<Interval> bounds(h.inequalities.cols);
    const auto scan = [&](const Matrix &A, const Vector &b, bool equality) {
        for (std::size_t i = 0; i < A.rows; ++i) {
            std::size_t index = 0, count = 0;
            for (std::size_t j = 0; j < A.cols; ++j)
                if (A.values[i * A.cols + j] != 0) {
                    index = j;
                    ++count;
                }
            if (count != 1)
                continue;
            const auto a = A.values[i * A.cols + index];
            const auto value = b[i] / a;
            const bool exact = b[i] == 0 || a == 1 || a == -1;
            const auto lower = exact ? value : std::nextafter(value, -inf);
            const auto upper = exact ? value : std::nextafter(value, inf);
            auto &interval = bounds[index];
            if (a > 0 || equality)
                interval.upper = std::min(interval.upper.value_or(inf), upper);
            if (a < 0 || equality)
                interval.lower = std::max(interval.lower.value_or(-inf), lower);
        }
    };
    scan(h.inequalities, h.upper_bounds, false);
    scan(h.equalities, h.equality_values, true);
    for (const auto &b : bounds)
        if (require_finite && (!b.lower || !b.upper || !std::isfinite(*b.lower) ||
                               !std::isfinite(*b.upper) || *b.lower > *b.upper))
            throw Rejected{
                {DiagnosticCode::unsupported, "fixed_tail.input_carrier",
                 "Finite explicit source input bounds required; arbitrary bounded H support can use the support-provider extension."}};
    return bounds;
}
std::vector<FixedTailCommandAdjustment>
recover_authored_command_bounds(const FixedTailHRows &domain, Vector &control, StageIndex stage) {
    std::vector<FixedTailCommandAdjustment> adjustments;
    const auto scan = [&](const Matrix &A, const Vector &b, bool equality) {
        for (std::size_t row = 0; row < A.rows; ++row) {
            std::size_t axis = 0, count = 0;
            for (std::size_t j = 0; j < A.cols; ++j)
                if (A.values[row * A.cols + j] != 0) {
                    axis = j;
                    ++count;
                }
            if (count != 1)
                continue;
            const auto coefficient = A.values[row * A.cols + axis];
            if (coefficient != 1 && coefficient != -1)
                continue;
            const auto bound = coefficient == 1 ? b[row] : -b[row];
            const bool upper = coefficient == 1;
            const auto raw = control[axis];
            if ((upper && raw <= bound && !equality) || (!upper && raw >= bound && !equality) ||
                raw == bound)
                continue;
            const auto allowed = fixed_tail_command_recovery_tolerance.absolute_tolerance +
                                 fixed_tail_command_recovery_tolerance.relative_tolerance *
                                     std::max(std::abs(raw), std::abs(bound));
            if (std::abs(raw - bound) > allowed)
                throw Rejected{invalid(
                    "optimizer command materially violates an authored literal unit-axis bound")};
            control[axis] = bound;
            adjustments.push_back(
                {stage, axis,
                 raw < bound ? FixedTailCommandBoundSide::lower : FixedTailCommandBoundSide::upper,
                 raw, bound, bound, allowed});
        }
    };
    scan(domain.inequalities, domain.upper_bounds, false);
    scan(domain.equalities, domain.equality_values, true);
    return adjustments;
}
std::vector<FixedTailCommandAdjustment> recover_anchor_commands(const FixedTailModel &model,
                                                                Vector &history) {
    const auto n = model.observed.size(), T = model.stages.size(),
               m = model.source_cost.coordinates.dimensions.control;
    std::vector<FixedTailCommandAdjustment> adjustments;
    for (std::size_t k = 0; k < T; ++k) {
        const auto begin = history.begin() + static_cast<std::ptrdiff_t>((T + 1) * n + k * m);
        Vector control(begin, begin + static_cast<std::ptrdiff_t>(m));
        auto recovered = recover_authored_command_bounds(model.control_domains[k], control, {k});
        std::copy(control.begin(), control.end(), begin);
        adjustments.insert(adjustments.end(), recovered.begin(), recovered.end());
    }
    return adjustments;
}
bool admitted(const FixedTailHRows &h, std::span<const double> value) {
    const auto check = [&](const Matrix &A, const Vector &b, bool equality) {
        auto x = image(A, value);
        for (std::size_t i = 0; i < x.size(); ++i) {
            const double residual = equality ? std::abs(x[i] - b[i]) : std::max(0.0, x[i] - b[i]);
            if (residual > 1e-7 + 1e-8 * std::max(std::abs(x[i]), std::abs(b[i])))
                return false;
        }
        return true;
    };
    return check(h.inequalities, h.upper_bounds, false) &&
           check(h.equalities, h.equality_values, true);
}
void pull_rows(FixedTailHRows &out, const FixedTailHRows &source, const Matrix &C,
               const Vector &d) {
    const auto pull = [&](const Matrix &A, const Vector &b, bool equality) {
        const auto AC = multiply(A, C);
        const auto Ad = image(A, d);
        for (std::size_t i = 0; i < A.rows; ++i) {
            Vector row(AC.values.begin() + static_cast<std::ptrdiff_t>(i * AC.cols),
                       AC.values.begin() + static_cast<std::ptrdiff_t>((i + 1) * AC.cols));
            append(out, std::move(row), b[i] - Ad[i], equality);
        }
    };
    pull(source.inequalities, source.upper_bounds, false);
    pull(source.equalities, source.equality_values, true);
}
double rounded_sum(double a, double b, bool upper) {
    if (a == 0)
        return b;
    if (b == 0)
        return a;
    if (a == -b)
        return 0;
    return std::nextafter(a + b, upper ? inf : -inf);
}
double rounded_product(double a, double b, bool upper) {
    if (a == 0 || b == 0)
        return 0;
    if (a == 1)
        return b;
    if (a == -1)
        return -b;
    if (b == 1)
        return a;
    if (b == -1)
        return -a;
    return std::nextafter(a * b, upper ? inf : -inf);
}
std::pair<Vector, Vector> interval_image(const Matrix &A, const Vector &lo, const Vector &hi,
                                         const Vector &c) {
    Vector lower = c, upper = c;
    for (std::size_t i = 0; i < A.rows; ++i)
        for (std::size_t j = 0; j < A.cols; ++j) {
            const double a = A.values[i * A.cols + j];
            if (a == 0)
                continue;
            const double l = rounded_product(a, a > 0 ? lo[j] : hi[j], false);
            const double u = rounded_product(a, a > 0 ? hi[j] : lo[j], true);
            lower[i] = rounded_sum(lower[i], l, false);
            upper[i] = rounded_sum(upper[i], u, true);
        }
    if (!std::all_of(lower.begin(), lower.end(), [](double v) { return std::isfinite(v); }) ||
        !std::all_of(upper.begin(), upper.end(), [](double v) { return std::isfinite(v); }))
        throw Rejected{invalid("derived carrier overflowed")};
    return {std::move(lower), std::move(upper)};
}
std::vector<std::pair<Vector, Vector>> carriers(const FixedTailModel &model) {
    std::vector<std::pair<Vector, Vector>> out{{model.observed, model.observed}};
    const auto n = model.observed.size();
    for (std::size_t k = 0; k < model.stages.size(); ++k) {
        Vector ulo, uhi;
        for (const auto &b : model.input_carriers[k]) {
            ulo.push_back(*b.lower);
            uhi.push_back(*b.upper);
        }
        auto [lo, hi] = interval_image(model.stages[k].A, out.back().first, out.back().second,
                                       model.stages[k].offset);
        const auto [left, right] = interval_image(model.stages[k].B, ulo, uhi, Vector(n, 0));
        for (std::size_t i = 0; i < n; ++i) {
            lo[i] = rounded_sum(lo[i], left[i], false);
            hi[i] = rounded_sum(hi[i], right[i], true);
        }
        out.emplace_back(std::move(lo), std::move(hi));
    }
    return out;
}
Matrix directions(FixedTailFamily family, const Vector &widths) {
    const auto n = widths.size();
    if (family == FixedTailFamily::polytope)
        return {n, 0, {}};
    const auto columns = family == FixedTailFamily::zonotope ? 2 * n : n;
    Matrix out{n, columns, Vector(n * columns, 0)};
    if (family == FixedTailFamily::box || family == FixedTailFamily::ellipsoid)
        for (std::size_t i = 0; i < n; ++i)
            out.values[i * columns + i] = widths[i];
    else {
        auto R = identity(n);
        for (std::size_t j = 0; j + 1 < n; j += 2) {
            const auto v = 1 / std::sqrt(2.0);
            R.values[j * n + j] = v;
            R.values[j * n + j + 1] = -v;
            R.values[(j + 1) * n + j] = v;
            R.values[(j + 1) * n + j + 1] = v;
        }
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) {
                if (family == FixedTailFamily::parallelotope)
                    out.values[i * columns + j] = widths[i] * R.values[i * n + j];
                else {
                    out.values[i * columns + j] = i == j ? widths[i] / 2 : 0;
                    out.values[i * columns + n + j] = widths[i] * R.values[i * n + j] / 2;
                }
            }
    }
    return out;
}
void check_model(const FixedTailModel &model) {
    const auto n = model.observed.size(), T = model.stages.size(),
               m = model.source_cost.coordinates.dimensions.control;
    const auto &coordinates = model.source_cost.coordinates;
    if (!n || !m || !T || coordinates.horizon != T || coordinates.dimensions.state != n ||
        coordinates.dimensions.external != 0 || model.state_domains.size() != T + 1 ||
        model.control_domains.size() != T || model.input_carriers.size() != T ||
        !std::all_of(model.observed.begin(), model.observed.end(),
                     [](double v) { return std::isfinite(v); }))
        throw Rejected{invalid("source model, cost and domain dimensions differ")};
    const auto maximum = std::numeric_limits<std::size_t>::max();
    if (T == maximum || n > maximum / (T + 1) || m > (maximum - (T + 1) * n) / T)
        throw Rejected{invalid("source history dimensions overflow")};
    const auto N = (T + 1) * n + T * m;
    if (model.source_cost.quadratic.dimension != N || model.full_history.inequalities.cols != N ||
        model.full_history.equalities.cols != N)
        throw Rejected{invalid("source history and cost coordinates differ")};
    const auto shape = [](const Matrix &A, std::size_t rows, std::size_t cols) {
        return (!rows || cols <= std::numeric_limits<std::size_t>::max() / rows) &&
               A.rows == rows && A.cols == cols && A.values.size() == rows * cols &&
               std::all_of(A.values.begin(), A.values.end(),
                           [](double v) { return std::isfinite(v); });
    };
    for (const auto &stage : model.stages)
        if (!shape(stage.A, n, n) || !shape(stage.B, n, m) || stage.offset.size() != n ||
            !std::all_of(stage.offset.begin(), stage.offset.end(),
                         [](double v) { return std::isfinite(v); }))
            throw Rejected{invalid("source predictor dimensions differ")};
    const auto domain_shape = [&](const FixedTailHRows &h, std::size_t count) {
        return shape(h.inequalities, h.upper_bounds.size(), count) &&
               shape(h.equalities, h.equality_values.size(), count) &&
               std::all_of(h.upper_bounds.begin(), h.upper_bounds.end(),
                           [](double v) { return std::isfinite(v); }) &&
               std::all_of(h.equality_values.begin(), h.equality_values.end(),
                           [](double v) { return std::isfinite(v); });
    };
    if (!domain_shape(model.full_history, N) || !shape(model.source_cost.quadratic.Q, N, N) ||
        model.source_cost.quadratic.linear.size() != N)
        throw Rejected{invalid("source H rows or polynomial dimensions differ")};
    for (const auto &h : model.state_domains)
        if (!domain_shape(h, n))
            throw Rejected{invalid("state H dimensions differ")};
    for (const auto &h : model.control_domains)
        if (!domain_shape(h, m))
            throw Rejected{invalid("control H dimensions differ")};
    for (const auto &stage : model.input_carriers) {
        if (stage.size() != m)
            throw Rejected{invalid("input carrier dimensions differ")};
        for (const auto &b : stage)
            if (!b.lower || !b.upper || !std::isfinite(*b.lower) || !std::isfinite(*b.upper) ||
                *b.lower > *b.upper)
                throw Rejected{invalid("input carrier must be finite")};
    }
}
std::optional<OperationStopped> stopped(const ExecutionContext &c) {
    if (c.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Fixed-tail policy cancelled"};
    if (c.deadline && std::chrono::steady_clock::now() >= *c.deadline)
        return OperationStopped{StopReason::deadline_expired, "Fixed-tail policy deadline expired"};
    return {};
}
FixedTailRegion region(const FixedTailModel &model, const Vector &anchor, std::size_t j,
                       FixedTailFamily family, const std::pair<Vector, Vector> &carrier,
                       const std::vector<std::size_t> &strict) {
    const auto n = model.observed.size();
    auto tail = take(fixed_tail_state_lift(model, anchor, {j}));
    FixedTailHRows h = empty_rows(n);
    std::vector<Vector> margins;
    Vector center(anchor.begin() + static_cast<std::ptrdiff_t>(j * n),
                  anchor.begin() + static_cast<std::ptrdiff_t>((j + 1) * n));
    for (std::size_t k = j; k <= model.stages.size(); ++k) {
        const auto &C = tail.maps[k - j];
        const auto &d = tail.offsets[k - j];
        pull_rows(h, model.state_domains[k], C, d);
        Vector stage_margins;
        const auto x = image(C, center, d);
        for (const auto axis : strict) {
            if (axis >= n || x[axis] <= 0 || !std::isfinite(x[axis] / 2) || x[axis] / 2 <= 0)
                throw Rejected{invalid("no positive strict-domain anchor margin")};
            Vector row(n, 0);
            for (std::size_t i = 0; i < n; ++i)
                row[i] = -C.values[axis * n + i];
            append(h, std::move(row), d[axis] - x[axis] / 2);
            stage_margins.push_back(x[axis] / 2);
        }
        margins.push_back(std::move(stage_margins));
    }
    Vector widths(n, 0);
    for (std::size_t i = 0; i < n; ++i) {
        Vector row(n, 0);
        row[i] = 1;
        append(h, row, carrier.second[i]);
        row[i] = -1;
        append(h, std::move(row), -carrier.first[i]);
        widths[i] = (carrier.second[i] - carrier.first[i]) / 2;
    }
    auto G = directions(family, widths);
    InnerTemplateInput input{center,
                             std::move(G),
                             family == FixedTailFamily::ellipsoid
                                 ? InnerTemplateNorm::euclidean_ball
                                 : InnerTemplateNorm::independent_intervals,
                             h.inequalities,
                             h.upper_bounds,
                             h.equalities,
                             h.equality_values};
    auto admitted_inner = take(inscribe_template(input));
    return {{j},
            family,
            std::move(h),
            family == FixedTailFamily::polytope
                ? std::nullopt
                : std::optional<InnerTemplate>{std::move(admitted_inner)},
            std::move(tail),
            carrier.first,
            carrier.second,
            strict,
            std::move(margins)};
}
}

Diagnostics check_full_history_lift(const FullHistoryLift &lift, std::size_t primary_dimension) {
    try {
        const auto dimension = history_size(lift.coordinates);
        if (!matrix_shape(lift.map, dimension, primary_dimension) ||
            lift.offset.size() != dimension || !finite_values(lift.offset))
            return {invalid(
                "history lift requires finite dimension-matched matrix storage and offset")};
        return {};
    } catch (const Rejected &error) {
        return {error.error};
    }
}
Diagnostics check_fixed_tail_solve_request(const FixedTailSolveRequest &request) {
    auto errors = check_full_history_lift(request.lift, request.initial_primary.size());
    if (!errors.empty())
        return errors;
    const auto dimension = request.lift.offset.size();
    const auto n = request.lift.coordinates.dimensions.state;
    const auto horizon = request.lift.coordinates.horizon;
    const auto &cost = request.source_cost;
    const auto &c = cost.coordinates;
    if (request.identity.problem.value.empty() || request.identity.program.value.empty() ||
        request.initial_primary.empty() || !finite_values(request.initial_primary) ||
        c.horizon != horizon || c.dimensions.state != n ||
        c.dimensions.control != request.lift.coordinates.dimensions.control ||
        c.dimensions.external != 0)
        return {invalid("optimizer identity, initialization or source cost coordinates differ")};
    if (!row_shape(request.domain, dimension))
        return {invalid("optimizer H rows require finite complete matrix and bound storage")};
    const auto &q = cost.quadratic;
    if (q.dimension != dimension || !matrix_shape(q.Q, dimension, dimension) ||
        q.linear.size() != dimension || !finite_values(q.linear) || !std::isfinite(q.offset))
        return {invalid("optimizer quadratic storage is malformed or nonfinite")};
    for (const auto &term : cost.residual_norms) {
        if (!matrix_shape(term.map, term.target.size(), dimension) ||
            term.weights.size() != term.target.size() || !finite_values(term.target) ||
            !finite_values(term.weights) ||
            std::any_of(term.weights.begin(), term.weights.end(),
                        [](double value) { return value < 0; }) ||
            !std::isfinite(term.coefficient) || term.coefficient < 0)
            return {invalid("optimizer residual norm storage or weights are malformed")};
    }
    if (request.feasibility_only) {
        if (request.lift.map.cols != dimension || !request.regions.empty())
            return {invalid("feasibility requires the unrestricted canonical base history")};
        for (std::size_t i = 0; i < dimension; ++i) {
            if (request.lift.offset[i] != 0)
                return {invalid("feasibility base-history lift must be identity")};
            for (std::size_t j = 0; j < dimension; ++j)
                if (request.lift.map.values[i * dimension + j] != (i == j ? 1.0 : 0.0))
                    return {invalid("feasibility base-history lift must be identity")};
        }
    } else {
        if (!request.strictly_positive_history_coordinates.empty() ||
            request.lift.map.cols != c.dimensions.control)
            return {invalid(
                "reduced solve frees only the current action and uses explicit inner strict-domain margins")};
        for (std::size_t i = 0; i < n * request.lift.map.cols; ++i)
            if (request.lift.map.values[i] != 0)
                return {invalid("reduced history lift must keep the observed initial state fixed")};
    }
    for (const auto index : request.strictly_positive_history_coordinates)
        if (index >= dimension || request.initial_primary[index] <= 0)
            return {invalid("positive history initialization is invalid")};
    for (const auto &region : request.regions) {
        if (region.stage.value > horizon || !row_shape(region.reference, n))
            return {invalid("region stage or H storage is malformed")};
        switch (region.family) {
        case FixedTailFamily::polytope:
            if (region.inner)
                return {invalid("polytope membership must retain its original H reference")};
            break;
        case FixedTailFamily::box:
        case FixedTailFamily::parallelotope:
        case FixedTailFamily::zonotope:
        case FixedTailFamily::ellipsoid: {
            if (!region.inner)
                return {invalid("selected physical family is missing its inner factor")};
            const auto &set = *region.inner;
            const auto expected = region.family == FixedTailFamily::ellipsoid
                                      ? InnerTemplateNorm::euclidean_ball
                                      : InnerTemplateNorm::independent_intervals;
            if (set.center.size() != n || !finite_values(set.center) ||
                !matrix_shape(set.factor, n, set.factor.cols) || set.norm != expected ||
                !std::isfinite(set.radius) || set.radius < 0 ||
                set.point != std::all_of(
                                 set.factor.values.begin(), set.factor.values.end(),
                                 [](double value) { return value == 0; }))
                return {invalid("physical inner factor storage, norm or point claim is malformed")};
            break;
        }
        default:
            return {invalid("unknown physical inner family")};
        }
    }
    return {};
}

FixedTailModelResult prepare_fixed_tail(const problem::ResolvedProblem &source,
                                        const optimization::RunningControlCost &running,
                                        std::size_t offset) {
    try {
        const auto p = source.description();
        const auto dims = source.model().dimensions();
        const auto horizon = source.model().horizon();
        if (dims.external != 0 || !dims.state || !dims.control || !horizon ||
            p->information != InformationPattern::nominal_open_loop ||
            p->model->dynamics.time_domain != TimeDomain::discrete ||
            (p->temporal && p->temporal->joint_map.rows))
            throw Rejected{invalid(
                "discrete known-state continuous nominal source without temporal coupling required")};
        const auto *initial = std::get_if<KnownInitial>(&p->initial);
        const auto *controls = std::get_if<ContinuousDomain>(&p->controls);
        if (!initial || !controls)
            throw Rejected{invalid("known initial point and continuous controls required")};
        auto terminal = take(sets::make_universal(
            {{source.identity().value + "/fixed-tail-universal"}, dims.state, {}}));
        auto full = take(synthesis::recover_joint_history(source, terminal));
        auto cost = take(optimization::compile_history_cost(full, p->objective, running, offset));
        FixedTailModel out{source.identity(), {}, initial->point, {}, {}, {}, rows(full.relation),
                           std::move(cost)};
        for (std::size_t k = 0; k < horizon; ++k) {
            const auto stage = take(source.model().stage({k}));
            out.stages.push_back({copy(stage.A), copy(stage.B), copy(stage.E), copy(stage.offset)});
            out.control_domains.push_back(rows(controls->stages[k], dims.control));
            out.input_carriers.push_back(axis_bounds(out.control_domains.back()));
        }
        for (const auto &state : p->states)
            out.state_domains.push_back(rows(state, dims.state));
        return out;
    } catch (const Rejected &e) {
        return e.error;
    }
}
HistoryLiftResult fixed_control_tail_lift(const FixedTailModel &model,
                                          std::span<const double> anchor) {
    try {
        check_model(model);
        const auto n = model.observed.size(), horizon = model.stages.size();
        const auto m = model.source_cost.coordinates.dimensions.control;
        const auto dimension = (horizon + 1) * n + horizon * m;
        if (!horizon || anchor.size() != dimension)
            throw Rejected{invalid("canonical full anchor history required")};
        FullHistoryLift out{model.source_cost.coordinates,
                            {dimension, m, Vector(dimension * m, 0)},
                            Vector(dimension, 0)};
        Matrix C{n, m, Vector(n * m, 0)};
        Vector d = model.observed;
        std::copy(d.begin(), d.end(), out.offset.begin());
        for (std::size_t k = 0; k < horizon; ++k) {
            const auto &stage = model.stages[k];
            C = multiply(stage.A, C);
            d = image(stage.A, d, stage.offset);
            if (k == 0)
                for (std::size_t i = 0; i < C.values.size(); ++i)
                    C.values[i] += stage.B.values[i];
            else {
                const auto u = anchor.subspan((horizon + 1) * n + k * m, m);
                const auto Bu = image(stage.B, u);
                for (std::size_t i = 0; i < n; ++i)
                    d[i] += Bu[i];
            }
            std::copy(C.values.begin(), C.values.end(),
                      out.map.values.begin() + static_cast<std::ptrdiff_t>((k + 1) * n * m));
            std::copy(d.begin(), d.end(),
                      out.offset.begin() + static_cast<std::ptrdiff_t>((k + 1) * n));
        }
        for (std::size_t k = 0; k < horizon; ++k) {
            for (std::size_t j = 0; j < m; ++j) {
                const auto index = (horizon + 1) * n + k * m + j;
                if (k == 0)
                    out.map.values[index * m + j] = 1;
                else
                    out.offset[index] = anchor[index];
            }
        }
        return out;
    } catch (const Rejected &e) {
        return e.error;
    }
}
std::variant<TailStateLift, Diagnostic>
fixed_tail_state_lift(const FixedTailModel &model, std::span<const double> anchor, StageIndex at) {
    try {
        check_model(model);
        const auto n = model.observed.size(), horizon = model.stages.size(),
                   m = model.source_cost.coordinates.dimensions.control;
        if (at.value > horizon || anchor.size() != (horizon + 1) * n + horizon * m)
            throw Rejected{invalid("tail stage or anchor dimension differs")};
        TailStateLift out{at.value, {identity(n)}, {Vector(n, 0)}};
        for (std::size_t k = at.value; k < horizon; ++k) {
            const auto &row = model.stages[k];
            const auto u = anchor.subspan((horizon + 1) * n + k * m, m);
            out.maps.push_back(multiply(row.A, out.maps.back()));
            auto d = image(row.A, out.offsets.back(), row.offset);
            const auto Bu = image(row.B, u);
            for (std::size_t i = 0; i < n; ++i)
                d[i] += Bu[i];
            out.offsets.push_back(std::move(d));
        }
        return out;
    } catch (const Rejected &e) {
        return e.error;
    }
}
std::variant<Vector, Diagnostic> recover_fixed_tail_history(const FullHistoryLift &lift,
                                                            std::span<const double> current) {
    const auto errors = check_full_history_lift(lift, current.size());
    if (!errors.empty())
        return errors.front();
    if (!finite_values(current))
        return invalid("recovered current control must be finite");
    try {
        return image(lift.map, current, lift.offset);
    } catch (const Rejected &e) {
        return e.error;
    }
}
std::variant<FixedTailInitialization, Diagnostic>
initialize_fixed_tail(const FixedTailModel &model,
                      const std::optional<FixedTailWarmHistory> &previous) {
    try {
        check_model(model);
        const auto n = model.observed.size(), T = model.stages.size(),
                   m = model.source_cost.coordinates.dimensions.control;
        if (previous) {
            const auto &p = *previous;
            if (p.absolute_stage == std::numeric_limits<std::size_t>::max() ||
                p.absolute_stage + 1 != model.source_cost.absolute_stage_offset ||
                p.coordinates.horizon != T + 1 ||
                (p.coordinates.dimensions.state != n || p.coordinates.dimensions.control != m ||
                 p.coordinates.dimensions.external != 0) ||
                p.source_objective_id != model.source_cost.running_source.objective_id ||
                p.original_horizon != model.source_cost.running_source.original_horizon ||
                p.history.size() != (T + 2) * n + (T + 1) * m)
                throw Rejected{invalid(
                    "prior accepted source history does not precede this fixed terminal horizon")};
            Vector out(p.history.begin() + static_cast<std::ptrdiff_t>(n),
                       p.history.begin() + static_cast<std::ptrdiff_t>((T + 2) * n));
            std::copy(model.observed.begin(), model.observed.end(), out.begin());
            out.insert(out.end(), p.history.begin() + static_cast<std::ptrdiff_t>((T + 2) * n + m),
                       p.history.end());
            return FixedTailInitialization{
                std::move(out), "shift-prior-primal-drop-applied-stage-no-terminal-repeat",
                p.absolute_stage};
        }
        Vector controls;
        for (const auto &stage : model.input_carriers)
            for (const auto &bound : stage)
                controls.push_back(std::clamp(0.0, *bound.lower, *bound.upper));
        Vector history = model.observed, state = model.observed;
        for (std::size_t k = 0; k < T; ++k) {
            const auto &stage = model.stages[k];
            auto next = image(stage.A, state, stage.offset);
            const auto Bu = image(stage.B, std::span<const double>(controls).subspan(k * m, m));
            for (std::size_t j = 0; j < n; ++j)
                next[j] += Bu[j];
            history.insert(history.end(), next.begin(), next.end());
            state = std::move(next);
        }
        history.insert(history.end(), controls.begin(), controls.end());
        return FixedTailInitialization{std::move(history), "initial-zero-control-rollout", {}};
    } catch (const Rejected &e) {
        return e.error;
    }
}

FixedTailPolicyOutcome
fixed_tail_policy(const FixedTailPolicyRequest &request,
                  const registry::PreparedProvider<registry::FixedTailOptimizerPort> &provider,
                  const ExecutionContext &context) {
    FixedTailPolicyFailure failure{"preparation", invalid("unknown failure"), {}, {}, {}, {}};
    try {
        if (auto stop = stopped(context))
            return *stop;
        const auto &model = request.model;
        check_model(model);
        switch (request.family) {
        case FixedTailFamily::polytope:
        case FixedTailFamily::box:
        case FixedTailFamily::zonotope:
        case FixedTailFamily::parallelotope:
        case FixedTailFamily::ellipsoid:
            break;
        default:
            throw Rejected{invalid("unknown physical fixed-tail family")};
        }
        const auto n = model.observed.size(), horizon = model.stages.size(),
                   m = model.source_cost.coordinates.dimensions.control;
        const auto dimension = (horizon + 1) * n + horizon * m;
        if (request.shifted_initial_history.size() != dimension ||
            model.state_domains.size() != horizon + 1 || model.control_domains.size() != horizon ||
            model.stages.size() != model.input_carriers.size())
            throw Rejected{invalid("source dimensions or shifted initial history differ")};
        FullHistoryLift full{model.source_cost.coordinates, identity(dimension),
                             Vector(dimension, 0)};
        std::vector<std::size_t> positives;
        for (const auto axis : request.strictly_positive_state_coordinates) {
            if (axis >= n || model.observed[axis] <= 0)
                throw Rejected{invalid("strict observed source coordinate is not positive")};
            for (std::size_t k = 1; k <= horizon; ++k)
                positives.push_back(k * n + axis);
        }
        const auto run = [&](const FixedTailSolveRequest &input) -> FixedTailSolveOutcome {
            auto prepared = provider.prepare(input);
            if (const auto *rejected = std::get_if<registry::Rejection>(&prepared)) {
                failure.providers.push_back(rejected->provenance);
                return rejected->diagnostics.empty() ? invalid("optimizer admission failed")
                                                     : rejected->diagnostics.front();
            }
            auto pipeline = std::get<registry::PreparedPipeline<registry::FixedTailOptimizerPort>>(
                std::move(prepared));
            failure.providers.push_back(pipeline.provenance().front());
            auto workspace = std::get<0>(pipeline.create());
            return workspace->run(context);
        };
        failure.phase = "feasibility";
        auto anchor_outcome = run({{model.problem, {request.request.value + "/feasibility"}},
                                   model.full_history,
                                   model.source_cost,
                                   std::move(full),
                                   {},
                                   request.shifted_initial_history,
                                   true,
                                   positives});
        if (const auto *stop = std::get_if<OperationStopped>(&anchor_outcome))
            return *stop;
        auto anchor = take(std::move(anchor_outcome));
        failure.feasibility = anchor;
        if (anchor.history.size() != dimension || anchor.primary.size() != dimension ||
            !finite_values(anchor.history) || !finite_values(anchor.primary) ||
            !std::isfinite(anchor.objective))
            throw Rejected{
                invalid("feasibility provider returned malformed or nonfinite history storage")};
        if (anchor.supplied_initial_primary != request.shifted_initial_history ||
            anchor.provider_initial_primary_readback.size() != dimension ||
            !finite_values(anchor.provider_initial_primary_readback) ||
            !initial_readback_matches(request.shifted_initial_history,
                                      anchor.provider_initial_primary_readback, positives) ||
            std::any_of(anchor.supplied_initial_duals.begin(), anchor.supplied_initial_duals.end(),
                        [](double v) { return v != 0; }))
            throw Rejected{invalid(
                "feasibility optimizer changed the submitted primal/readback or supplied nonzero duals")};
        auto recovered_anchor = anchor.history;
        auto anchor_adjustments = recover_anchor_commands(model, recovered_anchor);
        auto lift = take(fixed_control_tail_lift(model, recovered_anchor));
        Vector first(recovered_anchor.begin() + static_cast<std::ptrdiff_t>((horizon + 1) * n),
                     recovered_anchor.begin() + static_cast<std::ptrdiff_t>((horizon + 1) * n + m));
        auto center = take(recover_fixed_tail_history(lift, first));
        if (!admitted(model.full_history, center))
            throw Rejected{invalid("fixed-tail anchor failed full source H check")};
        for (const auto coordinate : positives)
            if (center[coordinate] <= 0)
                throw Rejected{invalid("fixed-tail anchor violates strict source domain")};
        const auto carrier = carriers(model);
        failure.phase = "inner-regions";
        for (std::size_t j = 0; j <= horizon; ++j) {
            if (auto stop = stopped(context))
                return *stop;
            failure.region_prefix.push_back(region(model, center, j, request.family, carrier[j],
                                                   request.strictly_positive_state_coordinates));
        }
        auto current_domain = empty_rows(dimension);
        Matrix C{m, dimension, Vector(m * dimension, 0)};
        for (std::size_t j = 0; j < m; ++j)
            C.values[j * dimension + (horizon + 1) * n + j] = 1;
        pull_rows(current_domain, model.control_domains[0], C, Vector(m, 0));
        failure.phase = "reduced-argmin";
        auto solved_outcome = run({{model.problem, {request.request.value + "/current-action"}},
                                   std::move(current_domain),
                                   model.source_cost,
                                   lift,
                                   failure.region_prefix,
                                   first,
                                   false,
                                   {}});
        if (const auto *stop = std::get_if<OperationStopped>(&solved_outcome))
            return *stop;
        auto solved = take(std::move(solved_outcome));
        failure.reduced_argmin = solved;
        if (solved.primary.size() != m || solved.history.size() != dimension ||
            !finite_values(solved.primary) || !finite_values(solved.history) ||
            !std::isfinite(solved.objective))
            throw Rejected{
                invalid("reduced provider returned malformed or nonfinite history storage")};
        if (solved.supplied_initial_primary != first ||
            solved.provider_initial_primary_readback.size() != m ||
            !finite_values(solved.provider_initial_primary_readback) ||
            !initial_readback_matches(first, solved.provider_initial_primary_readback) ||
            std::any_of(solved.supplied_initial_duals.begin(), solved.supplied_initial_duals.end(),
                        [](double value) { return value != 0; }))
            throw Rejected{invalid(
                "reduced optimizer changed the recovered initial primal/readback or supplied nonzero duals")};
        auto recovered_control = solved.primary;
        auto command_adjustments =
            recover_authored_command_bounds(model.control_domains[0], recovered_control, {0});
        auto history = take(recover_fixed_tail_history(lift, recovered_control));
        if (solved.history.size() != history.size() || !admitted(model.full_history, history))
            throw Rejected{invalid("reduced action failed independent full source H check")};
        for (std::size_t i = 0; i < history.size(); ++i)
            if (std::abs(history[i] - solved.history[i]) > 1e-7 + 1e-8 * std::abs(history[i]))
                throw Rejected{invalid("provider history differs from the native affine recovery")};
        for (const auto coordinate : positives)
            if (history[coordinate] <= 0)
                throw Rejected{invalid("reduced history violates strict source domain")};
        if (solved.region_factors.size() != failure.region_prefix.size())
            throw Rejected{invalid("missing native region membership witnesses")};
        for (std::size_t j = 0; j < failure.region_prefix.size(); ++j) {
            const auto &r = failure.region_prefix[j];
            const auto x = std::span<const double>(history).subspan(j * n, n);
            if (!admitted(r.reference, x))
                throw Rejected{invalid("recovered history leaves a fixed-tail inner reference")};
            if (!r.inner)
                continue;
            const auto &set = *r.inner;
            Vector witness = solved.region_factors[j];
            if (j == 0 || set.point)
                witness = Vector(set.factor.cols, 0);
            if (witness.size() != set.factor.cols)
                throw Rejected{invalid("region factor witness dimension differs")};
            double norm = 0;
            for (const auto value : witness) {
                if (!std::isfinite(value))
                    throw Rejected{invalid("nonfinite region factor witness")};
                if (set.norm == InnerTemplateNorm::euclidean_ball)
                    norm = std::hypot(norm, value);
                else
                    norm = std::max(norm, std::abs(value));
            }
            if (norm > 1 + 1e-7)
                throw Rejected{invalid("region factor witness violates its original norm")};
            const auto reconstructed = image(set.factor, witness, set.center);
            for (std::size_t i = 0; i < n; ++i)
                if (std::abs(x[i] - reconstructed[i]) > 1e-7)
                    throw Rejected{
                        invalid("recovered state differs from physical inner-region membership")};
        }
        std::vector<Vector> states, controls;
        for (std::size_t j = 0; j <= horizon; ++j)
            states.emplace_back(history.begin() + static_cast<std::ptrdiff_t>(j * n),
                                history.begin() + static_cast<std::ptrdiff_t>((j + 1) * n));
        for (std::size_t j = 0; j < horizon; ++j)
            controls.emplace_back(
                history.begin() + static_cast<std::ptrdiff_t>((horizon + 1) * n + j * m),
                history.begin() + static_cast<std::ptrdiff_t>((horizon + 1) * n + (j + 1) * m));
        auto cost = take(optimization::evaluate_history_cost(model.source_cost, states, controls));
        if (!std::isfinite(solved.objective) ||
            std::abs(cost.total - solved.objective) >
                1e-7 + 1e-8 * std::max(std::abs(cost.total), std::abs(solved.objective)))
            throw Rejected{
                invalid("reduced optimizer objective differs from full original source cost")};
        return FixedTailPolicyResult{model.problem,
                                     request.request,
                                     request.family,
                                     std::move(recovered_control),
                                     std::move(history),
                                     center,
                                     cost,
                                     std::move(anchor),
                                     std::move(solved),
                                     std::move(anchor_adjustments),
                                     std::move(command_adjustments),
                                     std::move(lift),
                                     std::move(failure.region_prefix),
                                     std::move(failure.providers)};
    } catch (const Rejected &e) {
        failure.cause = e.error;
        return failure;
    }
}
} // namespace csl::reachability
