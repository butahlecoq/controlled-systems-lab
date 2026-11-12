#include <csl/reachability/bounded_h_support.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/reachability/feedback_geometry.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <cstdlib>

void check(bool condition) { if (!condition) std::abort(); }
#include <cmath>
#include <variant>

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
    check(solved.lp_calls.size()==1);
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
    check(box.lp_calls.size()==4);

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
