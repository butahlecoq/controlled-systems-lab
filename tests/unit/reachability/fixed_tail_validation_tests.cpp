#include <csl/reachability/fixed_tail_policy.hpp>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace csl;
using namespace csl::reachability;
namespace {
void require(bool value, const char *reason) {
    if (!value)
        throw std::runtime_error(reason);
}
Matrix identity(std::size_t n) {
    Matrix out{n, n, Vector(n * n, 0)};
    for (std::size_t j = 0; j < n; ++j)
        out.values[j * n + j] = 1;
    return out;
}
FixedTailHRows empty(std::size_t n) { return {{0, n, {}}, {}, {0, n, {}}, {}}; }
optimization::HistoryCostProgram cost() {
    Matrix Q{3, 3, Vector(9, 0)};
    Q.values[4] = 2;
    return {
        {{1, 1, 0}, 1}, {3, Q, {0, -2, 0}, 1}, {}, QuadraticTerminal{{1, 1, {2}}, {-2}, 1}, {}, 0};
}
FixedTailSolveRequest request() {
    return {{{"validation-problem"}, {"validation-solve"}},
            empty(3),
            cost(),
            {{{1, 1, 0}, 1}, identity(3), Vector(3, 0)},
            {},
            Vector(3, 0),
            true,
            {}};
}
FixedTailModel validation_model() {
    FixedTailHRows control{{2, 1, {1, -1}}, {0, 0}, {0, 1, {}}, {}};
    FixedTailHRows full{{2, 3, {0, 0, 1, 0, 0, -1}}, {0, 0}, {2, 3, {1, 0, 0, -1, 1, -1}}, {0, 0}};
    return {{"validation-problem"},
            {{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}},
            {0},
            {empty(1), empty(1)},
            {control},
            {{Interval{0, 0}}},
            full,
            cost()};
}
FixedTailModel endpoint_model(bool future) {
    auto out = validation_model();
    out.control_domains[0].upper_bounds = {1, 1};
    out.input_carriers[0] = {Interval{-1, 1}};
    out.full_history.upper_bounds = {1, 1};
    if (!future)
        return out;
    out.stages.push_back(out.stages.front());
    out.state_domains.push_back(empty(1));
    out.control_domains.push_back(out.control_domains.front());
    out.input_carriers.push_back(out.input_carriers.front());
    out.full_history = {{4, 5, {0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1}},
                        {1, 1, 1, 1},
                        {3, 5, {1, 0, 0, 0, 0, -1, 1, 0, -1, 0, 0, -1, 1, 0, -1}},
                        {0, 0, 0}};
    Matrix Q{5, 5, Vector(25, 0)};
    Q.values[12] = 2;
    out.source_cost = {{{1, 1, 0}, 2},
                       {5, Q, {0, 0, -2, 0, 0}, 1},
                       {},
                       QuadraticTerminal{{1, 1, {2}}, {-2}, 1},
                       {},
                       0};
    return out;
}
class EndpointWorkspace final : public FixedTailOptimizerWorkspace {
  public:
    EndpointWorkspace(double delta, bool future, int bad_readback)
        : delta_(delta), future_(future), bad_readback_(bad_readback) {}
    FixedTailSolveOutcome solve(const FixedTailSolveRequest &r, const ExecutionContext &) override {
        const auto T = r.lift.coordinates.horizon;
        Vector primary = r.initial_primary, history;
        if (r.feasibility_only) {
            history = Vector((T + 1) + T, 0);
            if (future_) {
                history.back() = 1 + delta_;
                history[T] = 1 + delta_;
            }
            primary = history;
        } else {
            primary = {future_ ? 0 : 1 + delta_};
            history = std::get<Vector>(recover_fixed_tail_history(r.lift, primary));
        }
        const auto objective = r.feasibility_only ? 0 : (history[T] - 1) * (history[T] - 1);
        std::vector<Vector> factors(T + 1);
        if (!r.feasibility_only)
            for (std::size_t j = 1; j <= T; ++j)
                factors[j] = {future_ ? 0 : primary[0]};
        auto readback = r.initial_primary;
        if (bad_readback_ == (r.feasibility_only ? 1 : 2))
            readback[0] += 1;
        return FixedTailSolveResult{primary, history,  objective, r.initial_primary,
                                    {},      readback, factors,   "endpoint-recovery fixture"};
    }

  private:
    double delta_;
    bool future_;
    int bad_readback_;
};
FixedTailPolicyOutcome endpoint_policy(double delta, bool future, int bad_readback = 0) {
    registry::Registry<registry::FixedTailOptimizerPort> registry;
    registry::Registration<registry::FixedTailOptimizerPort> entry{
        {{"test.endpoint-provider"}, "1"},
        [](const FixedTailSolveRequest &, const registry::Requirements &) -> registry::Capability {
            return registry::Offer{{{"csl.fixed-tail-solve.v1"}, Assurance::numerical, {}, {}, {}}};
        },
        [=](const FixedTailSolveRequest &) -> std::unique_ptr<FixedTailOptimizerWorkspace> {
            return std::make_unique<EndpointWorkspace>(delta, future, bad_readback);
        }};
    const registry::Method method{entry.identity.id, entry.identity.version};
    require(!registry.add(std::move(entry)), "endpoint fixture registration failed");
    registry::Requirements requirements;
    requirements.output.representation = {"csl.fixed-tail-solve.v1"};
    auto selected =
        registry::prepare_provider(registry::select_provider(registry, method, requirements));
    return fixed_tail_policy(
        {endpoint_model(future),
         {"endpoint-recovery"},
         FixedTailFamily::box,
         Vector(future ? 5 : 3, 0),
         {}},
        std::get<registry::PreparedProvider<registry::FixedTailOptimizerPort>>(selected), {});
}
class MalformedWorkspace final : public FixedTailOptimizerWorkspace {
  public:
    explicit MalformedWorkspace(bool bad_anchor) : bad_anchor_(bad_anchor) {}
    FixedTailSolveOutcome solve(const FixedTailSolveRequest &r, const ExecutionContext &) override {
        auto result = FixedTailSolveResult{r.initial_primary,
                                           Vector(3, 0),
                                           0,
                                           r.initial_primary,
                                           {},
                                           r.initial_primary,
                                           {},
                                           "deliberate malformed-provider fixture"};
        if (bad_anchor_)
            result.history.clear();
        else if (!r.feasibility_only)
            result.primary.clear();
        return result;
    }

  private:
    bool bad_anchor_;
};
}
int run() {
    FullHistoryLift lift{{{1, 1, 0}, 1}, {3, 1, {0, 1, 1}}, {0, 0, 0}};
    const Vector current{1};
    auto bad = lift;
    bad.offset.pop_back();
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(bad, current)),
            "short lift offset was not rejected");
    bad = lift;
    bad.map.values.clear();
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(bad, current)),
            "missing lift matrix storage was not rejected");
    bad = lift;
    bad.map.rows = std::numeric_limits<std::size_t>::max();
    require(std::holds_alternative<Diagnostic>(recover_fixed_tail_history(bad, current)),
            "overflowing lift dimensions were not rejected");
    require(std::holds_alternative<Diagnostic>(
                recover_fixed_tail_history(lift, Vector{std::numeric_limits<double>::quiet_NaN()})),
            "nonfinite current action was not rejected");
    require(std::get<Vector>(recover_fixed_tail_history(lift, current)) == Vector({0, 1, 1}),
            "valid public recovery changed");

    const auto valid = request();
    require(check_fixed_tail_solve_request(valid).empty(),
            "valid native solve request failed validation");
    auto malformed = valid;
    malformed.domain.inequalities = {1, 3, {}};
    malformed.domain.upper_bounds = {0};
    require(!check_fixed_tail_solve_request(malformed).empty(),
            "missing H matrix storage was not rejected");
    malformed = valid;
    malformed.domain.equalities = {1, 3, {1, 0, 0}};
    require(!check_fixed_tail_solve_request(malformed).empty(),
            "missing equality bound was not rejected");
    malformed = valid;
    malformed.source_cost.quadratic.Q.values.clear();
    require(!check_fixed_tail_solve_request(malformed).empty(),
            "missing quadratic storage was not rejected");
    malformed = valid;
    malformed.source_cost.quadratic.linear = {0};
    require(!check_fixed_tail_solve_request(malformed).empty(),
            "short source linear objective was not rejected");
    malformed = valid;
    malformed.source_cost.residual_norms.push_back({{1, 3, {}}, {0}, {1}, 1});
    require(!check_fixed_tail_solve_request(malformed).empty(),
            "missing residual matrix was not rejected");
    malformed = valid;
    malformed.source_cost.residual_norms.push_back({{1, 3, {1, 0, 0}}, {0}, {-1}, 1});
    require(!check_fixed_tail_solve_request(malformed).empty(),
            "negative norm weight was not rejected");

    for (const bool bad_anchor : {true, false}) {
        registry::Registry<registry::FixedTailOptimizerPort> providers;
        registry::Registration<registry::FixedTailOptimizerPort> entry{
            {{"test.malformed-provider"}, "1"},
            [](const FixedTailSolveRequest &,
               const registry::Requirements &) -> registry::Capability {
                return registry::Offer{
                    {{"csl.fixed-tail-solve.v1"}, Assurance::numerical, {}, {}, {}}};
            },
            [bad_anchor](
                const FixedTailSolveRequest &) -> std::unique_ptr<FixedTailOptimizerWorkspace> {
                return std::make_unique<MalformedWorkspace>(bad_anchor);
            }};
        const registry::Method method{entry.identity.id, entry.identity.version};
        require(!providers.add(std::move(entry)), "fixture provider registration failed");
        registry::Requirements requirements;
        requirements.output.representation = {"csl.fixed-tail-solve.v1"};
        auto selected =
            registry::prepare_provider(registry::select_provider(providers, method, requirements));
        require(
            std::holds_alternative<registry::PreparedProvider<registry::FixedTailOptimizerPort>>(
                selected),
            "fixture selection failed");
        const auto result = fixed_tail_policy(
            {validation_model(), {"malformed-result"}, FixedTailFamily::box, Vector(3, 0), {}},
            std::get<registry::PreparedProvider<registry::FixedTailOptimizerPort>>(selected), {});
        const auto *failure = std::get_if<FixedTailPolicyFailure>(&result);
        require(failure != nullptr,
                "malformed provider result was accepted or escaped its typed failure");
        require(failure->phase == (bad_anchor ? "feasibility" : "reduced-argmin"),
                "malformed result failed in the wrong phase");
    }
    for (const bool future : {false, true}) {
        const auto answer = endpoint_policy(5e-13, future);
        const auto *result = std::get_if<FixedTailPolicyResult>(&answer);
        if (const auto *failure = std::get_if<FixedTailPolicyFailure>(&answer))
            std::cerr << "endpoint future=" << future << " phase=" << failure->phase
                      << " reason=" << failure->cause.explanation << "\n";
        require(result != nullptr, "tiny literal endpoint violation was not recovered");
        require(result->history.back() == 1, "recovered history retained an out-of-bound command");
        require(result->cost.total == 0,
                "complete original J was not recomputed at recovered history");
        if (future) {
            require(result->feasibility.history.back() > 1,
                    "raw feasibility primal was overwritten");
            require(result->anchor_control_adjustments.size() == 1 &&
                        result->anchor_control_adjustments[0].stage.value == 1,
                    "future anchor endpoint adjustment was not reported");
        } else {
            require(result->reduced_argmin.primary[0] > 1,
                    "raw reduced optimizer primal was overwritten");
            require(result->command_adjustments.size() == 1 &&
                        result->command_adjustments[0].source_bound == 1,
                    "current command endpoint adjustment was not reported");
        }
        const auto material = endpoint_policy(1e-3, future);
        const auto *failure = std::get_if<FixedTailPolicyFailure>(&material);
        require(failure && failure->cause.explanation.find("materially") != std::string::npos,
                "material authored endpoint violation was repaired or misclassified");
    }
    bool readbacks_rejected = true;
    for (const int phase : {1, 2}) {
        const auto malformed = endpoint_policy(0, false, phase);
        const auto *failure = std::get_if<FixedTailPolicyFailure>(&malformed);
        if (!failure) {
            std::cerr << "materially different provider readback accepted in phase " << phase
                      << "\n";
            readbacks_rejected = false;
        }
    }
    require(readbacks_rejected,
            "materially different actual provider initialization was not rejected");
    std::cout
        << "Native fixed-tail boundaries: malformed lift, request and provider result rejection passed\n";
    return 0;
}
int main() {
    try {
        return run();
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
