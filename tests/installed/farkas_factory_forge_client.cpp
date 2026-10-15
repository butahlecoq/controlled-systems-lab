#include <csl/optimization/linear_infeasibility_certificate.hpp>

namespace csl::optimization::detail {
class FarkasEvidenceFactory {
public:
    static csl::ExactFarkasEvidence forge(csl::LinearInfeasibilityCertificate certificate) {
        return csl::ExactFarkasEvidence(std::move(certificate));
    }
};
}

int main() {
    return 0;
}
