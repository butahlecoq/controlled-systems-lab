#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/sets/data.hpp>
#include <array>
#include <cmath>
#include <iostream>
#include <variant>

namespace {
template<class T,class... U> T take(std::variant<T,U...> value) {
    if (!std::holds_alternative<T>(value)) throw 1;
    return std::get<T>(std::move(value));
}
}

int main() {
    using namespace csl;
    auto a=take(numeric::snapshot(Matrix{4,2,{1,0,-1,0,0,1,0,-1}}));
    auto b=take(numeric::snapshot_vector(Vector{1,0,1,0}));
    auto e=take(numeric::snapshot(Matrix{0,2,{}}));
    auto f=take(numeric::snapshot_vector(Vector{}));
    auto input=take(sets::make_h({{"installed-square"},2,{}},{a,b,e,f})).as_handle();
    auto lp=take(adapters::lp::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(std::move(lp)));
    registry::Registry<registry::ConversionPort> conversions;
    if (conversions.add(std::move(converter))) return 2;
    ConversionRequest request{{{"installed"},{"square"},{"square-ideal"}},input,{"csl.polyhedron.v"},Assurance::numerical};
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.assurance=Assurance::numerical;
    requirements.output.relation=SetRelation::equivalent;
    auto prepared=registry::prepare_pipeline(registry::select(conversions,{{"csl.conversion.qhull"},{}},request,requirements));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::ConversionPort>>(prepared)) return 3;
    auto [worker]=std::get<registry::PreparedPipeline<registry::ConversionPort>>(prepared).create();
    ExecutionContext context{{},{},{},{1e-8,1e-8},"installed-conversion"};
    auto outcome=worker->run(context);
    if (!std::holds_alternative<OperationResult>(outcome)) return 4;
    auto converted=take(sets::from_handle(std::get<OperationResult>(outcome).output));
    const auto rep=converted.representation();
    if (!std::holds_alternative<sets::VRepresentation>(rep)) return 5;
    const auto& vertices=std::get<sets::VRepresentation>(rep).vertices;
    bool origin=false, upper=false;
    for (std::size_t i=0;i<vertices.rows();++i) {
        origin=origin||(std::abs(vertices(i,0))<1e-7&&std::abs(vertices(i,1))<1e-7);
        upper=upper||(std::abs(vertices(i,0)-1)<1e-7&&std::abs(vertices(i,1)-1)<1e-7);
    }
    if (!origin||!upper) return 6;
    std::cout << "Installed Qhull conversion client: registered square conversion and literal vertices passed\n";
    return 0;
}
