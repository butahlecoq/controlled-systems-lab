#include <csl/problem/domains.hpp>
#include <csl/problem/constraints.hpp>
#include <csl/problem/initial_information.hpp>

#include <iostream>
#include <stdexcept>
#include <tuple>

namespace {
using namespace csl;
template<class T> T accepted(std::variant<T,Diagnostic> result) {
    if (const auto* error=std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field+": "+error->explanation);
    return std::get<T>(std::move(result));
}
void require(bool condition) {
    if (!condition) throw std::runtime_error("Installed problem literal differs.");
}
}

int main() {
    using namespace csl;
    try {
        const auto retained=[] {
            SystemModel raw{{{2,1,0},TimeDomain::discrete,LinearStage{
                {2,2,{1,0,0,1}},{2,1,{1,0}},{2,0,{}},{0,0}}},{}};
            auto model=accepted(model::snapshot(raw,Vector{0,1,2}));
            ControlDomain domain=FiniteDomain{1,{{-1},{1},{-1}}};
            InitialInformation initial=KnownInitial{{2,3}};
            auto singleton=accepted(sets::make_singleton({{"initial-stage"},2,{}},
                accepted(numeric::snapshot_vector(Vector{2,3}))));
            std::vector<AdmissibleSet> states{singleton.as_handle(),UniversalSet{2},EmptySet{2}};
            auto controls=accepted(problem::snapshot_controls(domain,model));
            auto point=accepted(problem::snapshot_initial(initial,model));
            auto external=accepted(problem::snapshot_external({},model));
            auto constraints=accepted(problem::snapshot_constraints(states,{},model));
            std::get<FiniteDomain>(domain).catalogue={{99}};
            std::get<KnownInitial>(initial).point={99,99}; states.clear();
            return std::tuple{controls.description(),point.description(),external.description(),constraints};
        }();
        require(std::get<FiniteDomain>(*std::get<0>(retained)).catalogue==std::vector<Vector>{{-1},{1},{-1}});
        require(std::get<KnownInitial>(*std::get<1>(retained)).point==Vector{2,3});
        require(!std::get<2>(retained)->has_value());
        const auto& constraints=std::get<3>(retained);
        require(constraints.joint_dimension()==8);
        require(accepted(constraints.state_offset({0}))==0 && accepted(constraints.state_offset({1}))==2 && accepted(constraints.state_offset({2}))==4);
        require(accepted(constraints.control_offset({0}))==6 && accepted(constraints.control_offset({1}))==7);
        require(std::get<EmptySet>((*constraints.states())[2]).dimension==2);
        auto temporal=[] {
            SystemModel raw{{{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}};
            auto model=accepted(model::snapshot(raw,Vector{0,1,2,3}));
            TemporalConstraints relation{{2,7,{0,3,5},{0,3,4,4,6},{-2,1,1,-1,1}},{{7,7},{-0.25,0.25}}};
            auto data=accepted(problem::snapshot_constraints(std::vector<AdmissibleSet>(4,UniversalSet{1}),relation,model));
            relation.joint_map.values.clear(); relation.bounds.clear();
            return *data.temporal();
        }();
        require(accepted(numeric::multiply(temporal.joint_map,accepted(numeric::snapshot_vector(Vector{1,0,0,8,1,0,1.25}))))==Vector{7,0.25});
        require(temporal.bounds->at(1).lower==-0.25 && temporal.bounds->at(1).upper==0.25);
        std::cout << "Installed problem client: immutable domains and full-history literals passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
