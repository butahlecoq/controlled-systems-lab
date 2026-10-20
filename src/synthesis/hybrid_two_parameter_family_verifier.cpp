#include "hybrid_family_verifier_internal.hpp"
#include <csl/synthesis/hybrid_path_program.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <optional>

namespace csl::synthesis {
namespace {
using namespace model;
constexpr std::size_t max_rows = 4096;
constexpr std::size_t max_vertices = 4096;
struct I {
  double lo{}, hi{};
  bool empty{};
};
struct P {
  double x{}, y{};
  bool operator==(const P &) const = default;
};
using Poly = std::vector<P>;
struct Aff {
  double c{}, x{}, y{};
};
struct Branch {
  enum class State {
    feasible,
    infeasible,
    unsupported
  } state{State::unsupported};
  std::string why;
  std::vector<Aff> tuple;
  std::array<std::size_t, 2> parameter_stages{};
  Poly parameter_box;
  Poly feasible;
  double ox{}, oy{}, oc{}, minimum{};
};

bool prod(double a, double b, double &r) {
  r = a * b;
  if (!std::isfinite(r))
    return false;
  if (a == 0 || b == 0)
    return r == 0;
  if (r == 0 || std::abs(r) < std::numeric_limits<double>::min())
    return false;
  int ea = 0, eb = 0;
  std::frexp(a, &ea);
  std::frexp(b, &eb);
  if (ea + eb - 106 < std::numeric_limits<double>::min_exponent -
                          std::numeric_limits<double>::digits)
    return false;
  return std::fma(a, b, -r) == 0;
}
bool sum(double a, double b, double &r) {
  r = a + b;
  if (!std::isfinite(r))
    return false;
  const double bv = r - a, av = r - bv, br = b - bv, ar = a - av;
  return ar + br == 0;
}
bool record_exact(bool success, bool &exact) {
  exact = exact && success;
  return success;
}
bool divi(double a, double b, double &r) {
  if (!std::isfinite(a) || !std::isfinite(b) || b == 0)
    return false;
  r = a / b;
  double back = 0;
  return std::isfinite(r) && prod(r, b, back) && back == a;
}
bool addmul(double &c, double &x, double &y, const Aff &a, double m) {
  double p = 0, n = 0;
  if (!prod(a.c, m, p) || !sum(c, p, n))
    return false;
  c = n;
  if (!prod(a.x, m, p) || !sum(x, p, n))
    return false;
  x = n;
  if (!prod(a.y, m, p) || !sum(y, p, n))
    return false;
  y = n;
  return true;
}
bool affine_flow(const LinearStage &f, const Aff &s, const Aff &u, Aff &out) {
  if (f.A.rows != 1 || f.A.cols != 1 || f.B.rows != 1 || f.B.cols != 1 ||
      f.E.rows != 1 || f.E.cols != 0 || f.offset.size() != 1)
    return false;
  out = {f.offset[0], 0, 0};
  return addmul(out.c, out.x, out.y, s, f.A.values[0]) &&
         addmul(out.c, out.x, out.y, u, f.B.values[0]);
}
const HybridMode *mode(const HybridSystem &s, const HybridModeId &id) {
  auto i = std::find_if(s.modes.begin(), s.modes.end(),
                        [&](const auto &m) { return m.id == id; });
  return i == s.modes.end() ? nullptr : &*i;
}
const HybridTransitionEdge *edge(const HybridSystem &s,
                                 const HybridEdgeId &id) {
  auto i = std::find_if(s.edges.begin(), s.edges.end(),
                        [&](const auto &e) { return e.id == id; });
  return i == s.edges.end() ? nullptr : &*i;
}
std::optional<I> interval(const AdmissibleSet &set, std::stop_token stop,
                          bool &cancelled, std::size_t &rows_used) {
  if (stop.stop_requested()) {
    cancelled = true;
    return {};
  }
  return std::visit(
      [&](const auto &v) -> std::optional<I> {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, UniversalSet>)
          return v.dimension == 1
                     ? std::optional<I>{I{-INFINITY, INFINITY, false}}
                     : std::nullopt;
        else if constexpr (std::is_same_v<T, EmptySet>)
          return v.dimension == 1 ? std::optional<I>{I{0, 0, true}}
                                  : std::nullopt;
        else if constexpr (std::is_same_v<T, Singleton>)
          return v.point.size() == 1 && std::isfinite(v.point[0])
                     ? std::optional<I>{I{v.point[0], v.point[0], false}}
                     : std::nullopt;
        else {
          auto d = sets::from_handle(v);
          if (std::holds_alternative<Diagnostic>(d))
            return {};
          auto r = std::get<sets::SetData>(d).representation();
          if (std::holds_alternative<sets::EmptyRepresentation>(r))
            return I{0, 0, true};
          if (std::holds_alternative<sets::UniversalRepresentation>(r))
            return I{-INFINITY, INFINITY, false};
          if (const auto *p = std::get_if<sets::SingletonRepresentation>(&r))
            return p->point.size() == 1 && std::isfinite(p->point[0])
                       ? std::optional<I>{I{p->point[0], p->point[0], false}}
                       : std::nullopt;
          const auto *h = std::get_if<sets::HRepresentation>(&r);
          if (!h || h->equalities.cols() != 1 || h->inequalities.cols() != 1 ||
              h->equalities.rows() > max_rows - rows_used ||
              h->inequalities.rows() >
                  max_rows - rows_used - h->equalities.rows() ||
              h->equality_values.size() != h->equalities.rows() ||
              h->upper_bounds.size() != h->inequalities.rows())
            return {};
          rows_used += h->equalities.rows() + h->inequalities.rows();
          I out{-INFINITY, INFINITY, false};
          for (std::size_t j = 0; j < h->equalities.rows(); ++j) {
            if ((j & 255U) == 0 && stop.stop_requested()) {
              cancelled = true;
              return {};
            }
            auto a = h->equalities(j, 0), b = h->equality_values[j];
            double x = 0;
            if (!std::isfinite(a) || !std::isfinite(b))
              return {};
            if (a == 0) {
              if (b != 0)
                out.empty = true;
            } else if (!divi(b, a, x))
              return {};
            else {
              out.lo = std::max(out.lo, x);
              out.hi = std::min(out.hi, x);
            }
          }
          for (std::size_t j = 0; j < h->inequalities.rows(); ++j) {
            if ((j & 255U) == 0 && stop.stop_requested()) {
              cancelled = true;
              return {};
            }
            auto a = h->inequalities(j, 0), b = h->upper_bounds[j];
            double x = 0;
            if (!std::isfinite(a) || !std::isfinite(b))
              return {};
            if (a == 0) {
              if (b < 0)
                out.empty = true;
            } else if (!divi(b, a, x))
              return {};
            else if (a > 0)
              out.hi = std::min(out.hi, x);
            else
              out.lo = std::max(out.lo, x);
          }
          if (out.lo > out.hi)
            out.empty = true;
          return out;
        }
      },
      set);
}
bool clip(Poly &p, double a, double b, double c, std::stop_token stop,
          bool &exact) {
  if (p.empty())
    return true;
  Poly q;
  q.reserve(p.size() + 1);
  auto value = [&](P v, double &z) {
    double x = 0, y = 0;
    return prod(a, v.x, x) && prod(b, v.y, y) && sum(x, y, x) && sum(x, -c, z);
  };
  for (std::size_t i = 0; i < p.size(); ++i) {
    if ((i & 255U) == 0 && stop.stop_requested())
      return false;
    const P s = p[i], t = p[(i + 1) % p.size()];
    double fs = 0, ft = 0;
    if (!value(s, fs) || !value(t, ft)) {
      exact = false;
      return false;
    }
    const bool ins = fs <= 0, intt = ft <= 0;
    if (ins)
      q.push_back(s);
    if (ins != intt) {
      double den = 0, num = 0, lambda = 0, dx = 0, dy = 0, x = 0, y = 0;
      if (!sum(fs, -ft, den) || !sum(0, fs, num) || !divi(num, den, lambda) ||
          !sum(t.x, -s.x, dx) || !prod(lambda, dx, dx) || !sum(s.x, dx, x) ||
          !sum(t.y, -s.y, dy) || !prod(lambda, dy, dy) || !sum(s.y, dy, y)) {
        exact = false;
        return false;
      }
      q.push_back({x, y});
    }
    if (q.size() > max_vertices) {
      exact = false;
      return false;
    }
  }
  Poly clean;
  for (auto v : q)
    if (clean.empty() || !(clean.back() == v))
      clean.push_back(v);
  if (clean.size() > 1 && clean.front() == clean.back())
    clean.pop_back();
  p = std::move(clean);
  return true;
}
bool constrain(Poly &p, const I &in, const Aff &v, std::stop_token stop,
               bool &exact, std::size_t &clips_used) {
  if (in.empty) {
    p.clear();
    return true;
  }
  double upper = 0, lower = 0;
  if (std::isfinite(in.hi) && ++clips_used > max_rows) {
    exact = false;
    return false;
  }
  if (std::isfinite(in.hi) &&
      (!sum(in.hi, -v.c, upper) || !clip(p, v.x, v.y, upper, stop, exact))) {
    exact = false;
    return false;
  }
  if (std::isfinite(in.lo) && ++clips_used > max_rows) {
    exact = false;
    return false;
  }
  if (std::isfinite(in.lo) &&
      (!sum(v.c, -in.lo, lower) || !clip(p, -v.x, -v.y, lower, stop, exact))) {
    exact = false;
    return false;
  }
  return true;
}
std::optional<std::size_t> exact_rank(std::vector<std::vector<double>> a,
                                      std::stop_token stop) {
  if (stop.stop_requested())
    return {};
  if (a.empty())
    return std::size_t{0};
  const std::size_t columns = a.front().size();
  for (const auto &values : a) {
    if (stop.stop_requested() || values.size() != columns)
      return {};
  }
  std::size_t row = 0;
  for (std::size_t col = 0; col < columns && row < a.size(); ++col) {
    if (stop.stop_requested())
      return {};
    std::size_t pivot = row;
    while (pivot < a.size() && a[pivot][col] == 0) {
      if (stop.stop_requested())
        return {};
      ++pivot;
    }
    if (pivot == a.size())
      continue;
    std::swap(a[row], a[pivot]);
    const double d = a[row][col];
    for (std::size_t j = col; j < columns; ++j) {
      if (stop.stop_requested())
        return {};
      if (!divi(a[row][j], d, a[row][j]))
        return {};
    }
    for (std::size_t i = 0; i < a.size(); ++i)
      if (i != row && a[i][col] != 0) {
        if (stop.stop_requested())
          return {};
        const double factor = a[i][col];
        for (std::size_t j = col; j < columns; ++j) {
          if (stop.stop_requested())
            return {};
          double p = 0, n = 0;
          if (!prod(factor, a[row][j], p) || !sum(a[i][j], -p, n))
            return {};
          a[i][j] = n;
        }
      }
    ++row;
  }
  return row;
}
std::optional<std::size_t> dimension(const Poly &p) {
  if (p.empty())
    return std::size_t{0};
  if (p.size() == 1)
    return std::size_t{0};
  const P a = p[0];
  for (std::size_t i = 1; i < p.size(); ++i)
    for (std::size_t j = i + 1; j < p.size(); ++j) {
      double ax = 0, by = 0, bx = 0, ay = 0, left = 0, right = 0, det = 0;
      if (!sum(p[i].x, -a.x, ax) || !sum(p[j].y, -a.y, by) ||
          !sum(p[j].x, -a.x, bx) || !sum(p[i].y, -a.y, ay) ||
          !prod(ax, by, left) || !prod(bx, ay, right) ||
          !sum(left, -right, det))
        return {};
      if (det != 0)
        return std::size_t{2};
    }
  return std::size_t{1};
}
bool orient(P a, P b, P c, double &out) {
  double x1 = 0, y1 = 0, x2 = 0, y2 = 0, left = 0, right = 0;
  return sum(b.x, -a.x, x1) && sum(c.y, -a.y, y1) && sum(c.x, -a.x, x2) &&
         sum(b.y, -a.y, y2) && prod(x1, y1, left) && prod(x2, y2, right) &&
         sum(left, -right, out);
}
std::optional<Poly> canonical_hull(Poly p) {
  std::sort(p.begin(), p.end(),
            [](P a, P b) { return a.x < b.x || (a.x == b.x && a.y < b.y); });
  p.erase(std::unique(p.begin(), p.end()), p.end());
  if (p.size() < 3)
    return p;
  Poly h;
  for (auto v : p) {
    double d = 0;
    while (h.size() >= 2) {
      if (!orient(h[h.size() - 2], h.back(), v, d))
        return {};
      if (d > 0)
        break;
      h.pop_back();
    }
    h.push_back(v);
  }
  const auto lower = h.size();
  for (auto it = p.rbegin() + 1; it != p.rend(); ++it) {
    double d = 0;
    while (h.size() > lower) {
      if (!orient(h[h.size() - 2], h.back(), *it, d))
        return {};
      if (d > 0)
        break;
      h.pop_back();
    }
    h.push_back(*it);
  }
  if (!h.empty())
    h.pop_back();
  return h;
}
bool point_in_poly(const Poly &p, P q) {
  if (p.empty())
    return false;
  if (p.size() == 1)
    return p[0] == q;
  if (p.size() == 2) {
    double d = 0;
    if (!orient(p[0], p[1], q, d) || d != 0)
      return false;
    return q.x >= std::min(p[0].x, p[1].x) && q.x <= std::max(p[0].x, p[1].x) &&
           q.y >= std::min(p[0].y, p[1].y) && q.y <= std::max(p[0].y, p[1].y);
  }
  int sign = 0;
  for (std::size_t i = 0; i < p.size(); ++i) {
    double d = 0;
    if (!orient(p[i], p[(i + 1) % p.size()], q, d))
      return false;
    if (d == 0)
      continue;
    const int s = d > 0 ? 1 : -1;
    if (sign && sign != s)
      return false;
    sign = s;
  }
  return true;
}
bool reset_affine(const SetHandle &h, double &off, double &gain) {
  auto d = sets::from_handle(h);
  if (std::holds_alternative<Diagnostic>(d))
    return false;
  auto r = std::get<sets::SetData>(d).representation();
  const auto *p = std::get_if<sets::HRepresentation>(&r);
  if (!p || p->equalities.rows() != 1 || p->equalities.cols() != 2 ||
      p->inequalities.rows() != 0 || p->inequalities.cols() != 2 ||
      p->equality_values.size() != 1 || p->upper_bounds.size() != 0)
    return false;
  return divi(p->equality_values[0], p->equalities(0, 1), off) &&
         p->equalities(0, 1) != 0 &&
         divi(-p->equalities(0, 0), p->equalities(0, 1), gain);
}
Branch eval(const HybridSystem &sys, const HybridRequest &req,
            const HybridPath &path, std::stop_token stop) {
  Branch b;
  auto unsupported = [&](const char *s) {
    b.why = s;
    return b;
  };
  const std::size_t horizon = sys.horizon;
  if (horizon < 2 ||
      horizon > (std::numeric_limits<std::size_t>::max() - 1) / 3 ||
      path.modes.size() != horizon + 1 ||
      path.edges.size() != horizon || req.initial.state.size() != 1 ||
      !std::isfinite(req.initial.state[0]))
    return unsupported("Requires at least two scalar stages");
  std::vector<const HybridMode *> modes(horizon + 1);
  std::vector<const HybridTransitionEdge *> edges(horizon);
  for (std::size_t s = 0; s <= horizon; ++s) {
    modes[s] = mode(sys, path.modes[s]);
    if (!modes[s] || modes[s]->state_dimension != 1 ||
        modes[s]->control_dimension != 1 ||
        modes[s]->invariants.size() != horizon + 1 ||
        modes[s]->control_sets.size() != horizon)
      return unsupported("Requires scalar modes with stage-indexed controls and invariants");
  }
  for (std::size_t s = 0; s < horizon; ++s) {
    edges[s] = edge(sys, path.edges[s]);
    if (!edges[s] || edges[s]->source != modes[s]->id ||
        edges[s]->target != modes[s + 1]->id ||
        edges[s]->guards.size() != horizon ||
        edges[s]->reset_relations.size() != horizon)
      return unsupported("Path edges are outside the scalar profile");
  }
  bool cancelled = false, exact = true;
  std::size_t rows_used = 0, clips_used = 0;
  std::array<std::size_t, 2> parameter_stages{};
  std::array<I, 2> parameter_intervals{};
  std::size_t parameter_count = 0;
  std::vector<I> controls(horizon);
  for (std::size_t s = 0; s < horizon; ++s) {
    auto control = interval(modes[s]->control_sets[s], stop, cancelled, rows_used);
    if (!control)
      return unsupported("Control set is unsupported");
    controls[s] = *control;
    if (control->empty) {
      b.state = Branch::State::infeasible;
      return b;
    }
    if (!std::isfinite(control->lo) || !std::isfinite(control->hi))
      return unsupported("Requires bounded control intervals");
    if (control->lo < control->hi) {
      if (parameter_count == parameter_stages.size())
        return unsupported("Requires exactly two non-singleton control intervals");
      parameter_stages[parameter_count] = s;
      parameter_intervals[parameter_count] = *control;
      ++parameter_count;
    }
  }
  if (parameter_count != 2)
    return unsupported("Requires exactly two non-singleton control intervals");
  b.parameter_stages = parameter_stages;
  b.feasible = {{parameter_intervals[0].lo, parameter_intervals[1].lo},
                {parameter_intervals[0].hi, parameter_intervals[1].lo},
                {parameter_intervals[0].hi, parameter_intervals[1].hi},
                {parameter_intervals[0].lo, parameter_intervals[1].hi}};
  b.parameter_box = b.feasible;
  const std::size_t tuple_size = 1 + 3 * horizon;
  b.tuple.resize(tuple_size);
  b.tuple[0].c = req.initial.state[0];
  Aff state = b.tuple[0];
  for (std::size_t s = 0; s < horizon; ++s) {
    auto inv = interval(modes[s]->invariants[s], stop, cancelled, rows_used);
    if (!inv)
      return unsupported("Invariant set is unsupported");
    if (!constrain(b.feasible, *inv, state, stop, exact, clips_used))
      return unsupported("Polygon clipping cancelled or exceeded exactness");
    Aff u{};
    if (s == parameter_stages[0])
      u = {0, 1, 0};
    else if (s == parameter_stages[1])
      u = {0, 0, 1};
    else
      u.c = controls[s].lo;
    b.tuple[1 + 3 * s] = u;
    if (!constrain(b.feasible, controls[s], u, stop, exact, clips_used))
      return unsupported("Control interval clipping failed");
    const auto *flows = std::get_if<std::vector<LinearStage>>(&modes[s]->flow);
    const LinearStage *f = flows && flows->size() == horizon
                               ? &(*flows)[s]
                               : std::get_if<LinearStage>(&modes[s]->flow);
    if (!f || !affine_flow(*f, state, u, b.tuple[2 + 3 * s]))
      return unsupported("Flow arithmetic or shape is unsupported");
    Aff pre = b.tuple[2 + 3 * s];
    auto preinv = interval(modes[s]->invariants[s + 1], stop, cancelled, rows_used);
    auto guard = interval(edges[s]->guards[s], stop, cancelled, rows_used);
    if (!preinv || !guard)
      return unsupported("Pre-reset invariant or guard is unsupported");
    if (!constrain(b.feasible, *preinv, pre, stop, exact, clips_used) ||
        !constrain(b.feasible, *guard, pre, stop, exact, clips_used))
      return unsupported("Pre-reset clipping failed");
    if (rows_used == max_rows)
      return unsupported("Path interval/reset row limit exceeded");
    ++rows_used;
    double ro = 0, rg = 0;
    if (!reset_affine(edges[s]->reset_relations[s], ro, rg))
      return unsupported("Requires deterministic exactly representable scalar affine resets");
    Aff post{ro, 0, 0};
    if (!addmul(post.c, post.x, post.y, pre, rg))
      return unsupported("Reset arithmetic is not exact");
    b.tuple[3 + 3 * s] = post;
    state = post;
    auto postinv = interval(modes[s + 1]->invariants[s + 1], stop, cancelled, rows_used);
    if (!postinv)
      return unsupported("Post-reset invariant is unsupported");
    if (!constrain(b.feasible, *postinv, post, stop, exact, clips_used))
      return unsupported("Post-reset clipping failed");
    if (b.feasible.empty()) {
      b.state = Branch::State::infeasible;
      return b;
    }
  }
  auto finalinv = interval(modes.back()->invariants[horizon], stop, cancelled, rows_used);
  if (!finalinv)
    return unsupported("Terminal invariant is unsupported");
  if (!constrain(b.feasible, *finalinv, state, stop, exact, clips_used))
    return unsupported("Terminal clipping failed");
  if (b.feasible.empty()) {
    b.state = Branch::State::infeasible;
    return b;
  }
  const auto feasible_dimension = dimension(b.feasible);
  if (!feasible_dimension)
    return unsupported("Feasible polygon dimension is not exactly representable");
  if (*feasible_dimension != 2)
    return unsupported("Degenerate feasible control polygons are unsupported");
  auto obj = std::find_if(req.terminal_objectives.begin(), req.terminal_objectives.end(),
      [&](const auto &o) { return o.mode == modes.back()->id; });
  if (obj == req.terminal_objectives.end())
    return unsupported("Missing terminal objective");
  const auto *l = std::get_if<LinearTerminal>(&obj->objective);
  if (!l || l->coefficients.size() != 1)
    return unsupported("Requires scalar linear terminal objective");
  if (!prod(l->coefficients[0], state.x, b.ox) ||
      !prod(l->coefficients[0], state.y, b.oy) ||
      !prod(l->coefficients[0], state.c, b.oc) || !sum(b.oc, l->offset, b.oc))
    return unsupported("Objective arithmetic is not exact");
  b.minimum = std::numeric_limits<double>::infinity();
  for (auto p : b.feasible) {
    double x = 0, y = 0, z = 0;
    if (!prod(b.ox, p.x, x) || !prod(b.oy, p.y, y) || !sum(x, y, z) || !sum(z, b.oc, z))
      return unsupported("Objective vertex arithmetic is not exact");
    b.minimum = std::min(b.minimum, z);
  }
  b.state = Branch::State::feasible;
  return b;
}
} // namespace

HybridFamilyVerificationCapabilities
TwoParameterScalarPolytopeHybridFamilyVerifier::capabilities() const noexcept {
  return {true, true, true, Assurance::numerical};
}
HybridFamilyVerificationPreflightResult
TwoParameterScalarPolytopeHybridFamilyVerifier::preflight(
    const HybridSystem &s, const HybridRequest &r,
    std::span<const HybridPath> paths,
    std::span<const HybridPlannedOperation> operation_plan,
    std::stop_token stop) const {
  for (const auto &terminal_mode : r.allowed_terminal_modes) {
    if (stop.stop_requested())
      return OperationStopped{StopReason::cancelled,
                              "Two-parameter admission cancelled while checking terminal objectives"};
    const auto objective = std::find_if(r.terminal_objectives.begin(),
        r.terminal_objectives.end(), [&](const auto &candidate) {
          return candidate.mode == terminal_mode;
        });
    const auto mode = std::find_if(s.modes.begin(), s.modes.end(),
        [&](const auto &candidate) { return candidate.id == terminal_mode; });
    const auto *linear = objective == r.terminal_objectives.end()
        ? nullptr : std::get_if<LinearTerminal>(&objective->objective);
    if (!linear || mode == s.modes.end() ||
        linear->coefficients.size() != mode->state_dimension)
      return Diagnostics{{DiagnosticCode::unsupported,
                          "hybrid.verification.two_parameter_objective",
                          "Terminal mode " + terminal_mode.value +
                              ": two-parameter verification requires a scalar linear objective matching the terminal state dimension"}};
  }
  for (const auto &p : paths) {
    if (stop.stop_requested())
      return OperationStopped{StopReason::cancelled,
                              "Two-parameter admission cancelled"};
    auto b = eval(s, r, p, stop);
    if (stop.stop_requested())
      return OperationStopped{StopReason::cancelled,
                              "Two-parameter admission cancelled"};
    if (b.state == Branch::State::unsupported)
      return Diagnostics{{DiagnosticCode::unsupported,
                          "hybrid.verification.two_parameter_domain",
                          detail::describe_hybrid_path(p) + ": " + b.why}};
  }
  return HybridOperationAdmissionSuccess{
      std::vector<HybridPlannedOperation>(operation_plan.begin(),operation_plan.end())};
}
HybridFamilyVerificationResult
TwoParameterScalarPolytopeHybridFamilyVerifier::verify(
    const HybridSystem &s, const HybridRequest &r,
    std::span<const HybridPath> paths,
    std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,
    NumericalPolicy policy, std::stop_token stop) const {
  if (stop.stop_requested())
    return OperationStopped{StopReason::cancelled,
                            "Two-parameter verification cancelled"};
  if (!std::isfinite(policy.absolute_tolerance) ||
      !std::isfinite(policy.relative_tolerance) ||
      policy.absolute_tolerance < 0 || policy.relative_tolerance < 0)
    return Diagnostics{{DiagnosticCode::invalid_input,
                        "hybrid.verification.two_parameter_policy",
                        "Tolerances must be finite and nonnegative"}};
  const auto profile_diagnostics = model::check_hybrid_profile(s, r);
  if (!profile_diagnostics.empty())
    return profile_diagnostics;
  if (s.horizon > (std::numeric_limits<std::size_t>::max() - 1) / 3)
    return Diagnostics{{DiagnosticCode::unsupported,
                        "hybrid.verification.two_parameter_dimension",
                        "Joint relation dimension overflows size_t"}};
  const std::size_t tuple_size = 1 + 3 * s.horizon;
  auto inv = detail::independently_enumerate_paths(
      s, r, paths.size(), std::max<std::size_t>(64, (s.edges.size() + 1) * 16),
      [&] { return stop.stop_requested(); });
  if (inv.cancelled || stop.stop_requested())
    return OperationStopped{StopReason::cancelled,
                            "Two-parameter path enumeration cancelled"};
  if (inv.resource_limit ||
      inv.paths != std::vector<HybridPath>(paths.begin(), paths.end()) ||
      programs.size() != paths.size())
    return Diagnostics{
        {DiagnosticCode::evidence_mismatch,
         "hybrid.verification.two_parameter_inventory",
         "Path or program inventory does not match independent enumeration"}};
  for (std::size_t i = 0; i < candidates.size(); ++i) {
    if (std::find(paths.begin(), paths.end(), candidates[i].path) ==
        paths.end())
      return Diagnostics{
          {DiagnosticCode::evidence_mismatch,
           "hybrid.verification.two_parameter_extra_face",
           "A face candidate is supplied for an unenumerated path"}};
    for (std::size_t j = 0; j < i; ++j)
      if (candidates[j].path == candidates[i].path)
        return Diagnostics{{DiagnosticCode::evidence_mismatch,
                            "hybrid.verification.two_parameter_duplicate_face",
                            "At most one face candidate is allowed per path"}};
  }
  std::vector<Branch> branches;
  double global = INFINITY;
  for (const auto &p : paths) {
    if (stop.stop_requested())
      return OperationStopped{StopReason::cancelled,
                              "Two-parameter traversal cancelled"};
    auto b = eval(s, r, p, stop);
    if (stop.stop_requested())
      return OperationStopped{
          StopReason::cancelled,
          "Two-parameter verification cancelled during reconstruction"};
    if (b.state == Branch::State::unsupported)
      return Diagnostics{{DiagnosticCode::unsupported,
                          "hybrid.verification.two_parameter_domain", b.why}};
    if (b.state == Branch::State::feasible)
      global = std::min(global, b.minimum);
    branches.push_back(std::move(b));
  }
  for (std::size_t i = 0; i < branches.size(); ++i) {
    const bool requires_face = branches[i].state == Branch::State::feasible &&
                               branches[i].minimum == global;
    const bool has_face = std::any_of(
        candidates.begin(), candidates.end(),
        [&](const auto &candidate) { return candidate.path == paths[i]; });
    if (requires_face != has_face)
      return Diagnostics{{DiagnosticCode::evidence_mismatch,
                          "hybrid.verification.two_parameter_face_inventory",
                          "Exactly one face candidate is required for each "
                          "globally optimal feasible path"}};
  }
  HybridFamilyVerificationReport report{
      "csl.hybrid.scalar-two-parameter-polytope",
      "1",
      policy,
      Assurance::numerical,
      std::vector<HybridPath>(paths.begin(), paths.end()),
      {},
      HybridVerificationStatus::not_checked,
      HybridVerificationStatus::not_checked,
      {},
      {}};
  report.branches.reserve(paths.size());
  bool all = true, any_unsupported = false;
  for (std::size_t i = 0; i < paths.size(); ++i) {
    const auto &b = branches[i];
    HybridPathVerificationRecord rec{};
    rec.path = paths[i];
    if (b.state == Branch::State::infeasible) {
      auto repr = programs[i].joint_relation.representation();
      bool empty = std::holds_alternative<sets::EmptyRepresentation>(repr);
      rec.feasibility = empty ? HybridVerificationStatus::refuted
                              : HybridVerificationStatus::unsupported;
      rec.objective_optimality = rec.feasibility;
      rec.continuous_coverage = rec.feasibility;
      all = all && empty;
      report.branches.push_back(std::move(rec));
      continue;
    }
    rec.feasibility = HybridVerificationStatus::established;
    const bool optimal = b.minimum == global;
    rec.objective_optimality = optimal ? HybridVerificationStatus::established
                                       : HybridVerificationStatus::refuted;
    const auto repr = programs[i].joint_relation.representation();
    const auto *h = std::get_if<sets::HRepresentation>(&repr);
    const auto hull_dimension = dimension(b.feasible);
    const bool program_domain =
        h && programs[i].path == paths[i] &&
        programs[i].relation_limits.max_variables >= tuple_size &&
        programs[i].joint_relation.metadata()->set.dimension == tuple_size &&
        h->equalities.cols() == tuple_size && h->inequalities.cols() == tuple_size &&
        h->equalities.rows() + h->inequalities.rows() <= 4096 &&
        h->equalities.rows() <= programs[i].relation_limits.max_rows &&
        h->inequalities.rows() <= programs[i].relation_limits.max_rows &&
        h->equality_values.size() == h->equalities.rows() &&
        h->upper_bounds.size() == h->inequalities.rows() &&
        (h->equalities.rows() + h->inequalities.rows()) <=
            programs[i].relation_limits.max_matrix_elements / tuple_size &&
        hull_dimension && *hull_dimension == 2;
    bool valid = program_domain;
    bool pullback_exact = true;
    bool rank_exact = true;
    if (valid) {
      std::vector<std::vector<double>> eq;
      for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        if ((row & 127U) == 0 && stop.stop_requested())
          return OperationStopped{StopReason::cancelled,
                                  "Two-parameter relation rank input cancelled"};
        std::vector<double> eqrow(tuple_size);
        for (std::size_t col = 0; col < tuple_size; ++col) {
          if ((col & 255U) == 0 && stop.stop_requested())
            return OperationStopped{StopReason::cancelled,
                                    "Two-parameter relation rank input cancelled"};
          eqrow[col] = h->equalities(row, col);
        }
        eq.push_back(eqrow);
      }
      const auto rank = exact_rank(std::move(eq), stop);
      if (stop.stop_requested())
        return OperationStopped{StopReason::cancelled,
                                "Two-parameter relation rank check cancelled"};
      rank_exact = rank.has_value();
      valid = rank && *rank == tuple_size - 2;
    }
    auto relation_poly = b.parameter_box;
    if (valid) {
      for (std::size_t row = 0; row < h->equalities.rows() && valid; ++row) {
        if ((row & 127U) == 0 && stop.stop_requested())
          return OperationStopped{StopReason::cancelled,
                                  "Two-parameter equality check cancelled"};
        double c = 0, x = 0, y = 0;
        for (std::size_t j = 0; j < tuple_size; ++j) {
          valid = valid &&
                  record_exact(prod(h->equalities(row, j), b.tuple[j].c, c),
                               pullback_exact);
          double q = 0;
          valid = valid &&
                  record_exact(prod(h->equalities(row, j), b.tuple[j].x, q),
                               pullback_exact) &&
                  record_exact(sum(x, q, x), pullback_exact);
          valid = valid &&
                  record_exact(prod(h->equalities(row, j), b.tuple[j].y, q),
                               pullback_exact) &&
                  record_exact(sum(y, q, y), pullback_exact);
        }
        valid =
            valid &&
            record_exact(sum(c, -h->equality_values[row], c), pullback_exact) &&
            x == 0 && y == 0 && c == 0;
      }
      for (std::size_t row = 0; row < h->inequalities.rows() && valid; ++row) {
        if ((row & 127U) == 0 && stop.stop_requested())
          return OperationStopped{StopReason::cancelled,
                                  "Two-parameter inequality check cancelled"};
        double c = 0, x = 0, y = 0, bound = 0;
        for (std::size_t j = 0; j < tuple_size; ++j) {
          double q = 0;
          valid = valid &&
                  record_exact(prod(h->inequalities(row, j), b.tuple[j].c, q),
                               pullback_exact) &&
                  record_exact(sum(c, q, c), pullback_exact);
          valid = valid &&
                  record_exact(prod(h->inequalities(row, j), b.tuple[j].x, q),
                               pullback_exact) &&
                  record_exact(sum(x, q, x), pullback_exact);
          valid = valid &&
                  record_exact(prod(h->inequalities(row, j), b.tuple[j].y, q),
                               pullback_exact) &&
                  record_exact(sum(y, q, y), pullback_exact);
        }
        valid = valid && std::isfinite(h->upper_bounds[row]) &&
                record_exact(sum(h->upper_bounds[row], -c, bound),
                             pullback_exact) &&
                clip(relation_poly, x, y, bound, stop, pullback_exact);
      }
      auto expected = canonical_hull(b.feasible),
           actual = canonical_hull(relation_poly);
      if (!expected || !actual)
        pullback_exact = false;
      valid = valid && expected && actual && *expected == *actual;
    }
    bool covered = false,
         coverage_unsupported = !program_domain || !rank_exact ||
                                !pullback_exact || !hull_dimension ||
                                *hull_dimension != 2;
    const auto *program_linear =
        std::get_if<LinearProgram>(&programs[i].program);
    const auto objective = std::find_if(
        r.terminal_objectives.begin(), r.terminal_objectives.end(),
        [&](const auto &o) { return o.mode == paths[i].modes.back(); });
    const auto *terminal_linear =
        objective == r.terminal_objectives.end()
            ? nullptr
            : std::get_if<LinearTerminal>(&objective->objective);
    if (!program_linear || !terminal_linear ||
        program_linear->objective().size() != tuple_size ||
        terminal_linear->coefficients.size() != 1)
      valid = false;
    else
      for (std::size_t j = 0; j < tuple_size; ++j) {
        const double expected = j + 1 == tuple_size ? terminal_linear->coefficients[0] : 0;
        if (program_linear->objective()[j] != expected)
          valid = false;
      }
    if (!program_linear || !terminal_linear ||
        program_linear->offset() != terminal_linear->offset)
      valid = false;
    auto cand = std::find_if(candidates.begin(), candidates.end(),
                             [&](const auto &c) { return c.path == paths[i]; });
    if (valid && !optimal)
      covered = cand == candidates.end();
    if (valid && optimal && cand != candidates.end()) {
      auto face = b.feasible;
      bool ex = true;
      if (b.ox != 0 || b.oy != 0) {
        double upper = 0, lower = 0;
        ex = sum(global, -b.oc, upper) && sum(b.oc, -global, lower) &&
             clip(face, b.ox, b.oy, upper, stop, ex) &&
             clip(face, -b.ox, -b.oy, lower, stop, ex);
      } // expected objective face
      const auto cr = cand->relation.representation();
      const auto *ch = std::get_if<sets::HRepresentation>(&cr);
      Poly cp = b.parameter_box;
      bool face_pullback_exact = true;
      bool cv = ch && cand->relation.metadata()->set.dimension == tuple_size &&
                ch->equalities.cols() == tuple_size && ch->inequalities.cols() == tuple_size;
      const bool candidate_domain =
          cv && cand->relation.metadata()->set.dimension == tuple_size &&
          programs[i].relation_limits.max_variables >= tuple_size &&
          ch->equalities.rows() + ch->inequalities.rows() <= 4096 &&
          ch->equalities.rows() <= programs[i].relation_limits.max_rows &&
          ch->inequalities.rows() <= programs[i].relation_limits.max_rows &&
          ch->equality_values.size() == ch->equalities.rows() &&
          ch->upper_bounds.size() == ch->inequalities.rows() &&
          (ch->equalities.rows() + ch->inequalities.rows()) <=
              programs[i].relation_limits.max_matrix_elements / tuple_size;
      if (!candidate_domain)
        coverage_unsupported = true;
      cv = candidate_domain;
      if (cv) {
        std::vector<std::vector<double>> eq;
        for (std::size_t row = 0; row < ch->equalities.rows(); ++row) {
          if ((row & 127U) == 0 && stop.stop_requested())
            return OperationStopped{StopReason::cancelled,
                                    "Two-parameter face rank input cancelled"};
          std::vector<double> eqrow(tuple_size);
          for (std::size_t j = 0; j < tuple_size; ++j) {
            if ((j & 255U) == 0 && stop.stop_requested())
              return OperationStopped{StopReason::cancelled,
                                      "Two-parameter face rank input cancelled"};
            eqrow[j] = ch->equalities(row, j);
          }
          eq.push_back(eqrow);
        }
        const auto rank = exact_rank(std::move(eq), stop);
        if (stop.stop_requested())
          return OperationStopped{StopReason::cancelled,
                                  "Two-parameter face rank check cancelled"};
        const auto face_dim = dimension(face);
        if (!rank || !face_dim)
          coverage_unsupported = true;
        cv = rank && face_dim && *rank == tuple_size - *face_dim;
      }
      if (cv) {
        for (std::size_t row = 0; row < ch->equalities.rows() && cv; ++row) {
          if ((row & 127U) == 0 && stop.stop_requested())
            return OperationStopped{
                StopReason::cancelled,
                "Two-parameter face equality check cancelled"};
          double c = 0, x = 0, y = 0;
          for (std::size_t j = 0; j < tuple_size; ++j) {
            double q = 0;
            cv = cv &&
                 record_exact(prod(ch->equalities(row, j), b.tuple[j].c, q),
                              face_pullback_exact) &&
                 record_exact(sum(c, q, c), face_pullback_exact);
            cv = cv &&
                 record_exact(prod(ch->equalities(row, j), b.tuple[j].x, q),
                              face_pullback_exact) &&
                 record_exact(sum(x, q, x), face_pullback_exact);
            cv = cv &&
                 record_exact(prod(ch->equalities(row, j), b.tuple[j].y, q),
                              face_pullback_exact) &&
                 record_exact(sum(y, q, y), face_pullback_exact);
          }
          cv = cv &&
               record_exact(sum(c, -ch->equality_values[row], c),
                            face_pullback_exact) &&
               clip(cp, x, y, c, stop, face_pullback_exact) &&
               clip(cp, -x, -y, -c, stop, face_pullback_exact);
        }
        for (std::size_t row = 0; row < ch->inequalities.rows() && cv; ++row) {
          if ((row & 127U) == 0 && stop.stop_requested())
            return OperationStopped{
                StopReason::cancelled,
                "Two-parameter face inequality check cancelled"};
          double c = 0, x = 0, y = 0;
          for (std::size_t j = 0; j < tuple_size; ++j) {
            double q = 0;
            cv = cv &&
                 record_exact(prod(ch->inequalities(row, j), b.tuple[j].c, q),
                              face_pullback_exact) &&
                 record_exact(sum(c, q, c), face_pullback_exact);
            cv = cv &&
                 record_exact(prod(ch->inequalities(row, j), b.tuple[j].x, q),
                              face_pullback_exact) &&
                 record_exact(sum(x, q, x), face_pullback_exact);
            cv = cv &&
                 record_exact(prod(ch->inequalities(row, j), b.tuple[j].y, q),
                              face_pullback_exact) &&
                 record_exact(sum(y, q, y), face_pullback_exact);
          }
          double bound = 0;
          cv = cv &&
               record_exact(sum(ch->upper_bounds[row], -c, bound),
                            face_pullback_exact) &&
               clip(cp, x, y, bound, stop, face_pullback_exact);
        }
      }
      auto face_hull = canonical_hull(face),
           candidate_hull = canonical_hull(cp);
      if (!face_hull || !candidate_hull)
        face_pullback_exact = false;
      if (stop.stop_requested())
        return OperationStopped{StopReason::cancelled,
                                "Two-parameter face pullback cancelled"};
      if (!ex || !face_pullback_exact)
        coverage_unsupported = true;
      covered =
          cv && ex && face_hull && candidate_hull &&
          *face_hull == *candidate_hull && cand->anchor.size() == tuple_size &&
          cand->solver_result.termination == Termination::completed &&
          cand->solver_result.outcome.value == MathematicalOutcome::optimal &&
          cand->solver_result.primal && cand->solver_result.primal->size() == tuple_size;
      if (covered) {
        bool candidate_tuple_exact = true;
        for (std::size_t j = 0; j < tuple_size; ++j)
          covered = covered &&
                    std::isfinite((*cand->solver_result.primal)[j]) &&
                    std::isfinite(cand->anchor[j]) &&
                    std::abs((*cand->solver_result.primal)[j] -
                             cand->anchor[j]) <=
                        policy.absolute_tolerance +
                            policy.relative_tolerance *
                                std::max(1.0, std::abs(cand->anchor[j]));
        const P anchor{cand->anchor[1 + 3 * b.parameter_stages[0]],
                       cand->anchor[1 + 3 * b.parameter_stages[1]]};
        covered = covered && point_in_poly(*face_hull, anchor);
        for (std::size_t j = 0; j < tuple_size && covered; ++j) {
          double x = 0, y = 0, v = 0;
          const bool exact =
              prod(b.tuple[j].x, anchor.x, x) &&
              prod(b.tuple[j].y, anchor.y, y) &&
              sum(b.tuple[j].c, x, v) && sum(v, y, v);
          record_exact(exact, candidate_tuple_exact);
          covered = exact &&
                    std::abs(v - cand->anchor[j]) <=
                        policy.absolute_tolerance +
                            policy.relative_tolerance *
                                std::max(1.0, std::abs(cand->anchor[j]));
        }
        if (!candidate_tuple_exact)
          coverage_unsupported = true;
      }
    }
    rec.continuous_coverage =
        covered ? HybridVerificationStatus::established
                : (coverage_unsupported ? HybridVerificationStatus::unsupported
                                        : HybridVerificationStatus::refuted);
    any_unsupported =
        any_unsupported ||
        rec.continuous_coverage == HybridVerificationStatus::unsupported;
    all = all && covered;
    report.branches.push_back(std::move(rec));
  }
  report.global_objective_optimality =
      std::isfinite(global) ? HybridVerificationStatus::established
                            : HybridVerificationStatus::refuted;
  report.complete_family_coverage =
      all ? HybridVerificationStatus::established
          : (any_unsupported ? HybridVerificationStatus::unsupported
                             : HybridVerificationStatus::refuted);
  if (stop.stop_requested())
    return OperationStopped{
        StopReason::cancelled,
        "Two-parameter report cancelled before publication"};
  return report;
}
} // namespace csl::synthesis
