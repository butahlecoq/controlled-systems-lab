#include <csl/reachability/nominal_predecessor.hpp>
#include <iostream>
#include <stdexcept>

using namespace csl;
template<class T,class... E> T take(std::variant<T,E...> value) {
    if(!std::holds_alternative<T>(value)) throw std::runtime_error("Installed predecessor query rejected.");
    return std::get<T>(std::move(value));
}
bool contains(const sets::HRepresentation& h,double value) {
    for(std::size_t r=0;r<h.inequalities.rows();++r)
        if(h.inequalities(r,0)*value>h.upper_bounds[r]) return false;
    for(std::size_t r=0;r<h.equalities.rows();++r)
        if(h.equalities(r,0)*value!=h.equality_values[r]) return false;
    return true;
}
int main() {
    try {
        const auto x=take(sets::make_universal({{"X"},1,{"x"}}));
        const auto u=take(sets::make_h({{"U"},1,{}},
            {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{1,1})),
             take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))}));
        const auto s=take(sets::make_singleton({{"S"},1,{"x"}},take(numeric::snapshot_vector(Vector{2}))));
        reachability::NominalPredecessorRequest request{{{"installed"},{"predecessor"},{"ideal"}},
            x.as_handle(),u.as_handle(),s.as_handle(),{1,1,{1}},{1,1,{1}},{0}};
        auto selected=[] {
            registry::Registry<registry::GeometryPort> entries;
            const auto registration=geometry::polyhedral::make_projection_registration();
            if(entries.add(registration)) throw std::runtime_error("Registration rejected.");
            registry::Requirements requirements;
            requirements.output.representation={"csl.polyhedron.h"};
            requirements.output.relation=SetRelation::equivalent;
            return take(registry::prepare_provider(registry::select_provider(entries,
                {registration.identity.id,registration.identity.version},requirements)));
        }();
        const auto prepared=take(reachability::prepare_nominal_predecessor(request,selected));
        const auto result=take(prepared.run({}));
        const auto data=take(sets::from_handle(result.result.output));
        const auto representation=data.representation();
        const auto& h=std::get<sets::HRepresentation>(representation);
        if(!contains(h,1)||!contains(h,3)||contains(h,0.875)||contains(h,3.125) ||
                data.metadata()->coordinate_labels!=std::vector<std::string>{"x"} ||
                !std::holds_alternative<Unestablished>(result.result.evidence.support))
            throw std::runtime_error("Literal predecessor interval/evidence mismatch.");
        std::cout << "Installed predecessor client: existential integrator interval and unestablished support passed\n";
        return 0;
    } catch(const std::exception& failure) {
        std::cerr << failure.what() << '\n';return 1;
    }
}
