#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/artifacts/h_relation_attachment.hpp>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include <bit>
#include <array>
#include <string>
#include <type_traits>
using namespace csl;
namespace ar=csl::artifacts;
namespace {
ar::HRelationAttachmentLimits limits(){return {1'000'000,16,64,4096};}
template<class T>T take(std::variant<T,ar::ArtifactError> value){REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));}
sets::SetData source(EvidenceSupport evidence=SymbolicArgument{"rank-note","caller supplied"},std::string id="relation"){
 Matrix a{2,2,{1.0,-0.0,0.0,-2.0}},e{1,2,{3.0,4.0}};Vector b{5.0,-0.0},f{6.0};
 auto av=numeric::snapshot(a);auto bv=numeric::snapshot_vector(b);auto ev=numeric::snapshot(e);auto fv=numeric::snapshot_vector(f);
 REQUIRE(std::holds_alternative<numeric::MatrixView>(av));REQUIRE(std::holds_alternative<numeric::VectorView>(bv));REQUIRE(std::holds_alternative<numeric::MatrixView>(ev));REQUIRE(std::holds_alternative<numeric::VectorView>(fv));
 sets::AffineDimensionClaim claim{sets::DimensionValue{1},std::move(evidence)};
 auto made=sets::make_h({{std::move(id)},2,{"x","u"}},{std::get<numeric::MatrixView>(av),std::get<numeric::VectorView>(bv),std::get<numeric::MatrixView>(ev),std::get<numeric::VectorView>(fv)},claim);
 REQUIRE(std::holds_alternative<sets::SetData>(made));return std::get<sets::SetData>(std::move(made));
}
ExactFarkasEvidence exact_farkas(){
 auto lp=optimization::make_linear_program({{{"farkas"},{"row-infeasible"}},{0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{1,{}},{{},0}}});
 REQUIRE(std::holds_alternative<LinearProgram>(lp));const auto& program=std::get<LinearProgram>(lp);
 LinearInfeasibilityCertificate cert{program.identity(),{1,0},{0,1},{0},{0}};
 auto checked=optimization::verify_linear_infeasibility_certificate(program,cert);REQUIRE(std::holds_alternative<ExactFarkasEvidence>(checked));return std::get<ExactFarkasEvidence>(std::move(checked));
}
}
TEST_CASE("H attachment round trips ordered binary64 coefficients and metadata into an inert DTO"){
 static_assert(std::is_same_v<decltype(ar::decode_h_relation_attachment(std::span<const std::byte>{},limits())),ar::ArtifactResult<ar::RecordedHRelation>>);
 static_assert(!std::is_same_v<ar::RecordedHRelation,sets::SetData>);
 const auto encoded=take(ar::encode_h_relation_attachment(source(),limits()));auto exact_size_limits=limits();exact_size_limits.max_bytes=encoded.bytes().size();CHECK(std::holds_alternative<problem::ResolvedContent>(ar::encode_h_relation_attachment(source(),exact_size_limits)));const auto decoded=take(ar::decode_h_relation_attachment(encoded.bytes(),limits(),encoded.digest()));
 CHECK(decoded.id.value=="relation");CHECK(decoded.metadata.dimension==2);CHECK(decoded.coordinate_labels==std::vector<std::string>{"x","u"});
 REQUIRE(decoded.affine_dimension.has_value());CHECK(decoded.affine_dimension->origin==sets::DimensionOrigin::supplied);CHECK(std::get<sets::DimensionValue>(decoded.affine_dimension->value).value==1);
 const auto& support=std::get<ar::RecordedSymbolicArgument>(decoded.affine_dimension->support);CHECK(support.reference=="rank-note");CHECK(support.assumptions=="caller supplied");
 const auto& h=decoded.representation;CHECK(std::bit_cast<std::uint64_t>(h.inequalities(0,0))==std::bit_cast<std::uint64_t>(1.0));CHECK(std::bit_cast<std::uint64_t>(h.inequalities(0,1))==std::bit_cast<std::uint64_t>(-0.0));CHECK(std::bit_cast<std::uint64_t>(h.inequalities(1,0))==std::bit_cast<std::uint64_t>(0.0));CHECK(std::bit_cast<std::uint64_t>(h.inequalities(1,1))==std::bit_cast<std::uint64_t>(-2.0));CHECK(std::bit_cast<std::uint64_t>(h.upper_bounds[0])==std::bit_cast<std::uint64_t>(5.0));CHECK(std::bit_cast<std::uint64_t>(h.upper_bounds[1])==std::bit_cast<std::uint64_t>(-0.0));CHECK(h.equalities.rows()==1);CHECK(std::bit_cast<std::uint64_t>(h.equalities(0,0))==std::bit_cast<std::uint64_t>(3.0));CHECK(std::bit_cast<std::uint64_t>(h.equalities(0,1))==std::bit_cast<std::uint64_t>(4.0));CHECK(std::bit_cast<std::uint64_t>(h.equality_values[0])==std::bit_cast<std::uint64_t>(6.0));
}
TEST_CASE("verified Farkas metadata round trips only as untrusted recorded certificate fields"){
 const auto proof=exact_farkas();const auto encoded=take(ar::encode_h_relation_attachment(source(EvidenceSupport{proof}),limits()));const auto decoded=take(ar::decode_h_relation_attachment(encoded.bytes(),limits()));
 REQUIRE(decoded.affine_dimension.has_value());const auto* recorded=std::get_if<ar::RecordedExactFarkasEvidence>(&decoded.affine_dimension->support);REQUIRE(recorded);
 CHECK(recorded->certificate.subject==proof.subject());CHECK(recorded->certificate.row_lower==proof.certificate().row_lower);CHECK(recorded->certificate.row_upper==proof.certificate().row_upper);CHECK(recorded->certificate.variable_lower==proof.certificate().variable_lower);CHECK(recorded->certificate.variable_upper==proof.certificate().variable_upper);
  auto decoder_row_limit=limits();decoder_row_limit.max_rows=4;const auto rejected=ar::decode_h_relation_attachment(encoded.bytes(),decoder_row_limit);REQUIRE(std::holds_alternative<ar::ArtifactError>(rejected));CHECK(std::get<ar::ArtifactError>(rejected).code==ar::ArtifactErrorCode::limit);CHECK(std::get<ar::ArtifactError>(rejected).path=="attachment.evidence.rows");
 const auto bounded=ar::encode_h_relation_attachment(source(EvidenceSupport{proof}),ar::HRelationAttachmentLimits{1'000'000,16,3,4096});REQUIRE(std::holds_alternative<ar::ArtifactError>(bounded));CHECK(std::get<ar::ArtifactError>(bounded).code==ar::ArtifactErrorCode::limit);
 static_assert(!std::is_same_v<ar::RecordedExactFarkasEvidence,ExactFarkasEvidence>);
}
TEST_CASE("other affine evidence variants remain recorded data"){
 const auto numerical=take(ar::encode_h_relation_attachment(source(EvidenceSupport{NumericalCheck{-0.0,0.25,1e-9,ModuleId{"numeric-checker"}}}),limits()));
 const auto numeric_record=take(ar::decode_h_relation_attachment(numerical.bytes(),limits()));const auto& n=std::get<ar::RecordedNumericalCheck>(numeric_record.affine_dimension->support);
 CHECK(std::bit_cast<std::uint64_t>(n.absolute_tolerance)==std::bit_cast<std::uint64_t>(-0.0));CHECK(std::bit_cast<std::uint64_t>(n.relative_tolerance)==std::bit_cast<std::uint64_t>(0.25));CHECK(std::bit_cast<std::uint64_t>(n.max_residual)==std::bit_cast<std::uint64_t>(1e-9));CHECK(n.verifier.value=="numeric-checker");
 const auto certificate=take(ar::encode_h_relation_attachment(source(EvidenceSupport{CertificateReference{"proof.bin","untrusted-ref"}}),limits()));
 const auto cert_record=take(ar::decode_h_relation_attachment(certificate.bytes(),limits()));const auto& c=std::get<ar::RecordedCertificateReference>(cert_record.affine_dimension->support);CHECK(c.artifact=="proof.bin");CHECK(c.verifier=="untrusted-ref");
 const auto absent=take(ar::encode_h_relation_attachment(source(EvidenceSupport{Unestablished{}}),limits()));const auto absent_record=take(ar::decode_h_relation_attachment(absent.bytes(),limits()));CHECK(std::holds_alternative<Unestablished>(absent_record.affine_dimension->support));
}
TEST_CASE("evidence text over the caller budget returns a typed limit error"){
 auto constrained=limits();constrained.max_text_bytes=12; // id and labels consume 11 bytes.
 const std::array<EvidenceSupport,4> supports{
  SymbolicArgument{"rank-note","caller supplied"},
  CertificateReference{"proof.bin","untrusted-ref"},
  NumericalCheck{-0.0,0.25,1e-9,ModuleId{"numeric-checker"}},
  exact_farkas()
 };
 for(const auto& evidence:supports){
  const auto encoded=take(ar::encode_h_relation_attachment(source(evidence),limits()));
  const auto decoded=ar::decode_h_relation_attachment(encoded.bytes(),constrained);
  REQUIRE(std::holds_alternative<ar::ArtifactError>(decoded));
  CHECK(std::get<ar::ArtifactError>(decoded).code==ar::ArtifactErrorCode::limit);
  CHECK(std::get<ar::ArtifactError>(decoded).path=="attachment.text");
 }
}
TEST_CASE("H attachment byte preflight includes metadata text before JSON construction"){
 auto constrained=limits();constrained.max_bytes=200;const auto result=ar::encode_h_relation_attachment(source(SymbolicArgument{"r","a"},std::string(256,'r')),constrained);REQUIRE(std::holds_alternative<ar::ArtifactError>(result));CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);CHECK(std::get<ar::ArtifactError>(result).path=="attachment.bytes");
}
TEST_CASE("H attachment rejects digest mismatch, malformed bytes, unknown version, and resource excess"){
 const auto encoded=take(ar::encode_h_relation_attachment(source(),limits()));std::array<std::byte,3> bad{std::byte{'b'},std::byte{'a'},std::byte{'d'}};
 CHECK(std::get<ar::ArtifactError>(ar::decode_h_relation_attachment(bad,limits(),encoded.digest())).code==ar::ArtifactErrorCode::identity);
 CHECK(std::get<ar::ArtifactError>(ar::decode_h_relation_attachment(encoded.bytes(),ar::HRelationAttachmentLimits{2,16,64,4096})).code==ar::ArtifactErrorCode::limit);
 auto corrupt=std::vector<std::byte>(encoded.bytes().begin(),encoded.bytes().end());corrupt.back()=std::byte{'x'};CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_h_relation_attachment(corrupt,limits())));
 auto truncated=std::vector<std::byte>(encoded.bytes().begin(),encoded.bytes().end()-1);CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_h_relation_attachment(truncated,limits())));
 std::string nonfinite;for(auto b:encoded.bytes())nonfinite.push_back(static_cast<char>(std::to_integer<unsigned char>(b)));const auto coefficient=nonfinite.find("3ff0000000000000");REQUIRE(coefficient!=std::string::npos);nonfinite.replace(coefficient,16,"7ff0000000000000");std::vector<std::byte> nonfinite_bytes;for(unsigned char c:nonfinite)nonfinite_bytes.push_back(static_cast<std::byte>(c));CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_h_relation_attachment(nonfinite_bytes,limits())));
 auto unknown=std::vector<std::byte>(encoded.bytes().begin(),encoded.bytes().end());for(std::size_t i=0;i+1<unknown.size();++i)if(unknown[i]==std::byte{'/'}&&unknown[i+1]==std::byte{'1'})unknown[i+1]=std::byte{'9'};
 const auto unsupported=ar::decode_h_relation_attachment(unknown,limits());REQUIRE(std::holds_alternative<ar::ArtifactError>(unsupported));CHECK(std::get<ar::ArtifactError>(unsupported).code==ar::ArtifactErrorCode::unsupported);
 auto trailing=std::vector<std::byte>(encoded.bytes().begin(),encoded.bytes().end());trailing.push_back(std::byte{' '});const auto trailing_result=ar::decode_h_relation_attachment(trailing,limits());REQUIRE(std::holds_alternative<ar::ArtifactError>(trailing_result));CHECK(std::get<ar::ArtifactError>(trailing_result).path=="attachment.trailing_bytes");
 std::string bad_shape;for(auto b:encoded.bytes())bad_shape.push_back(static_cast<char>(std::to_integer<unsigned char>(b)));const auto col=bad_shape.find("\"cols\":\"2\"");REQUIRE(col!=std::string::npos);bad_shape.replace(col,9,"\"cols\":\"3\"");std::vector<std::byte> shape_bytes;for(unsigned char c:bad_shape)shape_bytes.push_back(static_cast<std::byte>(c));CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_h_relation_attachment(shape_bytes,limits())));
}
