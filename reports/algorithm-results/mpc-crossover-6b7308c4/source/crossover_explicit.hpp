#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <stdexcept>
#include <vector>

namespace mpc_crossover {

using Point = std::array<double, 2>;
using AffineLaw = std::array<double, 3>; // position, velocity, constant
using Polygon = std::vector<Point>;

inline double evaluate(const AffineLaw &f, Point x) { return f[0] * x[0] + f[1] * x[1] + f[2]; }

struct Region {
    Polygon vertices;
    AffineLaw action;
};

class ExplicitController {
  public:
    explicit ExplicitController(int n) : n_(n) {
        if (n < 1 || n > 3)
            throw std::invalid_argument("horizon must be 1, 2 or 3");
        // Each row stores coefficients of u and an affine upper bound in the initial state.
        for (int i = 0; i < n; ++i) {
            for (int sign : {-1, 1}) {
                Bound row{};
                row.g[i] = sign;
                row.rhs[2] = 1;
                bounds_.push_back(row);
            }
        }
        for (int k = 1; k <= n; ++k) {
            for (int sign : {-1, 1}) {
                bound_state(k, sign, 0, 3);
                bound_state(k, 0, sign, 2);
                if (k == n) {
                    bound_state(k, sign, sign, 1);
                    bound_state(k, sign, 2 * sign, 1);
                }
            }
        }
        std::array<int, 3> active{};
        enumerate(active, 0, 0);
        if (regions_.empty())
            throw std::runtime_error("empty explicit policy");
        // The deployed policy needs only polygons and first-action coefficients.
        std::vector<Bound>().swap(bounds_);
    }

    std::optional<double> decide(Point x) const {
        if (!std::isfinite(x[0]) || !std::isfinite(x[1]))
            throw std::invalid_argument("state must be finite");
        for (const auto &region : regions_) {
            if (contains(region.vertices, x))
                return evaluate(region.action, x);
        }
        return std::nullopt;
    }
    const std::vector<Region> &regions() const { return regions_; }
    std::size_t storage_bytes() const {
        auto bytes = sizeof(*this) + regions_.capacity() * sizeof(Region);
        for (const auto &region : regions_)
            bytes += region.vertices.capacity() * sizeof(Point);
        return bytes;
    }

  private:
    struct Bound {
        std::array<double, 3> g;
        AffineLaw rhs;
    };
    // At most three controls plus three active multipliers, with three right-hand sides.
    using System = std::array<std::array<double, 9>, 6>;
    static constexpr double epsilon = 1e-10;

    void bound_state(int k, int a, int b, int limit) {
        Bound row{};
        for (int j = 0; j < k; ++j)
            row.g[j] = a * (k - 1 - j) + b;
        row.rhs = {-double(a), -double(k * a + b), double(limit)};
        bounds_.push_back(row);
    }
    static bool contains(const Polygon &poly, Point x) {
        for (std::size_t i = 0; i < poly.size(); ++i) {
            const auto p = poly[i], q = poly[(i + 1) % poly.size()];
            const double cross = (q[0] - p[0]) * (x[1] - p[1]) - (q[1] - p[1]) * (x[0] - p[0]);
            if (cross < -epsilon * std::hypot(q[0] - p[0], q[1] - p[1]))
                return false;
        }
        return true;
    }
    static void clip(Polygon &polygon, const AffineLaw &margin) {
        if (polygon.empty())
            return;
        Polygon out;
        Point p = polygon.back();
        double prev = evaluate(margin, p);
        for (auto q : polygon) {
            double value = evaluate(margin, q);
            if (std::abs(value) < epsilon)
                value = 0;
            if (std::abs(prev) < epsilon)
                prev = 0;
            if ((value < 0) != (prev < 0)) {
                const double t = prev / (prev - value);
                out.push_back({p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])});
            }
            if (value >= 0)
                out.push_back(q);
            p = q;
            prev = value;
        }
        auto same = [](Point a, Point b) { return std::hypot(a[0] - b[0], a[1] - b[1]) < epsilon; };
        out.erase(std::unique(out.begin(), out.end(), same), out.end());
        if (out.size() > 1 && same(out.front(), out.back()))
            out.pop_back();
        polygon.swap(out);
    }
    static bool solve(System &mat, int dim) {
        for (int j = 0; j < dim; ++j) {
            int pivot = j;
            for (int i = j + 1; i < dim; ++i)
                if (std::abs(mat[i][j]) > std::abs(mat[pivot][j]))
                    pivot = i;
            if (std::abs(mat[pivot][j]) < epsilon)
                return false;
            std::swap(mat[pivot], mat[j]);
            const double d = mat[j][j];
            for (int k = j; k < dim + 3; ++k)
                mat[j][k] /= d;
            for (int i = 0; i < dim; ++i) {
                if (i == j)
                    continue;
                const double factor = mat[i][j];
                for (int k = j; k < dim + 3; ++k)
                    mat[i][k] -= factor * mat[j][k];
            }
        }
        return true;
    }
    void enumerate(std::array<int, 3> &active, int first, int count) {
        consider(active, count);
        if (count == n_)
            return;
        for (int i = first; i < static_cast<int>(bounds_.size()); ++i) {
            if (bounds_[i].g == std::array<double, 3>{})
                continue;
            active[count] = i;
            enumerate(active, i + 1, count + 1);
        }
    }
    void consider(const std::array<int, 3> &active, int count) {
        const int dim = n_ + count;
        System kkt{};
        for (int i = 0; i < n_; ++i) {
            const int p_gain = n_ - i - 1;
            for (int j = 0; j < n_; ++j)
                kkt[i][j] = p_gain * (n_ - j - 1) + 1 + (i == j ? 0.25 : 0);
            kkt[i][dim] = -p_gain;
            kkt[i][dim + 1] = -(n_ * p_gain + 1);
        }
        for (int i = 0; i < count; ++i) {
            const auto &row = bounds_[active[i]];
            for (int j = 0; j < n_; ++j)
                kkt[n_ + i][j] = kkt[j][n_ + i] = row.g[j];
            std::copy(row.rhs.begin(), row.rhs.end(), kkt[n_ + i].begin() + dim);
        }
        if (!solve(kkt, dim))
            return;
        Polygon poly{{-3, -2}, {3, -2}, {3, 2}, {-3, 2}};
        for (int i = n_; i < dim && !poly.empty(); ++i)
            clip(poly, {kkt[i][dim], kkt[i][dim + 1], kkt[i][dim + 2]});
        for (const Bound &row : bounds_) {
            if (poly.empty())
                return;
            AffineLaw margin = row.rhs;
            for (int j = 0; j < n_; ++j)
                for (int k = 0; k < 3; ++k)
                    margin[k] -= row.g[j] * kkt[j][dim + k];
            clip(poly, margin);
        }
        double twice_area = 0;
        for (std::size_t i = 0; i < poly.size(); ++i) {
            const auto a = poly[i], b = poly[(i + 1) % poly.size()];
            twice_area += a[0] * b[1] - a[1] * b[0];
        }
        if (twice_area <= epsilon)
            return;
        for (const Region &region : regions_) {
            auto inside = [](const Polygon &a, const Polygon &b) {
                return std::all_of(a.begin(), a.end(), [&](Point p) { return contains(b, p); });
            };
            if (inside(poly, region.vertices) && inside(region.vertices, poly))
                return;
        }
        regions_.push_back({std::move(poly), {kkt[0][dim], kkt[0][dim + 1], kkt[0][dim + 2]}});
    }

    int n_;
    std::vector<Bound> bounds_;
    std::vector<Region> regions_;
};

} // namespace mpc_crossover
