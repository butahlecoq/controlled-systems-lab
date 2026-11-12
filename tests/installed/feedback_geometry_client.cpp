#include <csl/reachability/bounded_h_support.hpp>
#include <csl/reachability/feedback_geometry.hpp>
#include <variant>
#include <iostream>
int main() {
    using namespace csl;
    using namespace csl::reachability;
    BoundedHSupportInput input{{1,2,{1,1}},{1},{0,2,{}},{},{-2,-2},{2,2},{1,1}};
    auto support=residual_corrected_support(input,{0.9},{});
    if (!std::holds_alternative<SupportUpperBound>(support)) return 1;
    auto value=std::get<SupportUpperBound>(support);
    if (value.value<1.3 || value.value>1.300000001 || value.inequality_multipliers.size()!=1) return 2;
    auto result=axis_enclosure(FeedbackFamily::ellipsoid,{"installed"},{-1,-2},{1,2},{"x","y"});
    if (!std::holds_alternative<FeedbackMembership>(result)) return 3;
    const auto* ellipsoid=std::get_if<FeedbackEllipsoidMembership>(&std::get<FeedbackMembership>(result));
    if (!ellipsoid || ellipsoid->factor.rows!=2 || ellipsoid->factor.cols!=2) return 4;
    std::cout << "Installed feedback geometry client: corrected support and ellipsoid factor passed\n";
    return 0;
}
