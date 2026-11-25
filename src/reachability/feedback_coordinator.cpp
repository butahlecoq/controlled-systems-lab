#include <csl/reachability/feedback_geometry.hpp>
#include <csl/reachability/bounded_h_support.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/reachability/nominal_predecessor.hpp>
#include <csl/sets/data.hpp>
#include "../synthesis/exact_h_enclosure.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <new>
#include <numeric>
#include <span>
#include <stdexcept>

namespace csl::reachability {
namespace {
struct Failure {
    std::variant<Unsupported, OperationStopped> cause;
};
[[noreturn]] void bad(std::string field, std::string message) {
    throw Failure{
        Unsupported{{{DiagnosticCode::unsupported, std::move(field), std::move(message)}}}};
}
template <class T> T take(std::variant<T, Diagnostic> value) {
    if (auto *e = std::get_if<Diagnostic>(&value))
        throw Failure{Unsupported{{*e}}};
    return std::get<T>(std::move(value));
}
struct Rows {
    Matrix a, e;
    Vector b, f;
    explicit Rows(std::size_t n) : a{0, n, {}}, e{0, n, {}} {}
    void append(Vector row, double bound, bool equal = false) {
        auto &m = equal ? e : a;
        auto &v = equal ? f : b;
        if (m.rows == std::numeric_limits<std::size_t>::max() ||
            (m.cols && m.rows + 1 > std::numeric_limits<std::size_t>::max() / m.cols))
            throw Failure{OperationStopped{StopReason::resource_limit, "H row capacity exceeded."}};
        ++m.rows;
        m.values.insert(m.values.end(), row.begin(), row.end());
        v.push_back(bound);
    }
    void add(const sets::SetData &data, std::size_t offset) {
        const auto n = data.metadata()->set.dimension;
        if (offset > a.cols || n > a.cols - offset)
            bad("feedback.dimension", "H operand dimensions differ.");
        auto representation = data.representation();
        if (auto *h = std::get_if<sets::HRepresentation>(&representation)) {
            auto copy = [&](const numeric::MatrixView &m, const numeric::VectorView &v,
                            bool equal) {
                for (std::size_t i = 0; i < m.rows(); ++i) {
                    Vector row(a.cols, 0);
                    for (std::size_t j = 0; j < n; ++j)
                        row[offset + j] = m(i, j);
                    append(std::move(row), v[i], equal);
                }
            };
            copy(h->inequalities, h->upper_bounds, false);
            copy(h->equalities, h->equality_values, true);
        } else if (auto *point = std::get_if<sets::SingletonRepresentation>(&representation)) {
            for (std::size_t j = 0; j < n; ++j) {
                Vector row(a.cols, 0);
                row[offset + j] = 1;
                append(std::move(row), point->point[j], true);
            }
        } else if (std::holds_alternative<sets::EmptyRepresentation>(representation))
            append(Vector(a.cols, 0), -1);
        else if (!std::holds_alternative<sets::UniversalRepresentation>(representation))
            bad("feedback.representation",
                "Only closed H, singleton, empty and universal source sets are admitted.");
    }
    SetHandle finish(SetId id, const std::vector<std::string> &labels) {
        return take(sets::make_h({std::move(id), a.cols, labels},
                                 {take(numeric::snapshot(a)), take(numeric::snapshot_vector(b)),
                                  take(numeric::snapshot(e)), take(numeric::snapshot_vector(f))}))
            .as_handle();
    }
};
sets::SetData import(const SetHandle &set) { return take(sets::from_handle(set)); }
SetHandle materialize(const AdmissibleSet &set, SetId id, std::size_t n,
                      const std::vector<std::string> &labels) {
    Rows rows(n);
    if (auto *handle = std::get_if<SetHandle>(&set)) {
        auto data = import(*handle);
        if (!labels.empty() && data.metadata()->coordinate_labels != labels)
            bad("feedback.coordinates",
                "Source coordinate labels must match the authored state ordering.");
        rows.add(data, 0);
    } else if (auto *point = std::get_if<Singleton>(&set)) {
        if (point->point.size() != n)
            bad("feedback.initial", "Singleton dimension differs.");
        for (std::size_t j = 0; j < n; ++j) {
            Vector row(n, 0);
            row[j] = 1;
            rows.append(std::move(row), point->point[j], true);
        }
    } else if (std::holds_alternative<EmptySet>(set))
        rows.append(Vector(n, 0), -1);
    return rows.finish(std::move(id), labels);
}
struct Runner {
    const FeedbackGeometryDependencies &deps;
    const ExecutionContext &context;
    ProblemId problem;
    RequestId request;
    std::vector<SetId> source_ids;
    std::size_t stage{};
    std::size_t serial{};
    std::vector<GeometryReference> requests;
    std::vector<RequestProvenance> providers;
    std::vector<GeometryEvidence> lineage;
    std::vector<registry::LPQueryRecord> support_calls;
    std::vector<SupportBoundMethod> support_methods;
    std::vector<SupportBoundCertificate> support_certificates;
    std::vector<SetHandle> input_carriers;
    Runner(const FeedbackGeometryDependencies &d, const ExecutionContext &c, ProblemId p,
           RequestId r)
        : deps(d), context(c), problem(std::move(p)), request(std::move(r)) {}
    std::string id(const char *role) {
        return "feedback/" + request.value + "/" + std::to_string(stage) + "/" + role + "/" +
               std::to_string(serial++);
    }
    OperationResult operation(GeometryOperation op,
                              const registry::PreparedProvider<registry::GeometryPort> &provider,
                              const char *role) {
        if (!provider.provenance().actual)
            bad("feedback.provider", "Selected geometry provider is unresolved.");
        auto key = id(role);
        GeometryRequestIdentity identity{problem, {key}, {key + "/set"}};
        OperationRequest req{identity, provider.provenance().actual->id, std::move(op),
                             SetRelation::equivalent, Assurance::numerical};
        requests.push_back(geometry_reference(req));
        const auto &p = provider.provenance();
        providers.push_back({identity.request, p.port, p.requested.id, p.requested.version,
                             p.actual->id, p.actual->version});
        auto prep = provider.prepare(req);
        if (auto *e = std::get_if<registry::Rejection>(&prep))
            throw Failure{Unsupported{e->diagnostics}};
        auto workspace =
            std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prep)).create();
        auto result = std::get<0>(workspace)->run(context);
        if (auto *e = std::get_if<Unsupported>(&result))
            throw Failure{*e};
        if (auto *e = std::get_if<OperationStopped>(&result))
            throw Failure{*e};
        auto *out = std::get_if<OperationResult>(&result);
        if (!out)
            bad("feedback.operation", "Set operation returned a query result.");
        auto errors = check_geometry_evidence(out->evidence, req);
        if (!errors.empty())
            throw Failure{Unsupported{std::move(errors)}};
        lineage.push_back(out->evidence);
        return *out;
    }
    OperationResult intersect(const SetHandle &a, const SetHandle &b, const char *role) {
        return operation(Intersection{a, b}, deps.geometry.intersection, role);
    }
    OperationResult project(const SetHandle &a, std::vector<std::size_t> axes, const char *role) {
        return operation(Projection{a, std::move(axes)}, deps.geometry.forward.projection, role);
    }
    BoundedHAxisCover cover(const SetHandle &input, const Vector &lower, const Vector &upper) {
        auto data = import(input);
        auto repr = data.representation();
        auto *h = std::get_if<sets::HRepresentation>(&repr);
        if (!h)
            bad("feedback.cover", "Full-state intersection must be H.");
        const auto n = lower.size();
        BoundedHSupportInput query{{h->inequalities.rows(), n, {}},
                                   {},
                                   {h->equalities.rows(), n, {}},
                                   {},
                                   lower,
                                   upper,
                                   Vector(n, 0)};
        for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
            for (std::size_t j = 0; j < n; ++j)
                query.inequalities.values.push_back(h->inequalities(i, j));
            query.upper_bounds.push_back(h->upper_bounds[i]);
        }
        for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
            for (std::size_t j = 0; j < n; ++j)
                query.equalities.values.push_back(h->equalities(i, j));
            query.equality_values.push_back(h->equality_values[i]);
        }
        auto result =
            bounded_h_axis_cover(query, {problem, {id("support")}}, deps.support, context);
        if (auto *failure = std::get_if<BoundedHAxisFailure>(&result)) {
            support_calls.insert(support_calls.end(), failure->prefix.lp_calls.begin(),
                                 failure->prefix.lp_calls.end());
            support_methods.insert(support_methods.end(), failure->prefix.methods.begin(),
                                   failure->prefix.methods.end());
            for (auto &certificate : failure->prefix.certificates)
                certificate.input_set = input.id;
            support_certificates.insert(support_certificates.end(),
                                        failure->prefix.certificates.begin(),
                                        failure->prefix.certificates.end());
            std::visit(
                [](auto cause) {
                    using T = decltype(cause);
                    if constexpr (std::is_same_v<T, Diagnostics>)
                        throw Failure{Unsupported{std::move(cause)}};
                    else
                        throw Failure{std::move(cause)};
                },
                failure->cause);
        }
        auto output = std::get<BoundedHAxisCover>(std::move(result));
        for (auto &certificate : output.certificates)
            certificate.input_set = input.id;
        support_calls.insert(support_calls.end(), output.lp_calls.begin(), output.lp_calls.end());
        support_methods.insert(support_methods.end(), output.methods.begin(), output.methods.end());
        support_certificates.insert(support_certificates.end(), output.certificates.begin(),
                                    output.certificates.end());
        return output;
    }
    BoundedHAxisCover cover_frame(const SetHandle &input, const Matrix &frame, const Vector &lower,
                                  const Vector &upper) {
        auto data = import(input);
        auto repr = data.representation();
        auto *h = std::get_if<sets::HRepresentation>(&repr);
        if (!h)
            bad("feedback.cover", "Full-state intersection must be H.");
        const auto n = lower.size();
        BoundedHSupportInput query{{h->inequalities.rows(), n, {}},
                                   {},
                                   {h->equalities.rows(), n, {}},
                                   {},
                                   lower,
                                   upper,
                                   Vector(n, 0)};
        for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
            for (std::size_t j = 0; j < n; ++j)
                query.inequalities.values.push_back(h->inequalities(i, j));
            query.upper_bounds.push_back(h->upper_bounds[i]);
        }
        for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
            for (std::size_t j = 0; j < n; ++j)
                query.equalities.values.push_back(h->equalities(i, j));
            query.equality_values.push_back(h->equality_values[i]);
        }
        auto result = bounded_h_frame_cover(query, frame, {problem, {id("support")}}, deps.support,
                                           context);
        if (auto *failure = std::get_if<BoundedHAxisFailure>(&result)) {
            support_calls.insert(support_calls.end(), failure->prefix.lp_calls.begin(),
                                 failure->prefix.lp_calls.end());
            support_methods.insert(support_methods.end(), failure->prefix.methods.begin(),
                                   failure->prefix.methods.end());
            for (auto &certificate : failure->prefix.certificates)
                certificate.input_set = input.id;
            support_certificates.insert(support_certificates.end(),
                                        failure->prefix.certificates.begin(),
                                        failure->prefix.certificates.end());
            std::visit(
                [](auto cause) {
                    using T = decltype(cause);
                    if constexpr (std::is_same_v<T, Diagnostics>)
                        throw Failure{Unsupported{std::move(cause)}};
                    else
                        throw Failure{std::move(cause)};
                },
                failure->cause);
        }
        auto output = std::get<BoundedHAxisCover>(std::move(result));
        for (auto &certificate : output.certificates)
            certificate.input_set = input.id;
        support_calls.insert(support_calls.end(), output.lp_calls.begin(), output.lp_calls.end());
        support_methods.insert(support_methods.end(), output.methods.begin(), output.methods.end());
        support_certificates.insert(support_certificates.end(), output.certificates.begin(),
                                    output.certificates.end());
        return output;
    }
};
namespace exact_h = csl::synthesis::detail::exact_h;

double outward_lower(const exact_h::ExactRational &value, std::size_t max_bits) {
    const auto bracket = exact_h::bracket_binary64(value, max_bits);
    if (bracket.status == exact_h::Binary64BracketStatus::arithmetic_budget)
        throw Failure{
            OperationStopped{StopReason::resource_limit,
                             "Exact control bound comparison exceeded its arithmetic budget."}};
    if (bracket.status != exact_h::Binary64BracketStatus::finite)
        bad("feedback.control.bounds",
            "A finite binary64 control carrier could not be represented.");
    return bracket.lower;
}

struct ExactCancellation {
    const ExecutionContext &context;
    bool stop_requested() const {
        return context.cancellation.stop_requested() ||
               (context.deadline && std::chrono::steady_clock::now() >= *context.deadline);
    }
};

std::pair<Vector, Vector> explicit_bounds(const SetHandle &input,
                                          const ExecutionContext &context = {},
                                          bool *used_exact = nullptr) {
    auto data = import(input);
    auto repr = data.representation();
    const auto n = data.metadata()->set.dimension;
    Vector lo(n, -std::numeric_limits<double>::infinity()),
        hi(n, std::numeric_limits<double>::infinity());
    if (auto *singleton = std::get_if<sets::SingletonRepresentation>(&repr)) {
        for (std::size_t j = 0; j < n; ++j)
            lo[j] = hi[j] = singleton->point[j];
        return {lo, hi};
    }
    auto *h = std::get_if<sets::HRepresentation>(&repr);
    if (!h)
        bad("feedback.control.bounds", "Control set needs explicit finite H axis bounds.");
    for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
        std::size_t axis = n;
        for (std::size_t j = 0; j < n; ++j)
            if (h->inequalities(i, j) != 0) {
                if (axis != n) {
                    axis = n;
                    break;
                }
                axis = j;
            }
        if (axis == n)
            continue;
        const auto c = h->inequalities(i, axis), v = h->upper_bounds[i] / c;
        if (!std::isfinite(v))
            bad("feedback.control.bounds", "Control bound overflowed.");
        if (c > 0)
            hi[axis] =
                std::min(hi[axis], std::nextafter(v, std::numeric_limits<double>::infinity()));
        else
            lo[axis] =
                std::max(lo[axis], std::nextafter(v, -std::numeric_limits<double>::infinity()));
    }
    for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
        std::size_t axis = n;
        for (std::size_t j = 0; j < n; ++j)
            if (h->equalities(i, j) != 0) {
                if (axis != n) {
                    axis = n;
                    break;
                }
                axis = j;
            }
        if (axis == n)
            continue;
        const double value = h->equality_values[i] / h->equalities(i, axis);
        if (!std::isfinite(value))
            bad("feedback.control.bounds", "Control equality bound overflowed.");
        const double down = value == 0 && h->equality_values[i] == 0
                                ? 0
                                : std::nextafter(value, -std::numeric_limits<double>::infinity());
        const double up = value == 0 && h->equality_values[i] == 0
                              ? 0
                              : std::nextafter(value, std::numeric_limits<double>::infinity());
        lo[axis] = std::max(lo[axis], down);
        hi[axis] = std::min(hi[axis], up);
    }
    const bool needs_exact =
        std::any_of(lo.begin(), lo.end(), [](double x) { return !std::isfinite(x); }) ||
        std::any_of(hi.begin(), hi.end(), [](double x) { return !std::isfinite(x); });
    if (needs_exact) {
        if (used_exact)
            *used_exact = true;
        exact_h::Limits limits;
        std::vector<exact_h::Row> rows;
        for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
            Vector coefficients(n);
            for (std::size_t j = 0; j < n; ++j)
                coefficients[j] = h->inequalities(i, j);
            if (!exact_h::append_inequality(coefficients, h->upper_bounds[i], false,
                                            limits.max_integer_bits, rows))
                throw Failure{
                    OperationStopped{StopReason::resource_limit,
                                     "Exact control carrier row exceeds arithmetic limits."}};
        }
        for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
            Vector coefficients(n);
            for (std::size_t j = 0; j < n; ++j)
                coefficients[j] = h->equalities(i, j);
            if (!exact_h::append_equality(coefficients, h->equality_values[i],
                                          limits.max_integer_bits, rows))
                throw Failure{
                    OperationStopped{StopReason::resource_limit,
                                     "Exact control carrier equality exceeds arithmetic limits."}};
        }
        for (std::size_t j = 0; j < n; ++j)
            for (bool upper : {false, true}) {
                if (upper ? std::isfinite(hi[j]) : std::isfinite(lo[j]))
                    continue;
                Vector objective(n, 0);
                objective[j] = upper ? -1 : 1;
                auto minimum = exact_h::minimize_linear(rows, n, objective, 0, limits,
                                                        ExactCancellation{context});
                if (minimum.state == exact_h::LinearMinimumState::cancelled) {
                    const auto reason = context.cancellation.stop_requested()
                                            ? StopReason::cancelled
                                            : StopReason::deadline_expired;
                    throw Failure{
                        OperationStopped{reason, "Exact control carrier calculation interrupted."}};
                }
                if (minimum.state == exact_h::LinearMinimumState::unsupported)
                    throw Failure{
                        OperationStopped{StopReason::resource_limit,
                                         "Exact control carrier limits: " + minimum.reason}};
                if (minimum.state != exact_h::LinearMinimumState::minimum)
                    bad("feedback.control.bounds",
                        "No finite control carrier was established; no source infeasibility is asserted.");
                const double lower = outward_lower(minimum.value, limits.max_integer_bits);
                if (upper)
                    hi[j] = -lower;
                else
                    lo[j] = lower;
            }
    }
    for (std::size_t j = 0; j < n; ++j)
        if (!std::isfinite(lo[j]) || !std::isfinite(hi[j]) || lo[j] > hi[j])
            bad("feedback.control.bounds",
                "A finite nonempty outer control carrier was not established.");
    return {lo, hi};
}
SetHandle axis_h(const Vector &lo, const Vector &hi, SetId id,
                 const std::vector<std::string> &labels) {
    auto result = axis_enclosure(FeedbackFamily::box, std::move(id), lo, hi, labels);
    if (auto *error = std::get_if<Diagnostics>(&result))
        throw Failure{Unsupported{*error}};
    return std::get<FeedbackHMembership>(std::get<FeedbackMembership>(std::move(result))).set;
}
FeedbackMembership shape(FeedbackFamily family, const SetHandle &h, const Vector &lo,
                         const Vector &hi, SetId id, const std::vector<std::string> &labels) {
    if (family == FeedbackFamily::polytope)
        return FeedbackHMembership{h, {}, {}};
    auto result = axis_enclosure(family, std::move(id), lo, hi, labels);
    if (auto *error = std::get_if<Diagnostics>(&result))
        throw Failure{Unsupported{*error}};
    return std::get<FeedbackMembership>(std::move(result));
}
FeedbackSet record(Runner &r, FeedbackFamily family, FeedbackMembership membership,
                   const std::vector<StrictCoordinateLowerBound> &strict,
                   std::vector<SetId> sources) {
    sources.insert(sources.end(), r.source_ids.begin(), r.source_ids.end());
    SetId output_id = std::holds_alternative<FeedbackHMembership>(membership)
                          ? std::get<FeedbackHMembership>(membership).set.id
                          : SetId{r.id("family-result")};
    FeedbackSet result{
        family,
        FeedbackScope::forward_relevant_from_observation,
        SetRelation::outer,
        Assurance::numerical,
        std::move(membership),
        strict,
        std::move(sources),
        r.requests,
        r.providers,
        r.support_calls,
        r.support_methods,
        r.support_certificates,
        {"H embeddings of generator and ellipsoid families are coordinate outer covers; family clipping uses an axis cover when needed."},
        r.lineage,
        std::move(output_id),
        r.input_carriers};
    r.requests.clear();
    r.providers.clear();
    r.support_calls.clear();
    r.support_methods.clear();
    r.support_certificates.clear();
    r.input_carriers.clear();
    r.lineage.clear();
    return result;
}
} // namespace
namespace {
std::pair<Vector, Vector> membership_bounds(const FeedbackMembership &member) {
    if (auto *h = std::get_if<FeedbackHMembership>(&member)) {
        if (h->parallelotope_frame && h->parallelotope_frame_bounds) {
            const auto &frame = *h->parallelotope_frame;
            const auto &[frame_lo, frame_hi] = *h->parallelotope_frame_bounds;
            const auto n = frame_lo.size();
            if (frame.rows == n && frame.cols == n && frame_hi.size() == n) {
                Vector lo(n), hi(n);
                const auto inf = std::numeric_limits<double>::infinity();
                for (std::size_t i = 0; i < n; ++i) {
                    double center = 0, radius = 0;
                    for (std::size_t j = 0; j < n; ++j) {
                        const auto q = frame.values[i * n + j];
                        const auto mid = frame_lo[j] / 2 + frame_hi[j] / 2;
                        const auto half = std::max(mid - frame_lo[j], frame_hi[j] - mid);
                        center = std::nextafter(center + std::nextafter(q * mid, inf), inf);
                        radius = std::nextafter(
                            radius + std::nextafter(std::abs(q) * half, inf), inf);
                    }
                    lo[i] = std::nextafter(center - radius, -inf);
                    hi[i] = std::nextafter(center + radius, inf);
                }
                return {lo, hi};
            }
        }
        return explicit_bounds(h->set);
    }
    Vector center;
    Matrix factor;
    bool ellipsoid = false;
    if (auto *z = std::get_if<FeedbackZonotopeMembership>(&member)) {
        center = z->center;
        factor = z->generators;
    } else {
        const auto &e = std::get<FeedbackEllipsoidMembership>(member);
        center = e.center;
        factor = e.factor;
        ellipsoid = true;
    }
    const auto n = center.size();
    Vector lo(n), hi(n);
    const auto inf = std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < n; ++i) {
        double radius = 0;
        for (std::size_t j = 0; j < factor.cols; ++j) {
            double v = std::abs(factor.values[i * factor.cols + j]);
            if (ellipsoid)
                v = std::nextafter(v * v, inf);
            radius = std::nextafter(radius + v, inf);
        }
        if (ellipsoid)
            radius = std::nextafter(std::sqrt(radius), inf);
        lo[i] = std::nextafter(center[i] - radius, -inf);
        hi[i] = std::nextafter(center[i] + radius, inf);
        if (!std::isfinite(lo[i]) || !std::isfinite(hi[i]))
            bad("feedback.shape.bounds", "Family support overflowed.");
    }
    return {lo, hi};
}
bool box_inside(const SetHandle &source, const Vector &lo, const Vector &hi) {
    auto data = import(source);
    auto repr = data.representation();
    auto *h = std::get_if<sets::HRepresentation>(&repr);
    if (!h || h->equalities.rows() != 0)
        return false;
    for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
        double total = 0;
        for (std::size_t j = 0; j < lo.size(); ++j) {
            const auto c = h->inequalities(i, j);
            if (c == 0)
                continue;
            const auto product = c * (c > 0 ? hi[j] : lo[j]);
            total = std::nextafter(
                total + std::nextafter(product, std::numeric_limits<double>::infinity()),
                std::numeric_limits<double>::infinity());
        }
        if (!std::isfinite(total) || total > h->upper_bounds[i])
            return false;
    }
    return true;
}
FeedbackMembership propagate_family(FeedbackFamily family, const FeedbackMembership &current,
                                    const model::DynamicsStage &dynamics, const Vector &control_lo,
                                    const Vector &control_hi, SetId id,
                                    const std::vector<std::string> &labels,
                                    const ExecutionContext &context, std::size_t stage,
                                    std::size_t generator_limit) {
    BoxStage controls{control_lo, control_hi};
    if (family == FeedbackFamily::zonotope) {
        const auto &z = std::get<FeedbackZonotopeMembership>(current);
        FinitePlanZonotopeTrace::Stage state{z.center, z.generators, z.factors};
        auto uz = axis_enclosure(FeedbackFamily::zonotope, {id.value + "/controls"}, control_lo,
                                 control_hi, {});
        if (auto *e = std::get_if<Diagnostics>(&uz))
            throw Failure{Unsupported{*e}};
        const auto &u = std::get<FeedbackZonotopeMembership>(std::get<FeedbackMembership>(uz));
        auto out = propagate_existential_control_zonotope(
            dynamics, state, {u.center, u.generators, u.factors}, generator_limit, context, stage);
        if (auto *e = std::get_if<Unsupported>(&out))
            throw Failure{*e};
        if (auto *e = std::get_if<OperationStopped>(&out))
            throw Failure{*e};
        auto next = std::get<FinitePlanZonotopeTrace::Stage>(std::move(out));
        return FeedbackZonotopeMembership{std::move(next.center), std::move(next.generators),
                                          std::move(next.factors)};
    }
    if (family == FeedbackFamily::ellipsoid) {
        const auto &e = std::get<FeedbackEllipsoidMembership>(current);
        Vector radii(e.center.size());
        for (std::size_t i = 0; i < radii.size(); ++i)
            radii[i] = e.factor.values[i * e.factor.cols + i];
        auto out =
            propagate_existential_control_ellipsoid(dynamics, {e.center, radii}, controls, context);
        if (auto *v = std::get_if<Unsupported>(&out))
            throw Failure{*v};
        if (auto *v = std::get_if<OperationStopped>(&out))
            throw Failure{*v};
        auto next = std::get<FinitePlanEllipsoidTrace::Stage>(std::move(out));
        Matrix factor{next.center.size(), next.center.size(),
                      Vector(next.center.size() * next.center.size(), 0)};
        for (std::size_t i = 0; i < next.center.size(); ++i)
            factor.values[i * factor.cols + i] = next.radii[i];
        return FeedbackEllipsoidMembership{std::move(next.center), std::move(factor)};
    }
    const auto [lo, hi] = membership_bounds(current);
    auto out = propagate_existential_control_box(dynamics, {lo, hi}, controls, context);
    if (auto *v = std::get_if<Unsupported>(&out))
        throw Failure{*v};
    if (auto *v = std::get_if<OperationStopped>(&out))
        throw Failure{*v};
    auto box = std::get<BoxStage>(std::move(out));
    auto enclosure = axis_enclosure(family, std::move(id), box.lower, box.upper, labels);
    if (auto *v = std::get_if<Diagnostics>(&enclosure))
        throw Failure{Unsupported{*v}};
    return std::get<FeedbackMembership>(std::move(enclosure));
}
Matrix copy_matrix(const numeric::MatrixView &view) {
    Matrix out{view.rows(), view.cols(), {}};
    for (std::size_t i = 0; i < view.rows(); ++i)
        for (std::size_t j = 0; j < view.cols(); ++j)
            out.values.push_back(view(i, j));
    return out;
}
namespace enclosure = csl::synthesis::detail::exact_h_enclosure;
namespace rational = csl::synthesis::detail::exact_rational;

[[noreturn]] void exact_history_limit(std::string message) {
    throw Failure{OperationStopped{StopReason::resource_limit, std::move(message)}};
}

void check_exact_history_stop(const ExecutionContext &context) {
    if (context.cancellation.stop_requested())
        throw Failure{
            OperationStopped{StopReason::cancelled, "Exact history geometry was cancelled."}};
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        throw Failure{OperationStopped{StopReason::deadline_expired,
                                       "Exact history geometry reached its deadline."}};
}

void preflight_exact_history(std::size_t n, std::size_t m, std::size_t horizon,
                             const std::vector<AdmissibleSet> &states,
                             const std::vector<AdmissibleSet> &controls,
                             const SetHandle &terminal) {
    const exact_h::Limits limits;
    if (n > limits.max_variables || m > limits.max_variables ||
        horizon > (limits.max_variables - n) / (n + m))
        exact_history_limit("The original history exceeds the exact projection dimension limit.");
    std::size_t remaining_rows = limits.max_rows - n * (horizon + 1);
    const auto charge = [&](std::size_t count) {
        if (count > remaining_rows)
            exact_history_limit("The exact history relation exceeded the row limit.");
        remaining_rows -= count;
    };
    const auto check = [&](const AdmissibleSet &set) {
        if (const auto *handle = std::get_if<SetHandle>(&set)) {
            const auto data = import(*handle);
            const auto representation = data.representation();
            if (const auto *h = std::get_if<sets::HRepresentation>(&representation)) {
                charge(h->inequalities.rows());
                charge(h->equalities.rows());
            } else if (const auto *singleton =
                           std::get_if<sets::SingletonRepresentation>(&representation)) {
                charge(singleton->point.size());
            } else if (std::holds_alternative<sets::EmptyRepresentation>(representation)) {
                charge(1);
            }
        } else if (const auto *singleton = std::get_if<Singleton>(&set)) {
            charge(singleton->point.size());
        } else if (std::holds_alternative<EmptySet>(set)) {
            charge(1);
        }
    };
    for (const auto &state : states)
        check(state);
    for (const auto &control : controls)
        check(control);
    check(AdmissibleSet{terminal});
}

enclosure::Interval exact_interval(double lo, double hi, enclosure::Budget &budget) {
    enclosure::Interval interval;
    if (!rational::from_binary64(lo, interval.lower, budget) ||
        !rational::from_binary64(hi, interval.upper, budget))
        exact_history_limit("An exact history coordinate bound exceeded the arithmetic budget.");
    return interval;
}

std::vector<enclosure::Interval> exact_successor_box(const model::DynamicsStage &dynamics,
                                                     std::span<const enclosure::Interval> states,
                                                     std::span<const enclosure::Interval> controls,
                                                     enclosure::Budget &budget) {
    std::vector<enclosure::Interval> result;
    result.reserve(states.size());
    for (std::size_t i = 0; i < states.size(); ++i) {
        auto interval = exact_interval(dynamics.offset[i], dynamics.offset[i], budget);
        for (std::size_t j = 0; j < states.size(); ++j)
            if (!enclosure::accumulate_scaled_interval(interval, dynamics.A(i, j), states[j],
                                                       budget))
                exact_history_limit("Exact affine state bounds exceeded the arithmetic budget.");
        for (std::size_t j = 0; j < controls.size(); ++j)
            if (!enclosure::accumulate_scaled_interval(interval, dynamics.B(i, j), controls[j],
                                                       budget))
                exact_history_limit("Exact affine control bounds exceeded the arithmetic budget.");
        result.push_back(std::move(interval));
    }
    return result;
}

std::optional<std::vector<enclosure::Interval>> exact_unit_normal_box(const SetHandle &input,
                                                                      enclosure::Budget &budget) {
    const auto data = import(input);
    const auto representation = data.representation();
    const auto *h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->equalities.rows() != 0)
        return std::nullopt;

    const auto dimension = h->inequalities.cols();
    Vector lower(dimension, -std::numeric_limits<double>::infinity());
    Vector upper(dimension, std::numeric_limits<double>::infinity());
    for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        std::size_t axis = dimension;
        double sign = 0;
        for (std::size_t column = 0; column < dimension; ++column) {
            const auto coefficient = h->inequalities(row, column);
            if (coefficient == 0)
                continue;
            if (axis != dimension || (coefficient != 1 && coefficient != -1))
                return std::nullopt;
            axis = column;
            sign = coefficient;
        }
        if (axis == dimension)
            return std::nullopt;
        if (sign > 0)
            upper[axis] = std::min(upper[axis], h->upper_bounds[row]);
        else
            lower[axis] = std::max(lower[axis], -h->upper_bounds[row]);
    }

    std::vector<enclosure::Interval> box;
    box.reserve(dimension);
    for (std::size_t axis = 0; axis < dimension; ++axis) {
        if (!std::isfinite(lower[axis]) || !std::isfinite(upper[axis]) || lower[axis] > upper[axis])
            return std::nullopt;
        box.push_back(exact_interval(lower[axis], upper[axis], budget));
    }
    return box;
}

double exact_prefix_support(std::span<const model::DynamicsStage> dynamics,
                            std::span<const std::vector<enclosure::Interval>> controls,
                            std::span<const double> initial, std::span<const double> normal,
                            const ExecutionContext &context) {
    enclosure::Budget budget;
    const auto decode = [&](double value) {
        enclosure::Rational result;
        if (!rational::from_binary64(value, result, budget))
            exact_history_limit("Exact support input exceeded the arithmetic budget.");
        return result;
    };
    const auto accumulate = [&](enclosure::Rational &sum, const enclosure::Rational &left,
                                const enclosure::Rational &right) {
        enclosure::Rational value;
        if (!rational::multiply(left, right, value, budget) ||
            !rational::add(sum, value, sum, budget))
            exact_history_limit("Exact support evaluation exceeded the arithmetic budget.");
    };
    std::vector<enclosure::Rational> direction;
    for (const auto value : normal)
        direction.push_back(decode(value));
    enclosure::Rational support;
    for (std::size_t k = dynamics.size(); k > 0; --k) {
        check_exact_history_stop(context);
        const auto &stage = dynamics[k - 1];
        std::vector<enclosure::Rational> prior(direction.size());
        for (std::size_t i = 0; i < direction.size(); ++i) {
            accumulate(support, direction[i], decode(stage.offset[i]));
            for (std::size_t j = 0; j < direction.size(); ++j)
                accumulate(prior[j], direction[i], decode(stage.A(i, j)));
        }
        for (std::size_t j = 0; j < controls[k - 1].size(); ++j) {
            enclosure::Rational coefficient;
            for (std::size_t i = 0; i < direction.size(); ++i)
                accumulate(coefficient, direction[i], decode(stage.B(i, j)));
            const auto &interval = controls[k - 1][j];
            accumulate(support, coefficient,
                       coefficient.numerator.negative ? interval.lower : interval.upper);
        }
        direction = std::move(prior);
    }
    for (std::size_t i = 0; i < initial.size(); ++i)
        accumulate(support, direction[i], decode(initial[i]));
    const auto bracket = exact_h::bracket_binary64(
        {support.numerator, support.denominator, support.binary_exponent}, budget.max_integer_bits);
    if (bracket.status != exact_h::Binary64BracketStatus::finite)
        exact_history_limit("Exact support could not be enclosed in binary64.");
    return bracket.upper;
}

bool affine_box_history_geometry(FeedbackGeometry &output, Runner &run,
                                 const model::LinearSystem &system,
                                 const std::vector<SetHandle> &states,
                                 const std::vector<SetHandle> &controls, const SetHandle &terminal,
                                 const Vector &initial, const std::vector<std::string> &labels,
                                 const std::vector<StrictCoordinateLowerBound> &strict,
                                 StageIndex &active) {
    const auto unrestricted = [](const SetHandle &set) {
        const auto data = import(set);
        const auto representation = data.representation();
        const auto *h = std::get_if<sets::HRepresentation>(&representation);
        return h && h->inequalities.rows() == 0 && h->equalities.rows() == 0;
    };
    if (!unrestricted(terminal) || !std::all_of(states.begin(), states.end(), unrestricted))
        return false;

    enclosure::Budget budget;
    std::vector<std::vector<enclosure::Interval>> boxes;
    std::vector<model::DynamicsStage> stages;
    for (std::size_t k = 0; k < controls.size(); ++k) {
        check_exact_history_stop(run.context);
        auto box = exact_unit_normal_box(controls[k], budget);
        if (!box)
            return false;
        boxes.push_back(std::move(*box));
        stages.push_back(take<model::DynamicsStage>(system.stage({k})));
    }

    const auto n = initial.size();
    std::vector<Rows> marginals;
    for (std::size_t k = 0; k <= stages.size(); ++k) {
        active = {k};
        run.stage = k;
        Rows rows(n);
        const auto add_support = [&](Vector normal) {
            const auto bound =
                exact_prefix_support(std::span{stages}.first(k), std::span{boxes}.first(k), initial,
                                     normal, run.context);
            rows.append(std::move(normal), bound);
        };
        for (std::size_t axis = 0; axis < n; ++axis) {
            Vector normal(n, 0);
            normal[axis] = -1;
            add_support(normal);
            const auto lower = -rows.b.back();
            for (const auto &predicate : strict)
                if (predicate.coordinate == axis && lower <= predicate.lower_bound)
                    return false;
            normal[axis] = 1;
            add_support(std::move(normal));
        }
        for (std::size_t axis = 0; axis + 1 < n; axis += 2) {
            Vector normal(n, 0);
            normal[axis] = 1;
            normal[axis + 1] = 1;
            add_support(normal);
            normal[axis] = -1;
            normal[axis + 1] = -1;
            add_support(std::move(normal));
        }
        marginals.push_back(std::move(rows));
    }

    for (std::size_t k = 0; k < marginals.size(); ++k) {
        active = {k};
        run.stage = k;
        auto &stage = output.stages[k];
        const auto assign = [&](const char *role, const char *statement,
                                std::optional<OperationResult> &geometry,
                                std::optional<FeedbackSet> &member) {
            const auto key = run.id(role);
            auto set = marginals[k].finish({key + "/set"}, labels);
            GeometryEvidence evidence{
                {{run.problem, {key}, {key + "/mathematical-marginal"}}, run.source_ids},
                GeometryClaimScope::set_relation,
                SymbolicArgument{statement,
                                 "Exact affine input-box support and outward binary64 rounding"},
                {"The closed state and terminal sets are universal.",
                 "All stagewise strict source predicates hold on the affine input histories."},
                {}};
            run.requests.push_back(evidence.reference);
            run.lineage.push_back(evidence);
            geometry = OperationResult{set, SetRelation::outer, std::move(evidence)};
            member = record(run, FeedbackFamily::polytope, FeedbackHMembership{set, {}, {}}, strict,
                            {set.id});
            member->assurance = Assurance::validated;
            member->construction = {statement};
        };
        assign("affine-box-forward", "Outer H template of the affine forward marginal.",
               stage.forward_h, stage.forward);
        assign("affine-box-backward",
               "Every forward history has an admissible continuation to the universal terminal.",
               stage.backward_h, stage.backward);
        assign("affine-box-intersection",
               "The forward-relevant intersection equals the affine forward marginal.",
               stage.intersection_h, stage.intersection);
        stage.forward_embedding_h = stage.forward_h->output;
        stage.backward_embedding_h = stage.backward_h->output;
    }
    return true;
}

OperationResult certified_history_projection(Runner &run, const Rows &source, std::size_t first,
                                             std::span<const enclosure::Interval> box,
                                             const std::vector<std::string> &labels,
                                             const char *role, std::vector<SetId> inputs) {
    const auto dimension = box.size();
    const auto variables = source.a.cols;
    exact_h::Limits limits;
    if (source.a.rows > limits.max_rows || source.e.rows > limits.max_rows - source.a.rows)
        exact_history_limit("The exact history relation exceeded the row limit.");
    std::vector<exact_h::Row> bounds, equations;
    const auto copy = [&](const Matrix &matrix, const Vector &rhs, std::vector<exact_h::Row> &out) {
        out.reserve(matrix.rows);
        for (std::size_t i = 0; i < matrix.rows; ++i) {
            check_exact_history_stop(run.context);
            const auto start = matrix.values.begin() + static_cast<std::ptrdiff_t>(i * variables);
            const auto selected = start + static_cast<std::ptrdiff_t>(first);
            const auto after = selected + static_cast<std::ptrdiff_t>(dimension);
            Vector row;
            row.reserve(variables);
            row.insert(row.end(), selected, after);
            row.insert(row.end(), start, selected);
            row.insert(row.end(), after, start + static_cast<std::ptrdiff_t>(variables));
            if (!exact_h::append_inequality(row, rhs[i], false, limits.max_integer_bits, out))
                exact_history_limit("An exact history row exceeded the arithmetic budget.");
        }
    };
    copy(source.a, source.b, bounds);
    copy(source.e, source.f, equations);
    std::vector<exact_h::Row> projected;
    const auto result =
        exact_h::feasible(std::move(bounds), variables, limits, ExactCancellation{run.context},
                          dimension, &projected, std::move(equations));
    if (result.state == exact_h::FeasibilityState::cancelled) {
        const auto reason = run.context.cancellation.stop_requested()
                                ? StopReason::cancelled
                                : StopReason::deadline_expired;
        throw Failure{OperationStopped{reason, result.reason}};
    }
    if (result.state == exact_h::FeasibilityState::unsupported)
        exact_history_limit(result.reason);

    Rows rows(dimension);
    if (result.state == exact_h::FeasibilityState::infeasible)
        rows.append(Vector(dimension, 0), -1);
    enclosure::Budget budget;
    for (const auto &row : projected) {
        check_exact_history_stop(run.context);
        auto enclosed = enclosure::enclose_upper_row(row, box, budget);
        if (!enclosed)
            exact_history_limit("The exact history projection could not be enclosed in binary64.");
        rows.append(std::move(enclosed->coefficients), enclosed->bound);
    }
    check_exact_history_stop(run.context);
    const auto key = run.id(role);
    auto set = rows.finish({key + "/set"}, labels);
    GeometryEvidence evidence{
        {{run.problem, {key}, {key + "/mathematical-projection"}}, std::move(inputs)},
        GeometryClaimScope::set_relation,
        SymbolicArgument{
            "Exact equality substitution followed by Fourier–Motzkin projection",
            "Exact interval bounds and normal-error allowance before outward binary64 rounding"},
        {"The original stored affine dynamics and closed-H source constraints define the ideal set.",
         "Strict source predicates remain attached separately."},
        {}};
    run.requests.push_back(evidence.reference);
    run.lineage.push_back(evidence);
    return {std::move(set), SetRelation::outer, std::move(evidence)};
}

void certified_history_geometry(FeedbackGeometry &output, Runner &run,
                                const model::LinearSystem &system,
                                const std::vector<SetHandle> &states,
                                const std::vector<SetHandle> &controls, const SetHandle &terminal,
                                const Vector &initial, const std::vector<std::string> &labels,
                                const std::vector<StrictCoordinateLowerBound> &strict,
                                StageIndex &active, FeedbackGeometryPhase &phase) {
    const auto n = initial.size(), m = system.dimensions().control, horizon = system.horizon();
    const auto state_variables = n * (horizon + 1);
    Rows history(state_variables + m * horizon);
    std::vector<std::vector<enclosure::Interval>> boxes(horizon + 1);
    enclosure::Budget budget;
    for (std::size_t i = 0; i < n; ++i) {
        Vector row(history.a.cols, 0);
        row[i] = 1;
        history.append(std::move(row), initial[i], true);
        boxes.front().push_back(exact_interval(initial[i], initial[i], budget));
    }
    const auto save = [&](const OperationResult &result, std::vector<SetId> inputs,
                          const char *construction) {
        inputs.push_back(result.output.id);
        auto member = record(run, FeedbackFamily::polytope,
                             FeedbackHMembership{result.output, {}, {}},
                             strict, std::move(inputs));
        member.assurance = Assurance::validated;
        member.construction = {construction};
        return member;
    };
    std::vector<SetId> inputs;
    for (std::size_t k = 0; k <= horizon; ++k) {
        run.stage = k;
        active = {k};
        auto &stage = output.stages[k];
        history.add(import(states[k]), k * n);
        inputs.push_back(states[k].id);
        if (k > 0) {
            const auto dynamics = take<model::DynamicsStage>(system.stage({k - 1}));
            const auto control_offset = state_variables + (k - 1) * m;
            history.add(import(controls[k - 1]), control_offset);
            inputs.push_back(controls[k - 1].id);
            const auto [lo, hi] = explicit_bounds(controls[k - 1], run.context);
            std::vector<enclosure::Interval> control_box;
            for (std::size_t j = 0; j < m; ++j)
                control_box.push_back(exact_interval(lo[j], hi[j], budget));
            boxes[k] = exact_successor_box(dynamics, boxes[k - 1], control_box, budget);
            for (std::size_t i = 0; i < n; ++i) {
                Vector row(history.a.cols, 0);
                for (std::size_t j = 0; j < n; ++j)
                    row[(k - 1) * n + j] = -dynamics.A(i, j);
                for (std::size_t j = 0; j < m; ++j)
                    row[control_offset + j] = -dynamics.B(i, j);
                row[k * n + i] = 1;
                history.append(std::move(row), dynamics.offset[i], true);
            }
        }
        stage.forward_h = certified_history_projection(run, history, k * n, boxes[k], labels,
                                                       "whole-history-prefix", inputs);
        stage.forward_embedding_h = stage.forward_h->output;
        stage.forward = save(*stage.forward_h, inputs,
                             "Projection of the original feasible prefix onto this state.");
    }

    history.add(import(terminal), horizon * n);
    inputs.push_back(terminal.id);
    for (std::size_t remaining = horizon + 1; remaining > 0; --remaining) {
        const auto k = remaining - 1;
        active = {k};
        run.stage = k;
        phase = k == horizon ? FeedbackGeometryPhase::terminal : FeedbackGeometryPhase::backward;
        auto &stage = output.stages[k];
        stage.backward_h = certified_history_projection(run, history, k * n, boxes[k], labels,
                                                        "whole-history-terminal-feasible", inputs);
        stage.backward_embedding_h = stage.backward_h->output;
        stage.backward =
            save(*stage.backward_h, inputs,
                 "Projection of the original terminal-feasible history onto this state.");
        phase = FeedbackGeometryPhase::intersection;
        // Every terminal-feasible history satisfies its original forward prefix.
        Rows overlap(n);
        overlap.add(import(stage.backward_h->output), 0);
        const auto key = run.id("whole-history-overlap");
        auto set = overlap.finish({key + "/set"}, labels);
        GeometryEvidence evidence{
            {{run.problem, {key}, {key + "/mathematical-intersection"}},
             {stage.forward->id, stage.backward->id}},
            GeometryClaimScope::set_relation,
            SymbolicArgument{"Terminal-feasible histories satisfy every original prefix",
                             "The outer backward marginal also encloses the exact intersection."},
            {},
            {}};
        run.requests.push_back(evidence.reference);
        run.lineage.push_back(evidence);
        stage.intersection_h =
            OperationResult{std::move(set), SetRelation::outer, std::move(evidence)};
        stage.intersection = save(
            *stage.intersection_h, {stage.forward->id, stage.backward->id},
            "Terminal-feasible histories already satisfy the forward prefix and define the exact overlap.");
    }
}

} // namespace

FeedbackGeometryOutcome feedback_geometry(const problem::ResolvedProblem &resolved,
                                          RequestId request, const SetHandle &terminal,
                                          FeedbackFamily family,
                                          const std::vector<StrictCoordinateLowerBound> &strict,
                                          const FeedbackGeometryDependencies &deps,
                                          const ExecutionContext &context) {
    return feedback_geometry(resolved, std::move(request), terminal, family, strict, deps,
                             FeedbackGeometryOptions{}, context);
}

FeedbackGeometryOutcome feedback_geometry(const problem::ResolvedProblem &resolved,
                                          RequestId request, const SetHandle &terminal,
                                          FeedbackFamily family,
                                          const std::vector<StrictCoordinateLowerBound> &strict,
                                          const FeedbackGeometryDependencies &deps,
                                          FeedbackPolytopeHistory polytope_history,
                                          const ExecutionContext &context) {
    return feedback_geometry(resolved, std::move(request), terminal, family, strict, deps,
                             FeedbackGeometryOptions{polytope_history,
                                                     ParallelotopeFrameRule::axis},
                             context);
}

FeedbackGeometryOutcome feedback_geometry(const problem::ResolvedProblem &resolved,
                                          RequestId request, const SetHandle &terminal,
                                          FeedbackFamily family,
                                          const std::vector<StrictCoordinateLowerBound> &strict,
                                          const FeedbackGeometryDependencies &deps,
                                          const FeedbackGeometryOptions &options,
                                          const ExecutionContext &context) {
    const auto polytope_history = options.polytope_history;
    FeedbackGeometry output{
        resolved.identity(), request, family, FeedbackScope::forward_relevant_from_observation, {}};
    FeedbackGeometryPhase phase = FeedbackGeometryPhase::forward;
    StageIndex active{0};
    Runner run{deps, context, resolved.identity(), request};
    try {
        auto source = resolved.description();
        auto system = resolved.model();
        auto dims = system.dimensions();
        const auto n = dims.state, m = dims.control, horizon = system.horizon();
        if (request.value.empty() || n == 0 || dims.external != 0 ||
            source->states.size() != horizon + 1 ||
            source->model->dynamics.time_domain != TimeDomain::discrete ||
            source->information != InformationPattern::nominal_open_loop ||
            !std::holds_alternative<KnownInitial>(source->initial))
            bad("feedback.profile",
                "Known initial state, positive state dimension, matching horizon and no external port are required.");
        auto controls_desc = resolved.controls().description();
        auto *continuous = std::get_if<ContinuousDomain>(controls_desc.get());
        if (!continuous || continuous->stages.size() != horizon)
            bad("feedback.controls", "A continuous control set is required for every transition.");
        std::vector<std::string> labels;
        if (auto *state = std::get_if<SetHandle>(&source->states.front()))
            labels = import(*state).metadata()->coordinate_labels;
        for (const auto &predicate : strict)
            if (predicate.coordinate >= n || !std::isfinite(predicate.lower_bound))
                bad("feedback.strict-domain", "Strict source predicate is invalid.");
        if (polytope_history == FeedbackPolytopeHistory::certified_whole_history) {
            check_exact_history_stop(context);
            if (family != FeedbackFamily::polytope)
                bad("feedback.polytope-history",
                    "Certified whole-history projection requires the polytope family.");
            preflight_exact_history(n, m, horizon, source->states, continuous->stages, terminal);
        }
        // Frame shaping for the forward, backward and intersection
        // enclosures. A fixed rule uses its single candidate; the support
        // selected rule covers both candidates and keeps the smaller
        // factor-width product, which for orthonormal frames is the
        // enclosure volume. Ties retain the axis candidate.
        const auto framed_member =
            [&](const SetHandle &input, const Vector &lo, const Vector &hi, const char *role)
            -> std::optional<std::pair<FeedbackMembership, std::string>> {
            if (family != FeedbackFamily::parallelotope ||
                options.parallelotope_frame == ParallelotopeFrameRule::axis)
                return std::nullopt;
            const auto candidates =
                parallelotope_frame_candidates(options.parallelotope_frame, n);
            std::vector<Vector> lowers, uppers;
            std::vector<double> excess;
            for (const auto &candidate : candidates) {
                const auto cover = run.cover_frame(input, candidate.matrix, lo, hi);
                lowers.push_back(cover.lower);
                uppers.push_back(cover.upper);
                double product = 1;
                for (std::size_t i = 0; i < cover.lower.size(); ++i) {
                    const auto width = cover.upper[i] - cover.lower[i];
                    if (!std::isfinite(width)) {
                        product = std::numeric_limits<double>::infinity();
                        break;
                    }
                    product *= width;
                }
                excess.push_back(product);
            }
            const auto selected = select_parallelotope_frame(excess);
            const auto &frame = candidates[selected].matrix;
            auto shaped =
                frame_enclosure({run.id(role)}, frame, lowers[selected], uppers[selected], labels);
            if (auto *error = std::get_if<Diagnostics>(&shaped))
                throw Failure{Unsupported{*error}};
            std::string note;
            if (options.parallelotope_frame == ParallelotopeFrameRule::support_selected) {
                note = "selected ";
                note += parallelotope_frame_rule_name(candidates[selected].rule);
                note += " by factor-width products axis=";
                note += std::to_string(excess[0]);
                note += " fixed-rotation-45=";
                note += std::to_string(excess[1]);
            }
            return std::make_pair(std::get<FeedbackMembership>(std::move(shaped)), std::move(note));
        };
        std::vector<SetHandle> states, controls;
        for (const auto &item : source->states)
            if (const auto *h = std::get_if<SetHandle>(&item))
                run.source_ids.push_back(h->id);
        for (const auto &item : continuous->stages)
            if (const auto *h = std::get_if<SetHandle>(&item))
                run.source_ids.push_back(h->id);
        run.source_ids.push_back(terminal.id);
        for (std::size_t k = 0; k <= horizon; ++k)
            states.push_back(materialize(source->states[k], {run.id("source-state")}, n, labels));
        for (std::size_t k = 0; k < horizon; ++k)
            controls.push_back(
                materialize(continuous->stages[k], {run.id("source-control")}, m, {}));
        auto terminal_h =
            materialize(AdmissibleSet{terminal}, {run.id("source-terminal")}, n, labels);
        auto initial = std::get<KnownInitial>(source->initial).point;
        if (initial.size() != n ||
            !std::all_of(initial.begin(), initial.end(), [](double x) { return std::isfinite(x); }))
            bad("feedback.initial", "Finite observed state of the authored dimension is required.");
        output.stages.reserve(horizon + 1);
        for (std::size_t k = 0; k <= horizon; ++k) {
            FeedbackGeometryStage stage;
            stage.stage = {k};
            stage.coordinates.resize(n);
            std::iota(stage.coordinates.begin(), stage.coordinates.end(), 0);
            output.stages.push_back(std::move(stage));
        }
        if (polytope_history == FeedbackPolytopeHistory::certified_whole_history) {
            certified_history_geometry(output, run, system, states, controls, terminal_h, initial,
                                       labels, strict, active, phase);
            check_exact_history_stop(context);
            return output;
        }
        auto selected = shape(family, axis_h(initial, initial, {run.id("initial-h")}, labels),
                              initial, initial, {run.id("initial")}, labels);
        SetHandle selected_h = axis_h(initial, initial, {run.id("initial-embedding")}, labels);
        Vector carrier_lo = initial, carrier_hi = initial;
        const bool certified_stagewise =
            polytope_history == FeedbackPolytopeHistory::certified_stagewise;
        if (certified_stagewise && family != FeedbackFamily::polytope)
            bad("feedback.polytope-history",
                "Certified stagewise projection requires the polytope family.");
        if (certified_stagewise &&
            affine_box_history_geometry(output, run, system, states, controls, terminal_h, initial,
                                        labels, strict, active))
            return output;
        std::vector<Vector> lower(horizon + 1), upper(horizon + 1);
        std::vector<SetHandle> forward_embeddings;
        forward_embeddings.reserve(horizon + 1);
        std::optional<SetId> previous_forward;
        for (std::size_t k = 0; k <= horizon; ++k) {
            active = {k};
            run.stage = k;
            auto &stage = output.stages[k];
            if (k > 0) {
                const auto dynamics_result = system.stage({k - 1});
                if (auto *e = std::get_if<Diagnostic>(&dynamics_result))
                    throw Failure{Unsupported{{*e}}};
                const auto dynamics = std::get<model::DynamicsStage>(dynamics_result);
                bool exact_control_carrier = false;
                auto [ulo, uhi] = explicit_bounds(controls[k - 1], context, &exact_control_carrier);
                run.input_carriers.push_back(axis_h(ulo, uhi, {run.id("control-carrier")}, {}));
                if (exact_control_carrier)
                    run.lineage.push_back(
                        {{{resolved.identity(),
                           {run.id("exact-control-carrier")},
                           {run.input_carriers.back().id.value}},
                          {controls[k - 1].id}},
                         GeometryClaimScope::set_relation,
                         SymbolicArgument{
                             "Exact stored-binary64 H elimination",
                             "Built-in bounded exact H linear minimization; outward binary64 bracketing"},
                         {"Exact carrier applies to the stored closed-H control set, not a nonlinear plant."},
                         {}});
                std::vector<enclosure::Interval> exact_box;
                if (certified_stagewise) {
                    enclosure::Budget budget;
                    std::vector<enclosure::Interval> state_box, control_box;
                    for (std::size_t i = 0; i < n; ++i)
                        state_box.push_back(exact_interval(carrier_lo[i], carrier_hi[i], budget));
                    for (std::size_t i = 0; i < m; ++i)
                        control_box.push_back(exact_interval(ulo[i], uhi[i], budget));
                    exact_box = exact_successor_box(dynamics, state_box, control_box, budget);
                    for (std::size_t i = 0; i < n; ++i) {
                        const auto &lo = exact_box[i].lower;
                        const auto &hi = exact_box[i].upper;
                        carrier_lo[i] =
                            outward_lower({lo.numerator, lo.denominator, lo.binary_exponent},
                                          budget.max_integer_bits);
                        auto negative_hi = hi.numerator;
                        if (!negative_hi.words.empty())
                            negative_hi.negative = !negative_hi.negative;
                        carrier_hi[i] =
                            -outward_lower({negative_hi, hi.denominator, hi.binary_exponent},
                                           budget.max_integer_bits);
                    }
                } else {
                    auto box = propagate_existential_control_box(dynamics, {carrier_lo, carrier_hi},
                                                                 {ulo, uhi}, context);
                    if (auto *e = std::get_if<Unsupported>(&box))
                        throw Failure{*e};
                    if (auto *e = std::get_if<OperationStopped>(&box))
                        throw Failure{*e};
                    carrier_lo = std::get<BoxStage>(box).lower;
                    carrier_hi = std::get<BoxStage>(box).upper;
                }
                if (family == FeedbackFamily::polytope) {
                    if (n > std::numeric_limits<std::size_t>::max() - m ||
                        n + m > std::numeric_limits<std::size_t>::max() - n)
                        throw Failure{
                            OperationStopped{StopReason::resource_limit,
                                             "Joint state/control dimension overflowed."}};
                    Rows joint(2 * n + m);
                    joint.add(import(selected_h), 0);
                    joint.add(import(controls[k - 1]), n);
                    for (std::size_t i = 0; i < n; ++i) {
                        Vector row(2 * n + m, 0);
                        for (std::size_t j = 0; j < n; ++j)
                            row[j] = -dynamics.A(i, j);
                        for (std::size_t j = 0; j < m; ++j)
                            row[n + j] = -dynamics.B(i, j);
                        row[n + m + i] = 1;
                        joint.append(std::move(row), dynamics.offset[i], true);
                    }
                    if (certified_stagewise) {
                        selected_h =
                            certified_history_projection(run, joint, n + m, exact_box, labels,
                                                         "certified-stagewise-forward",
                                                         {selected_h.id, controls[k - 1].id})
                                .output;
                    } else {
                        auto relation = joint.finish({run.id("forward-joint")}, {});
                        std::vector<std::size_t> axes(n);
                        std::iota(axes.begin(), axes.end(), n + m);
                        auto image = run.project(relation, std::move(axes), "forward-image");
                        Rows relabel(n);
                        relabel.add(import(image.output), 0);
                        selected_h = relabel.finish({run.id("forward-labelled")}, labels);
                    }
                } else {
                    selected = propagate_family(family, selected, dynamics, ulo, uhi,
                                                {run.id("family-forward")}, labels, context, k,
                                                deps.max_generators_per_stage);
                    auto bounds = membership_bounds(selected);
                    carrier_lo = bounds.first;
                    carrier_hi = bounds.second;
                    selected_h =
                        axis_h(carrier_lo, carrier_hi, {run.id("forward-embedding")}, labels);
                }
            }
            auto physical = run.intersect(selected_h, states[k], "forward-intersection");
            auto forward_carrier =
                axis_h(carrier_lo, carrier_hi, {run.id("forward-carrier")}, labels);
            auto clipped =
                run.intersect(physical.output, forward_carrier, "forward-carrier-intersection");
            stage.forward_h = clipped;
            if (certified_stagewise) {
                lower[k] = carrier_lo;
                upper[k] = carrier_hi;
            } else {
                auto bounds = run.cover(clipped.output, carrier_lo, carrier_hi);
                lower[k] = std::move(bounds.lower);
                upper[k] = std::move(bounds.upper);
            }
            bool framed_forward = false;
            std::string forward_frame_note;
            auto framed = framed_member(clipped.output, lower[k], upper[k], "clipped-frame");
            if (family == FeedbackFamily::polytope) {
                selected = FeedbackHMembership{clipped.output, {}, {}};
                selected_h = clipped.output;
            } else if (framed) {
                selected = std::move(framed->first);
                forward_frame_note = std::move(framed->second);
                selected_h = std::get<FeedbackHMembership>(selected).set;
                framed_forward = true;
            } else if (!box_inside(states[k], carrier_lo, carrier_hi)) {
                selected = shape(family, clipped.output, lower[k], upper[k],
                                 {run.id("clipped-family")}, labels);
                auto embedding = membership_bounds(selected);
                selected_h = axis_h(embedding.first, embedding.second,
                                    {run.id("clipped-embedding")}, labels);
            }
            stage.forward_embedding_h = selected_h;
            forward_embeddings.push_back(selected_h);
            stage.forward = record(run, family, selected, strict, {clipped.output.id});
            if (framed_forward) {
                stage.forward->construction.push_back(
                    "parallelotope frame rule=" +
                    std::string(parallelotope_frame_rule_name(options.parallelotope_frame)) +
                    " with support bounds in frame coordinates.");
                if (!forward_frame_note.empty())
                    stage.forward->construction.push_back(std::move(forward_frame_note));
            }
            if (previous_forward)
                stage.forward->source_sets.push_back(*previous_forward);
            previous_forward = stage.forward->id;
            if (k == 0)
                stage.forward->construction.push_back(
                    "Observed singleton and physical state intersection.");
            else if (family == FeedbackFamily::polytope)
                stage.forward->construction.push_back(
                    "Full joint H state/control relation projected through the selected provider.");
            else if (family == FeedbackFamily::zonotope)
                stage.forward->construction.push_back(
                    "Native finite-plan zonotope one-step kernel, with the complete continuous control cover mapped through B as independent existential factors.");
            else if (family == FeedbackFamily::ellipsoid)
                stage.forward->construction.push_back(
                    "Native finite-plan ellipsoid one-step kernel with the complete control box mapped through B; output is an axis ellipsoid.");
            else
                stage.forward->construction.push_back(
                    "Native finite-plan box one-step kernel with the complete control box mapped through B; parallelotope uses the identity frame.");
            carrier_lo = lower[k];
            carrier_hi = upper[k];
        }
        SetHandle next_backward = terminal_h;
        std::optional<SetId> next_backward_family;
        for (std::size_t rev = horizon + 1; rev > 0; --rev) {
            const auto k = rev - 1;
            active = {k};
            run.stage = k;
            auto &stage = output.stages[k];
            phase =
                k == horizon ? FeedbackGeometryPhase::terminal : FeedbackGeometryPhase::backward;
            auto carrier = axis_h(lower[k], upper[k], {run.id("forward-carrier")}, labels);
            OperationResult backward =
                run.intersect(forward_embeddings[k], carrier, "relevant-carrier");
            if (k == horizon)
                backward = run.intersect(backward.output, terminal_h, "terminal");
            else {
                auto dynamics_result = system.stage({k});
                if (auto *e = std::get_if<Diagnostic>(&dynamics_result))
                    throw Failure{Unsupported{{*e}}};
                auto dynamics = std::get<model::DynamicsStage>(std::move(dynamics_result));
                if (certified_stagewise) {
                    Rows joint(2 * n + m);
                    joint.add(import(backward.output), 0);
                    joint.add(import(controls[k]), n);
                    joint.add(import(next_backward), n + m);
                    for (std::size_t i = 0; i < n; ++i) {
                        Vector row(2 * n + m, 0);
                        for (std::size_t j = 0; j < n; ++j)
                            row[j] = -dynamics.A(i, j);
                        for (std::size_t j = 0; j < m; ++j)
                            row[n + j] = -dynamics.B(i, j);
                        row[n + m + i] = 1;
                        joint.append(std::move(row), dynamics.offset[i], true);
                    }
                    enclosure::Budget budget;
                    std::vector<enclosure::Interval> box;
                    for (std::size_t i = 0; i < n; ++i)
                        box.push_back(exact_interval(lower[k][i], upper[k][i], budget));
                    backward = certified_history_projection(
                        run, joint, 0, box, labels, "certified-stagewise-backward",
                        {backward.output.id, controls[k].id, next_backward.id});
                } else {
                    GeometryRequestIdentity identity{
                        resolved.identity(), {run.id("predecessor")}, {run.id("predecessor-set")}};
                    NominalPredecessorRequest req{
                        identity,
                        backward.output,
                        controls[k],
                        next_backward,
                        copy_matrix(dynamics.A),
                        copy_matrix(dynamics.B),
                        Vector(dynamics.offset.values().begin(), dynamics.offset.values().end()),
                        SetRelation::equivalent,
                        Assurance::numerical};
                    auto prep = prepare_nominal_predecessor(req, deps.geometry.forward.projection);
                    if (auto *e = std::get_if<Diagnostics>(&prep))
                        throw Failure{Unsupported{*e}};
                    if (auto *e = std::get_if<registry::Rejection>(&prep))
                        throw Failure{Unsupported{e->diagnostics}};
                    auto result =
                        std::get<PreparedNominalPredecessor>(std::move(prep)).run(context);
                    if (auto *e = std::get_if<NominalPredecessorFailure>(&result)) {
                        run.requests.push_back(e->predecessor);
                        run.requests.push_back(e->projection);
                        run.providers.push_back(e->projection_provider);
                        run.lineage.insert(run.lineage.end(), e->completed_lineage.begin(),
                                           e->completed_lineage.end());
                        std::visit([](auto cause) { throw Failure{std::move(cause)}; }, e->cause);
                    }
                    auto pre = std::get<NominalPredecessorResult>(std::move(result));
                    run.requests.push_back(pre.result.evidence.reference);
                    run.providers.push_back(pre.projection_provider);
                    run.lineage.push_back(pre.result.evidence);
                    backward = std::move(pre.result);
                }
            }
            stage.backward_h = backward;
            auto bounds = run.cover(backward.output, lower[k], upper[k]);
            std::optional<std::pair<FeedbackMembership, std::string>> framed_backward;
            std::string backward_frame_note;
            if (family != FeedbackFamily::polytope)
                framed_backward =
                    framed_member(backward.output, lower[k], upper[k], "backward-frame");
            auto member = framed_backward
                              ? std::move(framed_backward->first)
                              : shape(family, backward.output, bounds.lower, bounds.upper,
                                      {run.id("backward-family")}, labels);
            if (framed_backward)
                backward_frame_note = std::move(framed_backward->second);
            if (family == FeedbackFamily::polytope)
                next_backward = backward.output;
            else {
                auto range = membership_bounds(member);
                next_backward =
                    axis_h(range.first, range.second, {run.id("backward-embedding")}, labels);
            }
            stage.backward_embedding_h = next_backward;
            stage.backward = record(run, family, member, strict, {backward.output.id});
            if (next_backward_family)
                stage.backward->source_sets.push_back(*next_backward_family);
            next_backward_family = stage.backward->id;
            stage.backward->construction.push_back(
                framed_backward
                    ? "Projected full-state H predecessor bounded in the selected "
                      "parallelotope frame within the forward-relevant carrier."
                : family == FeedbackFamily::polytope
                    ? "Projected full-state H predecessor with forward-relevant carrier."
                    : "Projected full-state H predecessor enclosed by a coarse axis family cover within the forward-relevant carrier.");
            if (!backward_frame_note.empty())
                stage.backward->construction.push_back(std::move(backward_frame_note));
            phase = FeedbackGeometryPhase::intersection;
            auto full_intersection =
                run.intersect(forward_embeddings[k], next_backward, "full-state-intersection");
            auto intersection =
                run.intersect(full_intersection.output, carrier, "intersection-carrier");
            stage.intersection_h = intersection;
            auto overlap = run.cover(intersection.output, lower[k], upper[k]);
            std::optional<std::pair<FeedbackMembership, std::string>> framed_intersection;
            std::string intersection_frame_note;
            if (family != FeedbackFamily::polytope)
                framed_intersection =
                    framed_member(intersection.output, lower[k], upper[k], "intersection-frame");
            auto intersection_shape =
                framed_intersection
                    ? std::move(framed_intersection->first)
                    : shape(family, intersection.output, overlap.lower, overlap.upper,
                            {run.id("intersection-family")}, labels);
            if (framed_intersection)
                intersection_frame_note = std::move(framed_intersection->second);
            stage.intersection = record(run, family, std::move(intersection_shape), strict,
                                        {forward_embeddings[k].id, next_backward.id, carrier.id,
                                         stage.forward->id, stage.backward->id});
            stage.intersection->construction.push_back(
                framed_intersection
                    ? "Full-state forward and backward H embeddings intersected with the explicit "
                      "forward-relevant carrier before selected-frame support enclosure."
                    : "Full-state forward and backward H embeddings intersected with the explicit forward-relevant carrier before family enclosure.");
            if (!intersection_frame_note.empty())
                stage.intersection->construction.push_back(std::move(intersection_frame_note));
        }
        return output;
    } catch (const Failure &failure) {
        return FeedbackGeometryFailure{std::move(output),
                                       active,
                                       phase,
                                       failure.cause,
                                       std::move(run.requests),
                                       std::move(run.providers),
                                       std::move(run.lineage),
                                       std::move(run.support_calls),
                                       std::move(run.support_certificates),
                                       std::move(run.input_carriers)};
    } catch (const std::bad_alloc &) {
        return FeedbackGeometryFailure{
            std::move(output),
            active,
            phase,
            OperationStopped{StopReason::resource_limit, "Feedback geometry allocation failed."},
            std::move(run.requests),
            std::move(run.providers),
            std::move(run.lineage),
            std::move(run.support_calls),
            std::move(run.support_certificates),
            std::move(run.input_carriers)};
    } catch (const std::length_error &) {
        return FeedbackGeometryFailure{
            std::move(output),
            active,
            phase,
            OperationStopped{StopReason::resource_limit, "Feedback geometry capacity exceeded."},
            std::move(run.requests),
            std::move(run.providers),
            std::move(run.lineage),
            std::move(run.support_calls),
            std::move(run.support_certificates),
            std::move(run.input_carriers)};
    }
}
} // namespace csl::reachability
