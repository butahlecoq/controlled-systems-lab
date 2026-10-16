#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/sets/generator_sets.hpp>
#include <csl/geometry/generators.hpp>

#include <cmath>
#include <limits>

using namespace csl;
using namespace csl::sets;
using namespace csl::geometry::generators;

namespace {
template<class T> T accepted(std::variant<T, Diagnostics> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

GeneratorSet interval(std::string id, double generator, std::string factor) {
    return accepted(make_generator_set({{std::move(id)}, {0}, {1,1,{generator}},
        {{std::move(factor)}}, {0,1,{}}, {}, {}}));
}

// Independent H-polyhedron membership query over the lifted factor space.
bool in_factor_polyhedron(const GeneratorSet& set, const Vector& factors) {
    const auto lift = accepted(factor_polyhedron(set));
    const auto h = std::get<HRepresentation>(lift.factors.representation());
    if (factors.size() != h.inequalities.cols()) return false;
    for (std::size_t i=0; i<h.inequalities.rows(); ++i) {
        double lhs=0;
        for (std::size_t j=0; j<factors.size(); ++j) lhs+=h.inequalities(i,j)*factors[j];
        if (lhs>h.upper_bounds[i]) return false;
    }
    for (std::size_t i=0; i<h.equalities.rows(); ++i) {
        double lhs=0;
        for (std::size_t j=0; j<factors.size(); ++j) lhs+=h.equalities(i,j)*factors[j];
        if (lhs!=h.equality_values[i]) return false;
    }
    return true;
}

// Independently authored physical H reference, not derived from a generator set.
bool in_reference_h(const HRepresentation& h, const Vector& point) {
    if (point.size()!=h.inequalities.cols()) return false;
    for (std::size_t i=0;i<h.inequalities.rows();++i) {
        double activity=0;
        for (std::size_t j=0;j<point.size();++j) activity+=h.inequalities(i,j)*point[j];
        if (activity>h.upper_bounds[i]) return false;
    }
    for (std::size_t i=0;i<h.equalities.rows();++i) {
        double activity=0;
        for (std::size_t j=0;j<point.size();++j) activity+=h.equalities(i,j)*point[j];
        if (activity!=h.equality_values[i]) return false;
    }
    return true;
}

HRepresentation h_reference(const Matrix& inequalities,const Vector& upper,
                            const Matrix& equalities,const Vector& values) {
    return {std::get<numeric::MatrixView>(numeric::snapshot(inequalities)),
        std::get<numeric::VectorView>(numeric::snapshot_vector(upper)),
        std::get<numeric::MatrixView>(numeric::snapshot(equalities)),
        std::get<numeric::VectorView>(numeric::snapshot_vector(values))};
}
}

TEST_CASE("box affine image keeps factor IDs and agrees with H-polyhedron corner queries") {
    const auto box=accepted(make_generator_set({{"box"}, {1,2}, {2,2,{2,0,0,3}},
        {{"horizontal"},{"vertical"}}, {0,2,{}}, {}, {"x","y"}}));
    const auto image=accepted(affine_image(box,{1,2,{1,1}},{4},{"image"}));
    CHECK(image.center()==Vector{7});
    CHECK(image.generators().values==Vector{2,3});
    CHECK(image.factor_ids()==std::vector<FactorId>{{"horizontal"},{"vertical"}});
    CHECK(in_factor_polyhedron(image,{-1,-1}));
    CHECK(in_factor_polyhedron(image,{1,1}));
    CHECK_FALSE(in_factor_polyhedron(image,{2,0}));
    const auto reference=h_reference({4,2,{1,0,-1,0,0,1,0,-1}},
        {3,1,5,1},{0,2,{}},{});
    for (const double x:Vector{-1,3}) for (const double y:Vector{-1,5}) {
        CHECK(in_reference_h(reference,{x,y}));
        const double via_image=image.center()[0]+image.generators().values[0]*((x-1)/2)
            +image.generators().values[1]*((y-2)/3);
        CHECK(via_image==x+y+4);
    }
    // The independent box H oracle gives x in [-1,3], y in [-1,5].
    // Its four corners mapped by x+y+4 have extrema 2 and 12.
    CHECK(image.center()[0]-std::abs(image.generators().values[0])-
        std::abs(image.generators().values[1])==2);
    CHECK(image.center()[0]+std::abs(image.generators().values[0])+
        std::abs(image.generators().values[1])==12);
}

TEST_CASE("synchronized sum cancels a shared factor while independent Minkowski rejects aliasing") {
    const auto left=interval("left",1,"history.0");
    const auto right=interval("right",-1,"history.0");
    const auto sum=accepted(dependent_sum(left,right,{"cancelled"}));
    CHECK(sum.factor_ids()==std::vector<FactorId>{{"history.0"}});
    CHECK(sum.generators().values==Vector{0});
    CHECK(sum.center()==Vector{0});
    CHECK(in_factor_polyhedron(sum,{-1}));
    CHECK(in_factor_polyhedron(sum,{1}));
    const auto origin=h_reference({0,1,{}},{},{1,1,{1}},{0});
    CHECK(in_reference_h(origin,{sum.center()[0]+sum.generators().values[0]}));
    CHECK_FALSE(in_reference_h(origin,{2}));
    const auto independent=minkowski_sum(left,right,{"not-allowed"});
    REQUIRE(std::holds_alternative<Diagnostics>(independent));
    CHECK(std::get<Diagnostics>(independent).front().code==DiagnosticCode::unsupported);
    const auto fresh=interval("fresh",-1,"history.1");
    const auto proper=accepted(minkowski_sum(left,fresh,{"independent"}));
    CHECK(proper.factor_ids()==std::vector<FactorId>{{"history.0"},{"history.1"}});
    CHECK(proper.generators().values==Vector{1,-1});
}

TEST_CASE("constrained equalities survive image and dependent sum") {
    const auto constrained=accepted(make_generator_set({{"diagonal"}, {0,0},
        {2,2,{1,0,0,1}}, {{"u"},{"v"}}, {1,2,{1,-1}}, {0}, {}}));
    const auto image=accepted(affine_image(constrained,{1,2,{1,-1}},{0},{"difference"}));
    CHECK(image.equalities().rows==1);
    CHECK(image.equalities().values==Vector{1,-1});
    CHECK(image.equality_values()==Vector{0});
    CHECK(in_factor_polyhedron(image,{1,1}));
    CHECK_FALSE(in_factor_polyhedron(image,{1,-1}));
    const auto diagonal=h_reference({4,2,{1,0,-1,0,0,1,0,-1}},
        {1,1,1,1},{1,2,{1,-1}},{0});
    CHECK(in_reference_h(diagonal,{1,1}));
    CHECK_FALSE(in_reference_h(diagonal,{1,-1}));
    const auto sum=accepted(dependent_sum(constrained,constrained,{"twice"}));
    CHECK(sum.factor_ids()==std::vector<FactorId>{{"u"},{"v"}});
    CHECK(sum.equalities().rows==2);
    CHECK(sum.equalities().values==Vector{1,-1,1,-1});
    CHECK(in_factor_polyhedron(sum,{0.5,0.5}));
    CHECK_FALSE(in_factor_polyhedron(sum,{0.5,-0.5}));
}

TEST_CASE("generator data rejects invalid identities, shapes and nonfinite arithmetic") {
    auto invalid=make_generator_set({{"duplicate"},{0},{1,2,{1,2}},
        {{"same"},{"same"}},{0,2,{}},{},{}});
    REQUIRE(std::holds_alternative<Diagnostics>(invalid));
    invalid=make_generator_set({{"nonfinite"},{0},{1,1,{std::numeric_limits<double>::infinity()}},
        {{"u"}},{0,1,{}},{},{}});
    REQUIRE(std::holds_alternative<Diagnostics>(invalid));
    invalid=make_generator_set({{"bad-equality"},{0},{1,1,{1}},
        {{"u"}},{1,1,{1}},{},{}});
    REQUIRE(std::holds_alternative<Diagnostics>(invalid));
    const auto full=interval("full",std::numeric_limits<double>::max(),"full");
    const auto overflow=affine_image(full,{1,1,{2}},{0},{"overflow"});
    CHECK(std::holds_alternative<Diagnostics>(overflow));
    const auto ordinary=interval("ordinary",1,"id");
    auto forged=ordinary.as_handle();
    forged.metadata.representation={"csl.polyhedron.h"};
    CHECK(std::holds_alternative<Diagnostics>(from_generator_handle(forged)));
    CHECK(std::holds_alternative<GeneratorSet>(from_generator_handle(ordinary.as_handle())));
}
