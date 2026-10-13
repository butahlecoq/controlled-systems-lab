#include <csl/synthesis/terminal_minimizers.hpp>

#include <iostream>

int main() {
    const csl::synthesis::TerminalMinimizers result;
    if (result.outcome != csl::MathematicalOutcome::undetermined || result.relation || result.optimum) {
        return 1;
    }
    std::cout << "Installed terminal-minimizers client: public outcome contract is available\n";
    return 0;
}
