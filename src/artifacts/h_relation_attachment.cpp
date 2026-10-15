#include <csl/artifacts/h_relation_attachment.hpp>
#include <nlohmann/json.hpp>
#include <bit>
#include <charconv>
#include <limits>

namespace csl::artifacts {
namespace {
using Json=nlohmann::ordered_json;
ArtifactError error(ArtifactErrorCode code,std::string path,std::string message){return {code,std::move(path),std::move(message)};}
using Bytes=std::vector<std::byte>;
std::string bits(double value){char out[16];auto result=std::to_chars(out,out+sizeof(out),std::bit_cast<std::uint64_t>(value),16);std::string s(16-(result.ptr-out),'0');s.append(out,result.ptr);return s;}
double number(const Json& j){if(!j.is_string()||j.get_ref<const std::string&>().size()!=16)throw std::runtime_error("Expected 16 hexadecimal binary64 digits");std::uint64_t v{};auto s=j.get<std::string>();auto r=std::from_chars(s.data(),s.data()+s.size(),v,16);if(r.ec!=std::errc{}||r.ptr!=s.data()+s.size())throw std::runtime_error("Invalid binary64 bits");return std::bit_cast<double>(v);}
Json support(const EvidenceSupport& v){return std::visit([](const auto& x)->Json{using T=std::decay_t<decltype(x)>;
 if constexpr(std::is_same_v<T,Unestablished>)return {{"kind","unestablished"}};
 else if constexpr(std::is_same_v<T,NumericalCheck>)return {{"kind","numerical_check"},{"absolute_tolerance",bits(x.absolute_tolerance)},{"relative_tolerance",bits(x.relative_tolerance)},{"max_residual",bits(x.max_residual)},{"verifier",x.verifier.value}};
 else if constexpr(std::is_same_v<T,SymbolicArgument>)return {{"kind","symbolic_argument"},{"reference",x.reference},{"assumptions",x.assumptions}};
 else return {{"kind","certificate_reference"},{"artifact",x.artifact},{"verifier",x.verifier}};
 },v);}
EvidenceSupport support(const Json& j){const auto k=j.at("kind").get<std::string>();if(k=="unestablished")return Unestablished{};
 if(k=="numerical_check")return NumericalCheck{number(j.at("absolute_tolerance")),number(j.at("relative_tolerance")),number(j.at("max_residual")),ModuleId{j.at("verifier").get<std::string>()}};
 if(k=="symbolic_argument")return SymbolicArgument{j.at("reference").get<std::string>(),j.at("assumptions").get<std::string>()};
 if(k=="certificate_reference")return CertificateReference{j.at("artifact").get<std::string>(),j.at("verifier").get<std::string>()};
 throw std::runtime_error("Unknown evidence support variant");}
std::uint64_t u64(const Json& j){if(!j.is_string())throw std::runtime_error("Expected unsigned integer string");std::uint64_t v{};auto s=j.get<std::string>();auto r=std::from_chars(s.data(),s.data()+s.size(),v);if(r.ec!=std::errc{}||r.ptr!=s.data()+s.size())throw std::runtime_error("Invalid unsigned integer");return v;}
std::string text(const Json& j){if(!j.is_string())throw std::runtime_error("Expected text");return j.get<std::string>();}
bool valid_limits(HRelationAttachmentLimits l){return l.max_bytes>0&&l.max_dimension>0&&l.max_rows>0&&l.max_text_bytes>0;}
std::optional<ArtifactError> text_limit(std::uint64_t& total,std::string_view s,HRelationAttachmentLimits l){if(s.size()>l.max_text_bytes||total>l.max_text_bytes-s.size())return error(ArtifactErrorCode::limit,"attachment.text","Metadata text limit exceeded");total+=s.size();return {};}
Json matrix(const numeric::MatrixView& m){Json values=Json::array();for(std::size_t r=0;r<m.rows();++r)for(std::size_t c=0;c<m.cols();++c)values.push_back(bits(m(r,c)));return {{"rows",std::to_string(m.rows())},{"cols",std::to_string(m.cols())},{"bits",std::move(values)}};}
std::vector<double> coefficients(const Json& j,std::uint64_t rows,std::uint64_t cols){if(u64(j.at("rows"))!=rows||u64(j.at("cols"))!=cols)throw std::runtime_error("Matrix shape mismatch");if(cols!=0&&rows>std::numeric_limits<std::uint64_t>::max()/cols)throw std::runtime_error("Matrix coefficient count overflow");const auto& a=j.at("bits");if(!a.is_array()||a.size()!=rows*cols)throw std::runtime_error("Coefficient count mismatch");std::vector<double> out;out.reserve(a.size());for(const auto& x:a)out.push_back(number(x));return out;}
}
ArtifactResult<problem::ResolvedContent> encode_h_relation_attachment(const sets::SetData& set,HRelationAttachmentLimits limits){
 if(!valid_limits(limits))return error(ArtifactErrorCode::invalid_input,"attachment.limits","All attachment limits must be positive");
 try {const auto m=set.metadata();const auto rep=set.representation();const auto* h=std::get_if<sets::HRepresentation>(&rep);
  if(!h)return error(ArtifactErrorCode::unsupported,"attachment.representation","Only H-representation set data is supported");
  if(m->set.representation.value!="csl.polyhedron.h"||m->set.convex!=SetProperty::yes||m->set.polyhedral!=SetProperty::yes||m->set.bounded!=SetProperty::unknown||(m->affine_dimension&&m->affine_dimension->origin!=sets::DimensionOrigin::supplied))
   return error(ArtifactErrorCode::invalid_input,"attachment.metadata","H metadata does not match the public SetData factory contract");
  const auto dim=m->set.dimension;const auto ir=h->inequalities.rows(),er=h->equalities.rows();if(ir>limits.max_rows||er>limits.max_rows-ir)return error(ArtifactErrorCode::limit,"attachment.shape","Dimension or row limit exceeded");const auto rows=ir+er;
  if(dim>limits.max_dimension)return error(ArtifactErrorCode::limit,"attachment.shape","Dimension or row limit exceeded");if(dim&&rows>limits.max_bytes/18/dim)return error(ArtifactErrorCode::limit,"attachment.coefficients","Coefficient count exceeds byte budget");
  std::uint64_t txt=0;if(auto e=text_limit(txt,m->id.value,limits))return *e;for(const auto& label:m->coordinate_labels)if(auto e=text_limit(txt,label,limits))return *e;if(m->affine_dimension)std::visit([&](const auto& x){using T=std::decay_t<decltype(x)>;if constexpr(std::is_same_v<T,SymbolicArgument>){if(auto e=text_limit(txt,x.reference,limits))throw std::length_error(e->message);if(auto e=text_limit(txt,x.assumptions,limits))throw std::length_error(e->message);}else if constexpr(std::is_same_v<T,CertificateReference>){if(auto e=text_limit(txt,x.artifact,limits))throw std::length_error(e->message);if(auto e=text_limit(txt,x.verifier,limits))throw std::length_error(e->message);}else if constexpr(std::is_same_v<T,NumericalCheck>){if(auto e=text_limit(txt,x.verifier.value,limits))throw std::length_error(e->message);}},m->affine_dimension->claim.support);
  Json affine=nullptr;if(m->affine_dimension){const auto& a=m->affine_dimension->claim;Json value;
   if(std::holds_alternative<EmptyAffineDimension>(a.value))value={{"kind","empty"}};else value={{"kind","dimension"},{"value",std::to_string(std::get<DimensionValue>(a.value).value)}};
   affine={{"origin","supplied"},{"value",std::move(value)},{"support",support(a.support)}};
  }
  Json j={{"schema","csl.h-relation-attachment/1"},{"id",m->id.value},{"dimension",std::to_string(dim)},
   {"representation",m->set.representation.value},{"convex","yes"},{"polyhedral","yes"},{"bounded","unknown"},
   {"labels",m->coordinate_labels},{"affine_dimension",std::move(affine)},
   {"inequalities",matrix(h->inequalities)},{"upper_bounds",Json::array()},{"equalities",matrix(h->equalities)},{"equality_values",Json::array()}};
  for(double x:h->upper_bounds.values())j["upper_bounds"].push_back(bits(x));for(double x:h->equality_values.values())j["equality_values"].push_back(bits(x));
  const auto s=j.dump();if(s.size()>limits.max_bytes)return error(ArtifactErrorCode::limit,"attachment.bytes","Encoded attachment exceeds byte limit");
  Bytes b; b.reserve(s.size());for(unsigned char c:s)b.push_back(static_cast<std::byte>(c));auto result=problem::snapshot_content(b);
  if(auto* content=std::get_if<problem::ResolvedContent>(&result))return *content;
  return error(ArtifactErrorCode::allocation,"attachment.content","Could not own encoded attachment bytes");
 }catch(const std::exception& e){return error(ArtifactErrorCode::invalid_input,"attachment.encode",e.what());}
}
ArtifactResult<sets::SetData> decode_h_relation_attachment(std::span<const std::byte> bytes,HRelationAttachmentLimits limits,std::optional<problem::ContentDigest> expected){
 if(!valid_limits(limits))return error(ArtifactErrorCode::invalid_input,"attachment.limits","All attachment limits must be positive");
 if(bytes.size()>limits.max_bytes)return error(ArtifactErrorCode::limit,"attachment.bytes","Attachment exceeds byte limit");
 auto owned=problem::snapshot_content(bytes,expected);if(!std::holds_alternative<problem::ResolvedContent>(owned))return error(ArtifactErrorCode::identity,"attachment.digest","Attachment digest mismatch");
 try {const auto content=std::get<problem::ResolvedContent>(std::move(owned));std::string source;source.reserve(content.bytes().size());for(auto b:content.bytes())source.push_back(static_cast<char>(std::to_integer<unsigned char>(b)));
  const auto j=Json::parse(source);if(j.at("schema")!="csl.h-relation-attachment/1")return error(ArtifactErrorCode::unsupported,"attachment.schema","Unknown H-relation attachment schema");
  const auto dim=u64(j.at("dimension"));if(dim>limits.max_dimension)return error(ArtifactErrorCode::limit,"attachment.dimension","Dimension limit exceeded");
  if(text(j.at("representation"))!="csl.polyhedron.h"||text(j.at("convex"))!="yes"||text(j.at("polyhedral"))!="yes"||text(j.at("bounded"))!="unknown")throw std::runtime_error("H metadata does not match SetData factory contract");const auto id=text(j.at("id"));std::uint64_t txt=0;if(auto e=text_limit(txt,id,limits))return *e;
  const auto labels=j.at("labels");if(!labels.is_array()||(!labels.empty()&&labels.size()!=dim))throw std::runtime_error("Coordinate label count mismatch");std::vector<std::string> names;names.reserve(labels.size());for(const auto& x:labels){auto s=text(x);if(auto e=text_limit(txt,s,limits))return *e;names.push_back(std::move(s));}
  const auto ir=u64(j.at("inequalities").at("rows")),er=u64(j.at("equalities").at("rows"));if(ir>limits.max_rows||er>limits.max_rows-ir)return error(ArtifactErrorCode::limit,"attachment.rows","Row limit exceeded");
  auto av=coefficients(j.at("inequalities"),ir,dim),ev=coefficients(j.at("equalities"),er,dim);const auto& ub=j.at("upper_bounds");const auto& fv=j.at("equality_values");if(!ub.is_array()||ub.size()!=ir||!fv.is_array()||fv.size()!=er)throw std::runtime_error("Bound count mismatch");
  std::vector<double> b,f;for(const auto& x:ub)b.push_back(number(x));for(const auto& x:fv)f.push_back(number(x));
  auto am=numeric::snapshot(Matrix{static_cast<std::size_t>(ir),static_cast<std::size_t>(dim),std::move(av)});auto bm=numeric::snapshot_vector(b);auto em=numeric::snapshot(Matrix{static_cast<std::size_t>(er),static_cast<std::size_t>(dim),std::move(ev)});auto fm=numeric::snapshot_vector(f);
  if(!std::holds_alternative<numeric::MatrixView>(am)||!std::holds_alternative<numeric::VectorView>(bm)||!std::holds_alternative<numeric::MatrixView>(em)||!std::holds_alternative<numeric::VectorView>(fm))throw std::runtime_error("Nonfinite or invalid H data");
  std::optional<sets::AffineDimensionClaim> claim;const auto& a=j.at("affine_dimension");if(!a.is_null()){if(a.at("origin")!="supplied")throw std::runtime_error("Unsupported affine-dimension origin");const auto& v=a.at("value");sets::AffineDimension avalue;if(v.at("kind")=="empty")avalue=sets::EmptyAffineDimension{};else if(v.at("kind")=="dimension"){auto n=u64(v.at("value"));if(n>dim)throw std::runtime_error("Affine dimension exceeds ambient dimension");avalue=sets::DimensionValue{static_cast<std::size_t>(n)};}else throw std::runtime_error("Unknown affine dimension kind");auto s=support(a.at("support"));std::visit([&](const auto& x){using T=std::decay_t<decltype(x)>;if constexpr(std::is_same_v<T,SymbolicArgument>){if(auto e=text_limit(txt,x.reference,limits))throw std::length_error(e->message);if(auto e=text_limit(txt,x.assumptions,limits))throw std::length_error(e->message);}else if constexpr(std::is_same_v<T,CertificateReference>){if(auto e=text_limit(txt,x.artifact,limits))throw std::length_error(e->message);if(auto e=text_limit(txt,x.verifier,limits))throw std::length_error(e->message);}else if constexpr(std::is_same_v<T,NumericalCheck>){if(auto e=text_limit(txt,x.verifier.value,limits))throw std::length_error(e->message);}},s);claim=sets::AffineDimensionClaim{std::move(avalue),std::move(s)};}
  auto made=sets::make_h({SetId{id},static_cast<std::size_t>(dim),std::move(names)},{std::get<numeric::MatrixView>(am),std::get<numeric::VectorView>(bm),std::get<numeric::MatrixView>(em),std::get<numeric::VectorView>(fm)},claim);
  if(auto* set=std::get_if<sets::SetData>(&made))return *set;return error(ArtifactErrorCode::invalid_input,"attachment.set","Decoded H set violates SetData contracts");
 }catch(const std::exception& e){return error(ArtifactErrorCode::invalid_input,"attachment.decode",e.what());}
}
} // namespace csl::artifacts
