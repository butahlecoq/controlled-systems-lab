#include <csl/reachability/bounded_h_support.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/reachability/feedback_geometry.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/optimization/contracts.hpp>
#include <csl/optimization/linear_program.hpp>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <source_location>
#include <variant>

void check(bool condition, std::source_location where = std::source_location::current()) {
    if (!condition) {
        std::fprintf(stderr, "check failed at line %u\n", where.line());
        std::abort();
    }
}

class FixedResultLP final : public csl::LPWorkspace {
    csl::Termination termination_;
    csl::MathematicalOutcome outcome_;

    csl::ProgramOutcome do_solve(const csl::LinearProgram &program,
                                 const csl::ExecutionContext &) override {
        return csl::ProgramResult{termination_,
                                  {program.identity(), outcome_, csl::Unestablished{}, {}},
                                  {},
                                  {},
                                  "bounded-H support fixture result"};
    }

  public:
    FixedResultLP(csl::Termination termination, csl::MathematicalOutcome outcome)
        : termination_(termination), outcome_(outcome) {}
};

csl::registry::PreparedProvider<csl::registry::LPPort>
fixed_result_provider(csl::Termination termination, csl::MathematicalOutcome outcome) {
    using namespace csl;
    registry::Registry<registry::LPPort> registry;
    check(!registry
               .add({{{"bounded-h-support-fixture"}, "1"},
                     [](const LinearProgram &, const registry::Requirements &)
                         -> registry::Capability { return registry::Offer{}; },
                     [termination, outcome](const LinearProgram &) {
                         return std::make_unique<FixedResultLP>(termination, outcome);
                     }})
               .has_value());
    auto prepared = registry::prepare_provider(
        registry::select_provider(registry, {{"bounded-h-support-fixture"}, "1"}));
    check(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

int main() {
    using namespace csl;
    using namespace csl::reachability;
    // x+y <= 1 over [-2,2]^2, query x+y. Approximate multiplier 0.9
    // leaves a nonzero residual which must be bounded over the carrier.
    BoundedHSupportInput input{{1,2,{1,1}}, {1}, {0,2,{}}, {},
        {-2,-2}, {2,2}, {1,1}};
    const auto result = residual_corrected_support(input, {0.9}, {});
    check(std::holds_alternative<SupportUpperBound>(result));
    const auto bound = std::get<SupportUpperBound>(result).value;
    check(bound >= 1.3 && bound < 1.300000000001);
    BoundedHSupportInput tiny{{1,2,{1e-14,1}}, {1}, {0,2,{}}, {},
        {-2,-2}, {2,2}, {1e-14,1}};
    auto tiny_bound=residual_corrected_support(tiny,{1},{});
    check(std::holds_alternative<SupportUpperBound>(tiny_bound));
    check(std::get<SupportUpperBound>(tiny_bound).value>=1);
    auto zonotope=axis_enclosure(FeedbackFamily::zonotope, {"z"},
        {-1,-2,3,4}, {1,2,3,4}, {});
    check(std::holds_alternative<FeedbackMembership>(zonotope));
    const auto& z=std::get<FeedbackZonotopeMembership>(std::get<FeedbackMembership>(zonotope));
    check(z.generators.rows==4 && z.generators.cols==4 && z.generators.values[10]==0);
    auto ellipsoid=axis_enclosure(FeedbackFamily::ellipsoid, {"e"},
        {-1,-2,3,4}, {1,2,3,4}, {});
    check(std::holds_alternative<FeedbackMembership>(ellipsoid));
    const auto& e=std::get<FeedbackEllipsoidMembership>(std::get<FeedbackMembership>(ellipsoid));
    check(e.factor.rows==4 && e.factor.cols==4 && e.factor.values[10]==0);
    check(e.factor.values[0]>=2 && e.factor.values[5]>=4);
    auto box_shape=axis_enclosure(FeedbackFamily::box, {"box"}, {-1,0}, {1,2}, {"x","y"});
    check(std::holds_alternative<FeedbackMembership>(box_shape));
    const auto& box_h=std::get<FeedbackHMembership>(std::get<FeedbackMembership>(box_shape));
    check(!box_h.parallelotope_frame.has_value());
    auto para=axis_enclosure(FeedbackFamily::parallelotope, {"p"}, {-1,0}, {1,2}, {"x","y"});
    check(std::holds_alternative<FeedbackMembership>(para));
    check(std::get<FeedbackHMembership>(std::get<FeedbackMembership>(para)).parallelotope_frame.has_value());
    auto matrix=[](Matrix m) { return std::get<numeric::MatrixView>(numeric::snapshot(m)); };
    auto vector=[](Vector v) { return std::get<numeric::VectorView>(numeric::snapshot_vector(v)); };
    model::DynamicsStage dynamics{matrix({2,2,{1,1,0,1}}),matrix({2,1,{1,1}}),
        matrix({2,0,{}}),vector({0,0})};
    FinitePlanZonotopeTrace::Stage state{{0,0},{2,1,{1,1}},{{"state"}}};
    FinitePlanZonotopeTrace::Stage control{{0},{1,1,{0.5}},{{"u"}}};
    auto propagated_box=propagate_existential_control_box(dynamics,
        {{-1,-1},{1,1}},{{-0.5},{0.5}},{});
    check(std::holds_alternative<BoxStage>(propagated_box));
    const auto& next_box=std::get<BoxStage>(propagated_box);
    check(next_box.lower[0]<=-2.5 && next_box.upper[0]>=2.5);
    check(next_box.lower[1]<=-1.5 && next_box.upper[1]>=1.5);
    auto propagated_ellipsoid=propagate_existential_control_ellipsoid(dynamics,
        {{0,0},{1,1}},{{-0.5},{0.5}},{});
    check(std::holds_alternative<FinitePlanEllipsoidTrace::Stage>(propagated_ellipsoid));
    const auto& next_e=std::get<FinitePlanEllipsoidTrace::Stage>(propagated_ellipsoid);
    check(next_e.radii[0]>=std::sqrt(2.0)*(std::sqrt(2.0)+0.5));
    auto propagated=propagate_existential_control_zonotope(dynamics,state,control,20,{},0);
    check(std::holds_alternative<FinitePlanZonotopeTrace::Stage>(propagated));
    const auto& next=std::get<FinitePlanZonotopeTrace::Stage>(propagated);
    check(next.generators.cols==4 && next.generators.values[0]==2 && next.generators.values[4]==1);
    check(next.generators.values[1]==0.5 && next.generators.values[5]==0.5);
    check(next.factors[0].value!=next.factors[1].value);
    auto dynamics4=model::DynamicsStage{matrix({4,4,{1,1,0,0, 0,1,0,0, 0,0,1,1, 0,0,0,1}}),
        matrix({4,0,{}}),matrix({4,0,{}}),vector({0,0,0,0})};
    FinitePlanZonotopeTrace::Stage state4{{0,0,0,0},{4,1,{1,1,1,1}},{{"coupled"}}};
    FinitePlanZonotopeTrace::Stage no_controls{{},{0,0,{}},{}};
    auto propagated4=propagate_existential_control_zonotope(dynamics4,state4,no_controls,20,{},1);
    check(std::holds_alternative<FinitePlanZonotopeTrace::Stage>(propagated4));
    const auto& next4=std::get<FinitePlanZonotopeTrace::Stage>(propagated4);
    check(next4.generators.values[0]==2 && next4.generators.values[5]==1 &&
        next4.generators.values[10]==2 && next4.generators.values[15]==1);
    auto duplicate=state;
    duplicate.factors[0].value="stage/0/u";
    auto invalid_factors=propagate_existential_control_zonotope(dynamics,duplicate,control,20,{},0);
    check(std::holds_alternative<Unsupported>(invalid_factors));
    // A negative inequality multiplier cannot justify the bound.
    check(std::holds_alternative<Diagnostics>(residual_corrected_support(input, {-1}, {})));
    // Equality multipliers and cross-coordinate support in four dimensions.
    BoundedHSupportInput four{{0,4,{}}, {}, {1,4,{1,1,0,0}}, {1},
        {-2,-2,-1,-1}, {2,2,1,1}, {1,1,1,1}};
    auto result4 = residual_corrected_support(four, {}, {1});
    check(std::holds_alternative<SupportUpperBound>(result4));
    check(std::get<SupportUpperBound>(result4).value >= 3);
    check(std::get<SupportUpperBound>(result4).value < 3.000000000001);

    auto registration=csl::adapters::lp::make_highs_registration();
    check(std::holds_alternative<csl::registry::Registration<csl::registry::LPPort>>(registration));
    auto entry=std::get<csl::registry::Registration<csl::registry::LPPort>>(std::move(registration));
    csl::registry::Registry<csl::registry::LPPort> registry;
    csl::registry::Method method{entry.identity.id,entry.identity.version};
    check(!registry.add(std::move(entry)).has_value());
    csl::registry::Requirements requirements;
    requirements.output.representation={"csl.program-result.v1"};
    auto prepared=csl::registry::prepare_provider(csl::registry::select_provider(registry,method,requirements));
    check(std::holds_alternative<csl::registry::PreparedProvider<csl::registry::LPPort>>(prepared));
    auto answer=bounded_h_support(input,{{"test"},{"dual"}},
        std::get<csl::registry::PreparedProvider<csl::registry::LPPort>>(prepared),{});
    check(std::holds_alternative<BoundedHSupportResult>(answer));
    const auto& solved=std::get<BoundedHSupportResult>(answer);
    check(solved.bound.value>=1 && solved.bound.value<1.00000001);
    auto replayed=residual_corrected_support(input,solved.bound.inequality_multipliers,solved.bound.equality_multipliers);
    check(std::holds_alternative<SupportUpperBound>(replayed));
    check(std::get<SupportUpperBound>(replayed).value==solved.bound.value);
    check(solved.lp_calls.size()==1);
    auto tiny_answer=bounded_h_support(tiny,{{"test"},{"dual-tiny"}},
        std::get<csl::registry::PreparedProvider<csl::registry::LPPort>>(prepared),{});
    // HiGHS rejects the candidate LP threshold. The carrier-only result uses
    // zero multipliers and retains that rejection without altering the H rows.
    check(std::holds_alternative<BoundedHSupportResult>(tiny_answer));
    const auto &tiny_result = std::get<BoundedHSupportResult>(tiny_answer);
    check(tiny_result.bound.method == SupportBoundMethod::carrier_only);
    check(tiny_result.bound.value >= 1 && tiny_result.lp_calls.size() == 1);
    auto numerical_failure = bounded_h_support(
        input, {{"test"}, {"carrier-fallback-numerical"}},
        fixed_result_provider(Termination::numerical_failure, MathematicalOutcome::undetermined),
        {});
    check(std::holds_alternative<BoundedHSupportResult>(numerical_failure));
    const auto &numerical_fallback = std::get<BoundedHSupportResult>(numerical_failure);
    check(numerical_fallback.bound.method == SupportBoundMethod::carrier_only);
    check(numerical_fallback.bound.value >= 1 && numerical_fallback.lp_calls.size() == 1);
    auto undetermined = bounded_h_support(
        input, {{"test"}, {"carrier-fallback-undetermined"}},
        fixed_result_provider(Termination::completed, MathematicalOutcome::undetermined), {});
    check(std::holds_alternative<BoundedHSupportResult>(undetermined));
    const auto &undetermined_fallback = std::get<BoundedHSupportResult>(undetermined);
    check(undetermined_fallback.bound.method == SupportBoundMethod::carrier_only);
    check(undetermined_fallback.bound.value >= 1 && undetermined_fallback.lp_calls.size() == 1);
    auto resource_limit = bounded_h_support(
        input, {{"test"}, {"carrier-fallback-resource-limit"}},
        fixed_result_provider(Termination::resource_limit, MathematicalOutcome::undetermined), {});
    check(std::holds_alternative<BoundedHSupportFailure>(resource_limit));
    const auto &resource_failure = std::get<BoundedHSupportFailure>(resource_limit);
    check(std::holds_alternative<OperationStopped>(resource_failure.cause));
    check(std::get<OperationStopped>(resource_failure.cause).reason == StopReason::resource_limit);
    auto four_answer=bounded_h_support(four,{{"test"},{"dual-four"}},
        std::get<csl::registry::PreparedProvider<csl::registry::LPPort>>(prepared),{});
    check(std::holds_alternative<BoundedHSupportResult>(four_answer));
    const auto four_bound=std::get<BoundedHSupportResult>(four_answer).bound.value;
    check(four_bound>=3 && four_bound<3.00000001);

    BoundedHSupportInput clip{{1,2,{1,1}}, {1}, {0,2,{}}, {},
        {-2,0}, {2,2}, {0,0}};
    auto cover=bounded_h_axis_cover(clip,{{"test"},{"axis"}},
        std::get<csl::registry::PreparedProvider<csl::registry::LPPort>>(prepared),{});
    check(std::holds_alternative<BoundedHAxisCover>(cover));
    const auto& box=std::get<BoundedHAxisCover>(cover);
    check(box.lower[0]<=-2 && box.upper[0]>=1 && box.upper[0]<1.00000001);
    check(box.lp_calls.size()==4 && box.certificates.size()==4);
    check(box.certificates[0].carrier_lower==clip.lower && box.certificates[0].carrier_upper==clip.upper);

    BoundedHSupportInput fixed{{0,2,{}}, {}, {0,2,{}}, {},
        {1,0}, {1,0}, {1,1}};
    auto fixed_bound=residual_corrected_support(fixed,{},{});
    check(std::holds_alternative<SupportUpperBound>(fixed_bound));
    check(std::get<SupportUpperBound>(fixed_bound).value>=1);
    check(std::get<SupportUpperBound>(fixed_bound).value<1.00000001);
}

// The production LP entry point accepts a registered provider and returns
// request records alongside the corrected bound.
void lp_api_must_exist(const csl::reachability::BoundedHSupportInput& input,
    const csl::registry::PreparedProvider<csl::registry::LPPort>& lp) {
    (void)csl::reachability::bounded_h_support(input, {{"support"},{"dual"}}, lp, {});
}

// API compilation gate for the staged full-state recurrence.
void coordinator_api_must_exist(const csl::problem::ResolvedProblem& problem,
    const csl::SetHandle& terminal,
    const csl::reachability::FeedbackGeometryDependencies& providers) {
    (void)csl::reachability::feedback_geometry(problem,{"analytic"},terminal,
        csl::reachability::FeedbackFamily::zonotope,{},providers,{});
}
