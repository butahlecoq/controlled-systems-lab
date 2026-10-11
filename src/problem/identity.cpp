#include "resolved_storage.hpp"
#include <bit>
#include <limits>
#include <stdexcept>
#include <climits>

namespace {
// FIPS 180-4 SHA-256, private to structural identity and owned content.
class Sha256 {
    std::array<std::uint32_t,8> state_{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
        0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::array<std::byte,64> block_{};
    std::size_t used_{};
    std::uint64_t length_{};
    void compress() {
        constexpr std::uint32_t k[]={
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        std::array<std::uint32_t,64> w{};
        for(std::size_t i=0;i<16;++i)
            for(std::size_t j=0;j<4;++j) w[i]=(w[i]<<8)|std::to_integer<std::uint32_t>(block_[4*i+j]);
        for(std::size_t i=16;i<64;++i) {
            const auto a=w[i-15],b=w[i-2];
            w[i]=w[i-16]+(std::rotr(a,7)^std::rotr(a,18)^(a>>3))+w[i-7]+(std::rotr(b,17)^std::rotr(b,19)^(b>>10));
        }
        auto [a,b,c,d,e,f,g,h]=state_;
        for(std::size_t i=0;i<64;++i) {
            const auto t1=h+(std::rotr(e,6)^std::rotr(e,11)^std::rotr(e,25))+((e&f)^(~e&g))+k[i]+w[i];
            const auto t2=(std::rotr(a,2)^std::rotr(a,13)^std::rotr(a,22))+((a&b)^(a&c)^(b&c));
            h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        const std::array tail{a,b,c,d,e,f,g,h};
        for(std::size_t i=0;i<8;++i) state_[i]+=tail[i];
    }
    void byte(std::byte value) {
        block_[used_++]=value;
        if(used_==64) {compress();used_=0;}
    }
public:
    static constexpr auto maximum_bytes=std::numeric_limits<std::uint64_t>::max()/8;
    void append(std::span<const std::byte> bytes) {
        if(bytes.size()>maximum_bytes-length_) throw std::length_error("SHA-256 byte count exceeds its bit-length encoding");
        length_+=bytes.size();
        for(auto value:bytes) byte(value);
    }
    csl::problem::ContentDigest finish() {
        const auto bits=length_*8;
        byte(std::byte{0x80});
        while(used_!=56) byte(std::byte{0});
        for(int shift=56;shift>=0;shift-=8) byte(static_cast<std::byte>((bits>>shift)&255));
        csl::problem::ContentDigest result{};
        for(std::size_t i=0;i<8;++i)
            for(std::size_t j=0;j<4;++j) result.bytes[4*i+j]=static_cast<std::byte>((state_[i]>>(24-8*j))&255);
        return result;
    }
};
}
namespace csl::problem {
ResolvedContent::ResolvedContent(std::shared_ptr<const detail::ContentStorage> storage):storage_(std::move(storage)) {}
ContentDigest ResolvedContent::digest() const noexcept {return storage_->digest;}
std::span<const std::byte> ResolvedContent::bytes() const noexcept {return storage_->bytes;}
std::string hex(ContentDigest digest) {
    constexpr char digits[]="0123456789abcdef";
    std::string result; result.reserve(64);
    for(auto byte:digest.bytes) {const auto value=std::to_integer<unsigned>(byte);result.push_back(digits[value>>4]);result.push_back(digits[value&15]);}
    return result;
}
Result<ResolvedContent> snapshot_content(std::span<const std::byte> bytes,std::optional<ContentDigest> expected) {
    if(bytes.size()>Sha256::maximum_bytes)
        return Diagnostic{DiagnosticCode::invalid_input,"problem.content.length","content exceeds SHA-256 length encoding"};
    std::vector<std::byte> owned(bytes.begin(),bytes.end());
    Sha256 hash;hash.append(owned);const auto digest=hash.finish();
    if(expected && *expected!=digest)
        return Diagnostic{DiagnosticCode::invalid_input,"problem.content.digest","expected digest does not match the supplied bytes"};
    return detail::ResolvedAccess::content(std::make_shared<const detail::ContentStorage>(std::move(owned),digest));
}
}
namespace csl::problem::detail {
namespace {
static_assert(CHAR_BIT==8 && sizeof(double)==8 && std::numeric_limits<double>::is_iec559 &&
    std::numeric_limits<double>::digits==53 && std::numeric_limits<double>::max_exponent==1024);
static_assert(sizeof(std::size_t)<=sizeof(std::uint64_t));
template<class... F> struct Visitor : F... {using F::operator()...;};
class Writer {
    Sha256 hash_;
    std::vector<std::byte>* output_;
    std::uint64_t count_{};
public:
    explicit Writer(std::vector<std::byte>* output=nullptr):output_(output) {}
    void ensure(std::uint64_t size) const {
        if(size>Sha256::maximum_bytes-count_) throw std::length_error("canonical problem exceeds SHA-256 byte count");
    }
    void raw(std::span<const std::byte> bytes) {
        ensure(bytes.size());count_+=bytes.size();hash_.append(bytes);
        if(output_) output_->insert(output_->end(),bytes.begin(),bytes.end());
    }
    void integer(std::uint64_t value,std::size_t width) {
        std::array<std::byte,8> bytes{};
        for(std::size_t i=0;i<width;++i) bytes[i]=static_cast<std::byte>((value>>(8*(width-1-i)))&255);
        raw(std::span(bytes).first(width));
    }
    void tag(std::uint8_t value) {integer(value,1);}
    void count(std::size_t value) {integer(value,8);}
    void number(double value) {integer(std::bit_cast<std::uint64_t>(value==0?0.0:value),8);}
    void string(std::string_view text) {count(text.size());raw(std::as_bytes(std::span(text.data(),text.size())));}
    template<class Range,class Emit> void array(const Range& range,Emit emit) {
        count(range.size());for(const auto& item:range) emit(item);
    }
    void vector(std::span<const double> values) {
        if(values.size()>Sha256::maximum_bytes/8) throw std::length_error("canonical vector width overflow");
        ensure(values.size()*8);count(values.size());for(double value:values) number(value);
    }
    void vector(const numeric::VectorView& values) {vector(values.values());}
    template<class Read> void matrix(std::size_t rows,std::size_t cols,Read read) {
        if(cols && rows>Sha256::maximum_bytes/8/cols) throw std::length_error("canonical matrix width overflow");
        ensure(static_cast<std::uint64_t>(rows)*cols*8);count(rows);count(cols);
        if(cols==0) return; // Zero-width native V records can have arbitrarily many empty rows.
        for(std::size_t row=0;row<rows;++row) for(std::size_t col=0;col<cols;++col) number(read(row,col));
    }
    void matrix(const Matrix& value) {
        matrix(value.rows,value.cols,[&](auto r,auto c){return value.values[r*value.cols+c];});
    }
    void matrix(const numeric::MatrixView& value) {
        matrix(value.rows(),value.cols(),[&](auto r,auto c){return value(r,c);});
    }
    void set(const AdmissibleSet& value) {
        std::visit(Visitor{
            [&](const EmptySet& s){tag(0);count(s.dimension);},
            [&](const UniversalSet& s){tag(1);count(s.dimension);},
            [&](const Singleton& s){tag(2);vector(s.point);},
            [&](const SetHandle& s){
                // Component publication already verified the envelope and immutable native owner.
                const auto native=std::get<sets::SetData>(sets::from_handle(s));
                tag(3);count(native.metadata()->set.dimension);
                std::visit(Visitor{
                    [&](const sets::HRepresentation& r){tag(0);matrix(r.inequalities);vector(r.upper_bounds);matrix(r.equalities);vector(r.equality_values);},
                    [&](const sets::VRepresentation& r){tag(1);matrix(r.vertices);matrix(r.rays);},
                    [&](const sets::EmptyRepresentation&){tag(2);},
                    [&](const sets::UniversalRepresentation&){tag(3);},
                    [&](const sets::SingletonRepresentation& r){tag(4);vector(r.point);}
                },native.representation());
            }
        },value);
    }
    void sets(std::span<const AdmissibleSet> values) {array(values,[&](const auto& s){set(s);});}
    void finite(const FiniteDomain& value) {count(value.dimension);array(value.catalogue,[&](const auto& v){vector(v);});}
    void stage(const LinearStage& s) {matrix(s.A);matrix(s.B);matrix(s.E);vector(s.offset);}
    void observation(const ObservationStage& s) {matrix(s.state_map);matrix(s.control_map);matrix(s.external_map);matrix(s.error_map);vector(s.offset);}
    void event(const ObservationPoint& value) {count(value.stage.value);tag(value.timing==ObservationTiming::before_decision?0:1);}
    void quantifier(SetQuantifier value) {tag(value==SetQuantifier::existential?1:2);}
    void interval(const Interval& value) {
        tag(value.lower.has_value());if(value.lower) number(*value.lower);
        tag(value.upper.has_value());if(value.upper) number(*value.upper);
    }
    ContentDigest finish() {return hash_.finish();}
};
void write_problem(Writer& w,const Problem& p,std::span<const ContentBinding> content) {
    // Includes the terminator; the format's magic is twelve bytes (CSL-PROBLEM plus NUL).
    constexpr std::array<std::byte,12> prefix{std::byte{'C'},std::byte{'S'},std::byte{'L'},std::byte{'-'},std::byte{'P'},std::byte{'R'},std::byte{'O'},std::byte{'B'},std::byte{'L'},std::byte{'E'},std::byte{'M'},std::byte{0}};
    w.raw(prefix);w.integer(1,4);w.tag(0);
    const auto& dynamics=p.model->dynamics;
    w.count(dynamics.dimensions.state);w.count(dynamics.dimensions.control);w.count(dynamics.dimensions.external);w.vector(p.times);
    std::visit(Visitor{
        [&](const LinearStage& stage){w.tag(0);w.stage(stage);},
        [&](const std::vector<LinearStage>& stages){w.tag(1);w.array(stages,[&](const auto& s){w.stage(s);});}
    },dynamics.stages);
    w.array(p.model->observations,[&](const Observation& o){
        std::visit(Visitor{
            [&](const ObservationStage& stage){w.tag(0);w.observation(stage);},
            [&](const std::vector<ObservationStage>& stages){w.tag(1);w.array(stages,[&](const auto& s){w.observation(s);});}
        },o.coefficients);
        w.array(o.schedule,[&](const ObservationSample& s){w.count(s.state_stage.value);w.event(s.measured_at);w.event(s.available_at);w.tag(s.input_stage.has_value());if(s.input_stage)w.count(s.input_stage->value);});
    });
    std::visit(Visitor{
        [&](const KnownInitial& initial){w.tag(0);w.vector(initial.point);},
        [&](const InitialSet& initial){w.tag(1);w.quantifier(initial.quantifier);w.set(initial.set);}
    },p.initial);
    std::visit(Visitor{
        [&](const ContinuousDomain& d){w.tag(0);w.sets(d.stages);},
        [&](const FiniteDomain& d){w.tag(1);w.finite(d);},
        [&](const MixedDomain& d){w.tag(2);w.sets(d.continuous.stages);w.finite(d.discrete);}
    },p.controls);
    w.sets(p.states);w.tag(p.temporal.has_value());
    if(p.temporal) {
        const auto& csr=p.temporal->joint_map;
        w.count(csr.rows);w.count(csr.cols);
        w.array(csr.row_offsets,[&](auto n){w.count(n);});w.array(csr.column_indices,[&](auto n){w.count(n);});w.vector(csr.values);
        w.array(p.temporal->bounds,[&](const auto& b){w.interval(b);});
    }
    if(!p.external) w.tag(0);
    else std::visit(Visitor{
        [&](const KnownExternalSequence& e){w.tag(1);w.array(e.stages,[&](const auto& v){w.vector(v);});},
        [&](const ExogenousExternalInput& e){w.tag(2);w.quantifier(e.quantifier);w.sets(e.stages);},
        [&](const AdversarialExternalInput& e){w.tag(3);w.quantifier(e.quantifier);w.sets(e.stages);w.string(e.semantics_reference);}
    },*p.external);
    w.tag(p.information==InformationPattern::nominal_open_loop?0:1);
    std::visit(Visitor{
        [&](const LinearTerminal& o){w.tag(0);w.vector(o.coefficients);w.number(o.offset);},
        [&](const QuadraticTerminal& o){w.tag(1);w.matrix(o.Q);w.vector(o.linear);w.number(o.offset);},
        [&](const ResidualNormTerminal& o){w.tag(2);w.matrix(o.map);w.vector(o.target);}
    },p.objective);
    w.tag(0);
    w.array(content,[&](const ContentBinding& binding){w.string(binding.key);w.count(binding.content.bytes().size());w.raw(binding.content.digest().bytes);});
}
}
std::vector<std::byte> encode_problem(const Problem& p,std::span<const ContentBinding> content) {
    std::vector<std::byte> result;Writer writer(&result);write_problem(writer,p,content);return result;
}
Result<ContentDigest> identity_digest(const Problem& p,std::span<const ContentBinding> content) {
    try {Writer writer;write_problem(writer,p,content);return writer.finish();}
    catch(const std::length_error& failure) {return Diagnostic{DiagnosticCode::invalid_input,"problem.identity.length",failure.what()};}
}
}
