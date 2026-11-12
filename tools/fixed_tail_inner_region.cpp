#include <csl/reachability/inner_template.hpp>
#include <nlohmann/json.hpp>
#include <iostream>
#include <string>

using Json=nlohmann::json;
namespace {
csl::Matrix matrix(const Json& rows,std::size_t n) {
    csl::Matrix result{rows.size(),n,{}};
    for(const auto& row:rows) {
        if(row.size()!=n) throw std::invalid_argument("matrix row dimension differs");
        for(const auto& value:row) result.values.push_back(value.get<double>());
    }
    return result;
}
Json rows(const csl::Matrix& A) {
    Json out=Json::array();
    for(std::size_t i=0;i<A.rows;++i) {
        Json row=Json::array();
        for(std::size_t j=0;j<A.cols;++j) row.push_back(A.values[i*A.cols+j]);
        out.push_back(std::move(row));
    }
    return out;
}
Json run(const Json& in) {
    const auto center=in.at("center").get<csl::Vector>();
    const auto n=center.size();
    const auto count=in.at("factor_count").get<std::size_t>();
    const auto norm=in.at("support_norm").get<std::string>();
    if(norm!="l1" && norm!="l2") throw std::invalid_argument("unknown template support norm");
    auto directions=matrix(in.at("directions"),count);
    if(directions.rows!=n) throw std::invalid_argument("template state dimension differs");
    csl::reachability::InnerTemplateInput input{center,std::move(directions),
        norm=="l1" ? csl::reachability::InnerTemplateNorm::independent_intervals : csl::reachability::InnerTemplateNorm::euclidean_ball,
        matrix(in.at("inequalities"),n),in.at("upper_bounds").get<csl::Vector>(),
        matrix(in.value("equalities",Json::array()),n),in.value("equality_values",csl::Vector{})};
    const auto outcome=csl::reachability::inscribe_template(input);
    if(const auto* error=std::get_if<csl::Diagnostic>(&outcome))
        return {{"status","failed"},{"field",error->field},{"reason",error->explanation}};
    const auto& set=std::get<csl::reachability::InnerTemplate>(outcome);
    return {{"status","complete"},{"center",set.center},{"factor",rows(set.factor)},{"factor_count",set.factor.cols},
        {"support_norm",norm},{"factor_domain_norm",norm=="l2"?"l2":"linf"},
        {"radius",set.radius},{"point",set.point},{"rounding_shrinks",set.rounding_shrinks},
        {"row_support_upper",set.row_support_upper},{"row_slack_lower",set.row_slack_lower},
        {"provider","csl.reachability.inner-template/1"},{"relation","inner"},
        {"reference",{{"inequalities",in.at("inequalities")},{"upper_bounds",in.at("upper_bounds")},
                      {"equalities",in.value("equalities",Json::array())},{"equality_values",in.value("equality_values",csl::Vector{})}}},
        {"containment","outward-rounded admission against stored closed H rows"}};
}
}
int main() {
    std::string line;
    while(std::getline(std::cin,line)) {
        try { std::cout<<run(Json::parse(line)).dump()<<'\n'; }
        catch(const std::exception& e) { std::cout<<Json{{"status","failed"},{"reason",e.what()}}.dump()<<'\n'; }
        std::cout.flush();
    }
}
