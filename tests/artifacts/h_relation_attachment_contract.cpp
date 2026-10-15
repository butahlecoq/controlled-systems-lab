#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/artifacts/h_relation_attachment.hpp>
#include <bit>
#include <type_traits>
using namespace csl;
namespace ar=csl::artifacts;
namespace {
ar::HRelationAttachmentLimits limits(){return {1'000'000,16,64,4096};}
template<class T>T take(std::variant<T,ar::ArtifactError> value){REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));}
sets::SetData source(){
 Matrix a{2,2,{1.0,-0.0,0.0,-2.0}},e{1,2,{3.0,4.0}};Vector b{5.0,-0.0},f{6.0};
 auto av=numeric::snapshot(a);auto bv=numeric::snapshot_vector(b);auto ev=numeric::snapshot(e);auto fv=numeric::snapshot_vector(f);
 REQUIRE(std::holds_alternative<numeric::MatrixView>(av));REQUIRE(std::holds_alternative<numeric::VectorView>(bv));
 REQUIRE(std::holds_alternative<numeric::MatrixView>(ev));REQUIRE(std::holds_alternative<numeric::VectorView>(fv));
 sets::AffineDimensionClaim claim{sets::DimensionValue{1},SymbolicArgument{"rank-note","caller supplied"}};
 auto made=sets::make_h({{"relation"},2,{"x","u"}},{std::get<numeric::MatrixView>(av),std::get<numeric::VectorView>(bv),std::get<numeric::MatrixView>(ev),std::get<numeric::VectorView>(fv)},claim);
 REQUIRE(std::holds_alternative<sets::SetData>(made));return std::get<sets::SetData>(std::move(made));
}
}
TEST_CASE("H attachment round trips ordered binary64 coefficients and supplied metadata"){
 static_assert(std::is_same_v<decltype(ar::decode_h_relation_attachment(std::span<const std::byte>{},limits())),ar::ArtifactResult<sets::SetData>>);
 const auto encoded=take(ar::encode_h_relation_attachment(source(),limits()));
 const auto decoded=take(ar::decode_h_relation_attachment(encoded.bytes(),limits(),encoded.digest()));
 const auto rep=decoded.representation();REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));const auto& h=std::get<sets::HRepresentation>(rep);
 CHECK(std::bit_cast<std::uint64_t>(h.inequalities(0,0))==std::bit_cast<std::uint64_t>(1.0));
 CHECK(std::bit_cast<std::uint64_t>(h.inequalities(0,1))==std::bit_cast<std::uint64_t>(-0.0));
 CHECK(std::bit_cast<std::uint64_t>(h.inequalities(1,0))==std::bit_cast<std::uint64_t>(0.0));
 CHECK(std::bit_cast<std::uint64_t>(h.upper_bounds[1])==std::bit_cast<std::uint64_t>(-0.0));
 const auto m=decoded.metadata();CHECK(m->id.value=="relation");CHECK(m->coordinate_labels==std::vector<std::string>{"x","u"});
 REQUIRE(m->affine_dimension.has_value());CHECK(m->affine_dimension->origin==sets::DimensionOrigin::supplied);
 CHECK(std::get<sets::DimensionValue>(m->affine_dimension->claim.value).value==1);
 const auto& support=std::get<SymbolicArgument>(m->affine_dimension->claim.support);CHECK(support.reference=="rank-note");CHECK(support.assumptions=="caller supplied");
}
TEST_CASE("H attachment rejects digest mismatch, malformed bytes and resource excess"){
 const auto encoded=take(ar::encode_h_relation_attachment(source(),limits()));
 std::array<std::byte,3> bad{std::byte{'b'},std::byte{'a'},std::byte{'d'}};
 CHECK(std::get<ar::ArtifactError>(ar::decode_h_relation_attachment(bad,limits(),encoded.digest())).code==ar::ArtifactErrorCode::identity);
 CHECK(std::get<ar::ArtifactError>(ar::decode_h_relation_attachment(encoded.bytes(),ar::HRelationAttachmentLimits{2,16,64,4096})).code==ar::ArtifactErrorCode::limit);
 auto corrupt=std::vector<std::byte>(encoded.bytes().begin(),encoded.bytes().end());corrupt.back()=std::byte{'x'};
 CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_h_relation_attachment(corrupt,limits())));`n auto unknown=std::vector<std::byte>(encoded.bytes().begin(),encoded.bytes().end());for(std::size_t i=0;i+1<unknown.size();++i)if(unknown[i]==std::byte{'/'}&&unknown[i+1]==std::byte{'1'})unknown[i+1]=std::byte{'9'};`n const auto unsupported=ar::decode_h_relation_attachment(unknown,limits());REQUIRE(std::holds_alternative<ar::ArtifactError>(unsupported));CHECK(std::get<ar::ArtifactError>(unsupported).code==ar::ArtifactErrorCode::unsupported);
}
