#include <csl/artifacts/comparison_manifest.hpp>
#include <nlohmann/json.hpp>

#include <fstream>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Json = nlohmann::json;
using namespace csl;

std::vector<std::byte> bytes(std::string_view text) {
    std::vector<std::byte> result;
    result.reserve(text.size());
    for (const unsigned char value : text) result.push_back(static_cast<std::byte>(value));
    return result;
}

problem::ContentDigest parse_digest(const std::string& text) {
    if (text.size() != 64) throw std::invalid_argument("digest must have 64 lowercase hex characters");
    const auto nibble = [](char value) -> unsigned char {
        if (value >= '0' && value <= '9') return static_cast<unsigned char>(value - '0');
        if (value >= 'a' && value <= 'f') return static_cast<unsigned char>(value - 'a' + 10);
        throw std::invalid_argument("digest must use lowercase hexadecimal");
    };
    problem::ContentDigest digest{};
    for (std::size_t index = 0; index < digest.bytes.size(); ++index)
        digest.bytes[index] = static_cast<std::byte>((nibble(text[index * 2]) << 4) |
            nibble(text[index * 2 + 1]));
    return digest;
}

artifacts::AttemptStatus parse_status(const std::string& value) {
    using artifacts::AttemptStatus;
    if (value == "completed") return AttemptStatus::completed;
    if (value == "failed") return AttemptStatus::failed;
    if (value == "refused") return AttemptStatus::refused;
    if (value == "unsupported") return AttemptStatus::unsupported;
    if (value == "timed_out") return AttemptStatus::timed_out;
    if (value == "cancelled") return AttemptStatus::cancelled;
    if (value == "resource_limited") return AttemptStatus::resource_limited;
    if (value == "incomplete") return AttemptStatus::incomplete;
    throw std::invalid_argument("unknown attempt status");
}

std::string text(const problem::ResolvedContent& content) {
    std::string result;
    result.reserve(content.bytes().size());
    for (const auto value : content.bytes()) result.push_back(static_cast<char>(std::to_integer<unsigned char>(value)));
    return result;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::invalid_argument("usage: csl_exp06_pack_comparison REQUEST.json");
        std::ifstream input(argv[1], std::ios::binary);
        if (!input) throw std::runtime_error("could not open comparison request");
        const auto request = Json::parse(input);
        if (request.at("schema") != "csl.exp06-pack-request/1")
            throw std::invalid_argument("unknown pack request schema");
        const auto manifest_text = request.at("manifest").get<std::string>();
        const auto manifest_bytes = bytes(manifest_text);
        const auto manifest_result = problem::snapshot_content(std::span<const std::byte>(manifest_bytes));
        if (const auto* failure = std::get_if<Diagnostic>(&manifest_result))
            throw std::runtime_error("manifest rejected: " + failure->explanation);
        const auto manifest = std::get<problem::ResolvedContent>(manifest_result);
        const auto manifest_hash = problem::hex(manifest.digest());
        const auto problem_id = std::string("csl.problem.v1.sha256:") + manifest_hash;
        const auto request_digest = parse_digest(request.at("request_digest").get<std::string>());
        const auto& methods = request.at("methods");
        if (!methods.is_array() || methods.size() < 2 || methods.size() > 8)
            throw std::invalid_argument("paired methods are required");
        const auto repetitions = methods.at(0).at("attempts").size();
        if (repetitions == 0 || repetitions > 100)
            throw std::invalid_argument("attempt count is invalid");
        Json arms = Json::array();
        std::vector<artifacts::ComparisonAttempt> attempts;
        for (std::size_t arm = 0; arm < methods.size(); ++arm) {
            const auto& method = methods.at(arm);
            const auto method_id = method.at("id").get<std::string>();
            const auto configuration_id = method.at("configuration_id").get<std::string>();
            arms.push_back({{"configuration_id", configuration_id}, {"strategy", method_id},
                {"instrumentation", "disabled"}});
            if (method.at("attempts").size() != repetitions)
                throw std::invalid_argument("methods have different repetition counts");
            for (std::size_t repetition = 0; repetition < repetitions; ++repetition) {
                const auto& attempt = method.at("attempts").at(repetition);
                artifacts::ExternalMethodRunInput run_input;
                run_input.run = {attempt.at("run_id").get<std::string>()};
                run_input.problem = {problem_id};
                run_input.configuration = {configuration_id};
                run_input.request_digest = request_digest;
                run_input.input_manifest_schema = "csl.geometry-hull-input/1";
                run_input.input_manifest = manifest_bytes;
                run_input.method_id = method_id;
                run_input.method_version = method.at("version").get<std::string>();
                for (const auto& source : method.at("sources"))
                    run_input.sources.push_back({source.at("path").get<std::string>(),
                        source.at("sha256").get<std::string>()});
                if (!method.at("deviations_sha256").is_null())
                    run_input.deviations_sha256 = method.at("deviations_sha256").get<std::string>();
                const auto& runtime = attempt.at("runtime");
                run_input.runtime = {runtime.at("language").get<std::string>(),
                    runtime.at("implementation").get<std::string>(), runtime.at("version").get<std::string>(),
                    runtime.at("executable_sha256").get<std::string>(), runtime.at("os").get<std::string>(),
                    runtime.at("architecture").get<std::string>(), runtime.at("compiler").get<std::string>(),
                    runtime.at("compiler_version").get<std::string>(), runtime.at("build_type").get<std::string>()};
                run_input.status = parse_status(attempt.at("status").get<std::string>());
                run_input.result_payload = attempt.at("result").dump();
                auto run = artifacts::encode_external_method_run(run_input);
                if (const auto* failure = std::get_if<artifacts::ArtifactError>(&run))
                    throw std::runtime_error("method run rejected at " + failure->path + ": " + failure->message);
                auto recorded = std::get<artifacts::RecordedExternalMethodRunArtifact>(std::move(run));
                const auto measurement = attempt.at("measurement");
                const auto measurement_payload = measurement.dump();
                attempts.push_back({static_cast<std::uint32_t>(arm), static_cast<std::uint32_t>(repetition),
                    recorded.status(), {recorded.run_id(), recorded.content().digest()},
                    std::move(recorded), measurement_payload});
            }
        }
        const auto spec = Json{{"schema", "csl.comparison-spec/2"}, {"problem_id", problem_id},
            {"request_digest", problem::hex(request_digest)}, {"repetitions", repetitions},
            {"input_manifest_hash", manifest_hash}, {"input_manifest_source", "csl.geometry-hull-input/1"},
            {"arms", std::move(arms)}};
        const auto spec_text = spec.dump();
        const auto spec_bytes = bytes(spec_text);
        const auto spec_content_result = problem::snapshot_content(std::span<const std::byte>(spec_bytes));
        if (const auto* failure = std::get_if<Diagnostic>(&spec_content_result))
            throw std::runtime_error("comparison spec rejected: " + failure->explanation);
        const auto spec_content = std::get<problem::ResolvedContent>(spec_content_result);
        auto comparison = artifacts::encode_recorded_comparison(spec_content, attempts);
        if (const auto* failure = std::get_if<artifacts::ArtifactError>(&comparison))
            throw std::runtime_error("comparison rejected at " + failure->path + ": " + failure->message);
        const auto& encoded = std::get<artifacts::RecordedComparisonArtifact>(comparison).content();
        const auto wire = text(encoded);
        const auto decoded = artifacts::decode_recorded_comparison(wire);
        if (const auto* failure = std::get_if<artifacts::ArtifactError>(&decoded))
            throw std::runtime_error("comparison round trip rejected at " + failure->path + ": " + failure->message);
        if (std::get<artifacts::RecordedComparisonArtifact>(decoded).content().digest() != encoded.digest())
            throw std::runtime_error("comparison round-trip digest changed");
        std::cout << wire << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
