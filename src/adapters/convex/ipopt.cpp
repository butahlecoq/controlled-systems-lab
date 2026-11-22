#include <csl/adapters/convex/ipopt.hpp>

#include <IpStdCInterface.h>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::adapters::convex {
namespace {
using namespace optimization;

constexpr double infinity = 1e19;
constexpr auto capacity = static_cast<std::size_t>(std::numeric_limits<ipindex>::max());

Diagnostics refusal(const char *field, const char *explanation) {
    return {{DiagnosticCode::unsupported, field, explanation}};
}

bool representable(const Interval &row) {
    return (!row.lower || std::abs(*row.lower) < infinity) &&
           (!row.upper || std::abs(*row.upper) < infinity);
}

Diagnostics admission(const ConvexProgram &program) {
    const auto coefficients = program.original_objective().coefficients();
    const auto *objective = std::get_if<QuadraticCoefficients>(&coefficients);
    if (!objective || program.reformulation())
        return refusal("ipopt.convex.objective", "A direct convex quadratic is required.");
    const auto &qp = program.quadratic_program();
    const auto n = qp.variables().size();
    const auto csr = std::get<numeric::CsrInput>(qp.constraints().descriptor());
    if (n == 0 || n > 4096 || csr.rows >= capacity || csr.values.size() > capacity)
        return refusal("ipopt.convex.capacity", "The problem exceeds the Ipopt QP profile.");
    if (!std::ranges::all_of(qp.variables(), representable) ||
        !std::ranges::all_of(qp.rows(), representable))
        return refusal("ipopt.convex.bounds",
                       "A finite bound collides with Ipopt's infinity convention.");
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < i; ++j)
            if (objective->Q(i, j) != objective->Q(j, i))
                return refusal("ipopt.convex.hessian", "The original quadratic must be symmetric.");
    return {};
}

std::optional<Termination> stopped(const ExecutionContext &context) {
    if (context.cancellation.stop_requested())
        return Termination::cancelled;
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return Termination::deadline_expired;
    return {};
}

struct NativeData {
    numeric::CsrInput rows;
    QuadraticCoefficients objective;
    const ExecutionContext &context;
    std::vector<ipindex> jacobian_rows, jacobian_columns, hessian_rows, hessian_columns;
    Vector hessian_values;
};

bool evaluate_objective(ipindex n, double *x, bool, double *value, void *opaque) {
    const auto &q = static_cast<NativeData *>(opaque)->objective;
    *value = q.offset;
    for (ipindex i = 0; i < n; ++i) {
        double row = 0;
        for (ipindex j = 0; j < n; ++j)
            row += q.Q(i, j) * x[j];
        *value += (0.5 * x[i]) * row;
        *value += q.linear[i] * x[i];
    }
    return std::isfinite(*value);
}

bool evaluate_gradient(ipindex n, double *x, bool, double *gradient, void *opaque) {
    const auto &q = static_cast<NativeData *>(opaque)->objective;
    for (ipindex i = 0; i < n; ++i) {
        gradient[i] = q.linear[i];
        for (ipindex j = 0; j < n; ++j)
            gradient[i] += q.Q(i, j) * x[j];
    }
    return std::all_of(gradient, gradient + n, [](double v) { return std::isfinite(v); });
}

bool evaluate_rows(ipindex, double *x, bool, ipindex m, double *activity, void *opaque) {
    const auto &a = static_cast<NativeData *>(opaque)->rows;
    for (ipindex i = 0; i < m; ++i) {
        activity[i] = 0;
        for (auto k = a.row_offsets[i]; k < a.row_offsets[i + 1]; ++k)
            activity[i] += a.values[k] * x[a.column_indices[k]];
        if (!std::isfinite(activity[i]))
            return false;
    }
    return true;
}

bool evaluate_jacobian(ipindex, double *, bool, ipindex, ipindex, ipindex *rows, ipindex *columns,
                       double *values, void *opaque) {
    const auto &data = *static_cast<NativeData *>(opaque);
    if (values) {
        std::ranges::copy(data.rows.values, values);
    } else {
        std::ranges::copy(data.jacobian_rows, rows);
        std::ranges::copy(data.jacobian_columns, columns);
    }
    return true;
}

bool evaluate_hessian(ipindex, double *, bool, double factor, ipindex, double *, bool, ipindex,
                      ipindex *rows, ipindex *columns, double *values, void *opaque) {
    const auto &data = *static_cast<NativeData *>(opaque);
    if (values) {
        std::ranges::transform(data.hessian_values, values,
                               [factor](double v) { return factor * v; });
    } else {
        std::ranges::copy(data.hessian_rows, rows);
        std::ranges::copy(data.hessian_columns, columns);
    }
    return true;
}

bool continue_iterations(ipindex, ipindex, double, double, double, double, double, double, double,
                         double, ipindex, void *opaque) {
    return !stopped(static_cast<NativeData *>(opaque)->context);
}

std::pair<Vector, Vector> native_bounds(std::span<const Interval> intervals) {
    std::pair<Vector, Vector> bounds;
    for (const auto &interval : intervals) {
        bounds.first.push_back(interval.lower.value_or(-infinity));
        bounds.second.push_back(interval.upper.value_or(infinity));
    }
    return bounds;
}

bool configure(IpoptProblem native, ipindex limit) {
    const auto integer = [&](std::string key, ipindex value) {
        return AddIpoptIntOption(native, key.data(), value);
    };
    const auto text = [&](std::string key, std::string value) {
        return AddIpoptStrOption(native, key.data(), value.data());
    };
    const auto number = [&](std::string key, double value) {
        return AddIpoptNumOption(native, key.data(), value);
    };
    return text("option_file_name", "") && integer("print_level", 0) && text("sb", "yes") &&
           text("nlp_scaling_method", "none") &&
           text("fixed_variable_treatment", "make_constraint") && number("bound_relax_factor", 0) &&
           number("tol", 1e-10) && number("dual_inf_tol", 1e-10) &&
           number("constr_viol_tol", 1e-10) && number("compl_inf_tol", 1e-10) &&
           integer("acceptable_iter", 0) && integer("max_iter", limit) &&
           SetIntermediateCallback(native, continue_iterations);
}

void check_candidate(ProgramResult &result, const ConvexProgram &p, const NumericalPolicy &policy,
                     ApplicationReturnStatus status, double objective, Vector x,
                     const DualMultipliers &multipliers) {
    if (!std::ranges::all_of(x, [](double v) { return std::isfinite(v); }))
        return;
    result.primal = std::move(x);
    const auto primal =
        evaluate_primal(p, *result.primal, policy, {{"csl.convex.ipopt.primal"}, "1"});
    const auto dual =
        evaluate_dual(p, *result.primal, multipliers, policy, {{"csl.convex.ipopt.kkt"}, "1"});
    const auto *checked = std::get_if<ConvexPrimalEvaluation>(&primal);
    const auto *kkt = std::get_if<DualResiduals>(&dual);
    if (checked)
        result.residuals.primal = checked->residuals;
    if (kkt)
        result.residuals.dual = *kkt;
    if (status != Solve_Succeeded || !checked || !kkt || !kkt->stationarity || !kkt->signs ||
        !kkt->complementarity)
        return;
    const auto pass = [&](const ResidualMeasure &metric) {
        return metric.violation <=
               policy.absolute_tolerance + policy.relative_tolerance * metric.scale;
    };
    const double tolerance =
        policy.absolute_tolerance + policy.relative_tolerance * std::max(1.0, std::abs(objective));
    if (std::isfinite(objective) && std::isfinite(tolerance) &&
        std::abs(checked->original_objective - objective) <= tolerance &&
        pass(checked->residuals.rows) && pass(checked->residuals.variables) &&
        pass(*kkt->stationarity) && pass(*kkt->signs) && pass(*kkt->complementarity)) {
        result.termination = Termination::completed;
        result.outcome.value = MathematicalOutcome::optimal;
    }
}

class Workspace final : public ConvexWorkspace {
    ipindex limit_;

    ProgramOutcome do_solve(const ConvexProgram &p, const ExecutionContext &context) override {
        if (auto errors = admission(p); !errors.empty())
            return Unsupported{std::move(errors)};
        if (!context.resources || !check_resources(*context.resources).empty())
            return Unsupported{refusal("resources", "A valid resource policy is required.")};
        if (context.resources->memory_bytes || context.resources->threads_per_worker != 1 ||
            context.resources->outer_workers != 1)
            return Unsupported{
                refusal("resources", "Ipopt requires one worker and no native memory cap.")};
        const auto policy = context.numerical;
        if (!std::isfinite(policy.absolute_tolerance) || policy.absolute_tolerance < 0 ||
            !std::isfinite(policy.relative_tolerance) || policy.relative_tolerance < 0)
            return Unsupported{refusal("ipopt.convex.tolerance",
                                       "Validation tolerances must be finite and nonnegative.")};
        ProgramResult result{Termination::numerical_failure,
                             {p.identity(), MathematicalOutcome::undetermined, Unestablished{}, {}},
                             {},
                             {},
                             {},
                             {}};
        if (const auto stop = stopped(context)) {
            result.termination = *stop;
            return result;
        }

        const auto &qp = p.quadratic_program();
        NativeData data{std::get<numeric::CsrInput>(qp.constraints().descriptor()),
                        std::get<QuadraticCoefficients>(p.original_objective().coefficients()),
                        context,
                        {},
                        {},
                        {},
                        {},
                        {}};
        const auto n = static_cast<ipindex>(data.rows.cols);
        const auto m = static_cast<ipindex>(data.rows.rows);
        for (ipindex i = 0; i < m; ++i)
            for (auto k = data.rows.row_offsets[i]; k < data.rows.row_offsets[i + 1]; ++k) {
                data.jacobian_rows.push_back(i);
                data.jacobian_columns.push_back(static_cast<ipindex>(data.rows.column_indices[k]));
            }
        for (ipindex i = 0; i < n; ++i)
            for (ipindex j = 0; j <= i; ++j)
                if (const double h = data.objective.Q(i, j); h != 0.0) {
                    data.hessian_rows.push_back(i);
                    data.hessian_columns.push_back(j);
                    data.hessian_values.push_back(h);
                }
        auto [xl, xu] = native_bounds(qp.variables());
        auto [gl, gu] = native_bounds(qp.rows());
        const auto native = CreateIpoptProblem(n, xl.data(), xu.data(), m, gl.data(), gu.data(),
                                               static_cast<ipindex>(data.jacobian_rows.size()),
                                               static_cast<ipindex>(data.hessian_rows.size()), 0,
                                               evaluate_objective, evaluate_rows, evaluate_gradient,
                                               evaluate_jacobian, evaluate_hessian);
        std::unique_ptr<IpoptProblemInfo, decltype(&FreeIpoptProblem)> owner(native,
                                                                             &FreeIpoptProblem);
        if (!native || !configure(native, limit_)) {
            result.raw_diagnostics = "Ipopt setup failed";
            return result;
        }

        Vector x(n), activity(m), signed_rows(m);
        DualMultipliers multipliers{Vector(m), Vector(m), Vector(n), Vector(n)};
        if (const auto hint = p.primal_start()) {
            std::ranges::copy(*hint, x.begin());
            result.raw_diagnostics = "primal_start=submitted\n";
        } else {
            for (ipindex i = 0; i < n; ++i)
                x[i] = std::clamp(0.0, xl[i], xu[i]);
        }
        double objective{};
        const auto status =
            IpoptSolve(native, x.data(), activity.data(), &objective, signed_rows.data(),
                       multipliers.variable_lower.data(), multipliers.variable_upper.data(), &data);
        result.raw_diagnostics += "ipopt_status=" + std::to_string(static_cast<int>(status));
        if (const auto stop = stopped(context)) {
            result.termination = *stop;
            return result;
        }
        if (status == Maximum_Iterations_Exceeded || status == Insufficient_Memory)
            result.termination = Termination::resource_limit;
        for (ipindex i = 0; i < m; ++i) {
            const double lambda = signed_rows[i];
            if (!std::isfinite(lambda))
                return result;
            multipliers.row_lower[i] = std::max(0.0, -lambda);
            multipliers.row_upper[i] = std::max(0.0, lambda);
        }
        check_candidate(result, p, context.numerical, status, objective, std::move(x), multipliers);
        if (status == Solve_Succeeded && result.outcome.value != MathematicalOutcome::optimal)
            result.raw_diagnostics +=
                "\noptimality.withheld=original-space checks unavailable or failing";
        return result;
    }

  public:
    explicit Workspace(ipindex limit) : limit_(limit) {}
};
} // namespace

std::variant<registry::Registration<registry::ConvexPort>, Diagnostics>
make_ipopt_registration(IpoptConvexOptions options) {
    ipindex major{}, minor{}, release{};
    GetIpoptVersion(&major, &minor, &release);
    if (major != 3 || minor != 14 || release != 19)
        return refusal("ipopt.convex.version", "The linked Ipopt library must be version 3.14.19.");
    const auto limit = options.iteration_limit.value_or(250);
    if (limit > capacity)
        return refusal("ipopt.convex.iteration_limit",
                       "Iteration count exceeds the native integer width.");
    return registry::Registration<registry::ConvexPort>{
        {{"csl.convex.ipopt"}, "1.0.0+ipopt.3.14.19"},
        [](const ConvexProgram &p,
           const registry::Requirements &requirements) -> registry::Capability {
            if (requirements.scalar != registry::Scalar::binary64)
                return refusal("scalar", "Binary64 is required.");
            if (auto errors = admission(p); !errors.empty())
                return errors;
            return registry::Offer{{{"csl.program-result.v1"},
                                    Assurance::numerical,
                                    {},
                                    {},
                                    registry::Completeness::unestablished}};
        },
        [limit](const ConvexProgram &) {
            return std::make_unique<Workspace>(static_cast<ipindex>(limit));
        },
        {},
        {}};
}
} // namespace csl::adapters::convex
