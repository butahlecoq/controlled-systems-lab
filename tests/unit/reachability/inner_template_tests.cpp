#include <csl/reachability/inner_template.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace csl;
using namespace csl::reachability;
void require(bool value) { if(!value) throw std::runtime_error("inner-template behavior failed"); }
int main() {
    InnerTemplateInput input{{0,0},{2,2,{1,0,0,1}},InnerTemplateNorm::independent_intervals,
        {4,2,{1,1,-1,-1,1,0,-1,0}},{1,1,1,1},{0,2,{}},{}};
    auto result=inscribe_template(input);
    require(std::holds_alternative<InnerTemplate>(result));
    auto box=std::get<InnerTemplate>(result);
    require(box.radius>0.49 && box.radius<=0.5);
    require(check_inner_template(input,box).empty());
    input.norm=InnerTemplateNorm::euclidean_ball;
    auto ellipse=std::get<InnerTemplate>(inscribe_template(input));
    require(ellipse.radius>box.radius && ellipse.radius<=std::sqrt(0.5));
    input.directions.values={0,0,0,0};
    auto point=std::get<InnerTemplate>(inscribe_template(input));
    require(point.point && point.radius==0);
    input.directions.values={1,0,0,1};
    input.equalities={1,2,{1,-1}};input.equality_values={0};
    point=std::get<InnerTemplate>(inscribe_template(input));
    require(point.point);
    input.directions={2,1,{1,1}};
    auto segment=std::get<InnerTemplate>(inscribe_template(input));
    require(!segment.point && segment.radius>0);
    require(check_inner_template(input,segment).empty());
    auto tampered=segment;tampered.factor.values={4,4};
    require(!check_inner_template(input,tampered).empty());
    input.center={2,2};
    require(std::holds_alternative<Diagnostic>(inscribe_template(input)));
    std::cout<<"ND inner templates: box, ellipsoid, point, affine hull and tampering passed\n";
}
