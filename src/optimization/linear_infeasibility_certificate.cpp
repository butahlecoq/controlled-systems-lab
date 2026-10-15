#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <vector>

namespace csl::optimization::detail {
class FarkasEvidenceFactory {
public:
    static ExactFarkasEvidence create(LinearInfeasibilityCertificate certificate) {
        return ExactFarkasEvidence(std::move(certificate));
    }
};
}

namespace csl::optimization {
namespace {
Diagnostics failure(DiagnosticCode code,std::string field,std::string explanation) {
    return {{code,std::move(field),std::move(explanation)}};
}
Diagnostics invalid(std::string field,std::string explanation) {
    return failure(DiagnosticCode::invalid_claim,std::move(field),std::move(explanation));
}

// A nonnegative arbitrary-precision integer in base 2^32. Farkas terms are
// at most 106 bits; dynamic words preserve carries for any finite term count.
class Magnitude {
    std::vector<std::uint32_t> words_;
public:
    void add_word(std::size_t index,std::uint32_t value) {
        std::uint64_t carry=value;
        while(carry) {
            if(index>=words_.size()) words_.resize(index+1,0);
            const std::uint64_t sum=std::uint64_t(words_[index])+carry;
            words_[index]=static_cast<std::uint32_t>(sum);
            carry=sum>>32;
            ++index;
        }
    }
    int compare(const Magnitude& other) const noexcept {
        auto left=words_.size(),right=other.words_.size();
        while(left&&words_[left-1]==0)--left;
        while(right&&other.words_[right-1]==0)--right;
        if(left!=right)return left<right?-1:1;
        while(left) {
            --left;
            if(words_[left]!=other.words_[left])return words_[left]<other.words_[left]?-1:1;
        }
        return 0;
    }
};

struct Binary64Parts { bool negative;std::uint64_t significand;int exponent; };
Binary64Parts parts(double value) noexcept {
    const auto bits=std::bit_cast<std::uint64_t>(value);
    const auto exponent=static_cast<unsigned>((bits>>52)&0x7ffu);
    const auto fraction=bits&((std::uint64_t{1}<<52)-1);
    if(exponent==0)return {(bits>>63)!=0,fraction,-1074};
    return {(bits>>63)!=0,(std::uint64_t{1}<<52)|fraction,
        static_cast<int>(exponent)-1023-52};
}

std::array<std::uint32_t,4> multiply_significands(std::uint64_t left,std::uint64_t right) noexcept {
    const std::array<std::uint32_t,2> a{static_cast<std::uint32_t>(left),static_cast<std::uint32_t>(left>>32)};
    const std::array<std::uint32_t,2> b{static_cast<std::uint32_t>(right),static_cast<std::uint32_t>(right>>32)};
    std::array<std::uint32_t,4> product{};
    for(std::size_t i=0;i<2;++i) {
        std::uint64_t carry=0;
        for(std::size_t j=0;j<2;++j) {
            const auto index=i+j;
            const std::uint64_t value=std::uint64_t(a[i])*b[j]+product[index]+carry;
            product[index]=static_cast<std::uint32_t>(value);
            carry=value>>32;
        }
        auto index=i+2;
        while(carry&&index<product.size()) {
            const std::uint64_t value=std::uint64_t(product[index])+carry;
            product[index]=static_cast<std::uint32_t>(value);
            carry=value>>32;
            ++index;
        }
    }
    return product;
}

// All products of finite binary64 values are integer multiples of 2^-2148.
// Separate positive and negative magnitudes make summation exactly order-free.
class ExactDyadicSum {
    static constexpr int common_exponent=-2148;
    Magnitude positive_,negative_;
public:
    void add_product(double left,double right,bool negate=false) {
        const auto a=parts(left),b=parts(right);
        if(!a.significand||!b.significand)return;
        const auto product=multiply_significands(a.significand,b.significand);
        const int exponent=a.exponent+b.exponent;
        const auto shift=static_cast<std::size_t>(exponent-common_exponent);
        const auto word=shift/32;
        const auto bit=static_cast<unsigned>(shift%32);
        auto& magnitude=(a.negative!=b.negative)!=negate?negative_:positive_;
        for(std::size_t i=0;i<product.size();++i) {
            if(product[i]==0)continue;
            const std::uint64_t shifted=std::uint64_t(product[i])<<bit;
            magnitude.add_word(word+i,static_cast<std::uint32_t>(shifted));
            magnitude.add_word(word+i+1,static_cast<std::uint32_t>(shifted>>32));
        }
    }
    bool zero() const noexcept { return positive_.compare(negative_)==0; }
    bool positive() const noexcept { return positive_.compare(negative_)>0; }
};

bool finite_nonnegative(std::span<const double> values) {
    for(double value:values)if(!std::isfinite(value)||value<0)return false;
    return true;
}
}

std::variant<ExactFarkasEvidence,Diagnostics> verify_linear_infeasibility_certificate(
    const LinearProgram& program,const LinearInfeasibilityCertificate& certificate) {
    if(certificate.subject!=program.identity())
        return failure(DiagnosticCode::evidence_mismatch,"lp.infeasibility.subject",
            "Certificate belongs to a different immutable linear program.");
    const auto row_count=program.rows().size(),variable_count=program.variables().size();
    if(certificate.row_lower.size()!=row_count||certificate.row_upper.size()!=row_count||
       certificate.variable_lower.size()!=variable_count||certificate.variable_upper.size()!=variable_count)
        return invalid("lp.infeasibility.shape","Farkas multiplier dimensions must match every row and variable endpoint.");
    if(!finite_nonnegative(certificate.row_lower)||!finite_nonnegative(certificate.row_upper)||
       !finite_nonnegative(certificate.variable_lower)||!finite_nonnegative(certificate.variable_upper))
        return invalid("lp.infeasibility.signs","Farkas multipliers must be finite and nonnegative.");
    for(std::size_t i=0;i<row_count;++i)
        if((!program.rows()[i].lower&&certificate.row_lower[i]!=0)||
           (!program.rows()[i].upper&&certificate.row_upper[i]!=0))
            return invalid("lp.infeasibility.absent_row_bound","An absent row endpoint must have zero multiplier.");
    for(std::size_t j=0;j<variable_count;++j)
        if((!program.variables()[j].lower&&certificate.variable_lower[j]!=0)||
           (!program.variables()[j].upper&&certificate.variable_upper[j]!=0))
            return invalid("lp.infeasibility.absent_variable_bound","An absent variable endpoint must have zero multiplier.");

    const auto csr=std::get<numeric::CsrInput>(program.constraints().descriptor());
    std::vector<ExactDyadicSum> stationarity(variable_count);
    for(std::size_t i=0;i<row_count;++i)
        for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {
            const auto j=csr.column_indices[k];
            stationarity[j].add_product(csr.values[k],certificate.row_lower[i],true);
            stationarity[j].add_product(csr.values[k],certificate.row_upper[i]);
        }
    for(std::size_t j=0;j<variable_count;++j) {
        stationarity[j].add_product(1.0,certificate.variable_lower[j],true);
        stationarity[j].add_product(1.0,certificate.variable_upper[j]);
        if(!stationarity[j].zero())
            return invalid("lp.infeasibility.stationarity","Exact dyadic Farkas stationarity is nonzero.");
    }

    ExactDyadicSum contradiction;
    for(std::size_t i=0;i<row_count;++i) {
        if(program.rows()[i].lower)
            contradiction.add_product(certificate.row_lower[i],*program.rows()[i].lower);
        if(program.rows()[i].upper)
            contradiction.add_product(certificate.row_upper[i],*program.rows()[i].upper,true);
    }
    for(std::size_t j=0;j<variable_count;++j) {
        if(program.variables()[j].lower)
            contradiction.add_product(certificate.variable_lower[j],*program.variables()[j].lower);
        if(program.variables()[j].upper)
            contradiction.add_product(certificate.variable_upper[j],*program.variables()[j].upper,true);
    }
    if(!contradiction.positive())
        return invalid("lp.infeasibility.contradiction","Exact dyadic contradiction constant must be strictly positive.");
    return detail::FarkasEvidenceFactory::create(certificate);
}
} // namespace csl::optimization
