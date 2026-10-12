#include "scenario_json.hpp"
#include <array>
#include <fstream>
namespace csl::input {
LoadResult load_scenario_file(const std::filesystem::path& path,const LoadOptions& options) {
    try {
        detail::validate_options(options);detail::poll(options);
        std::ifstream stream(path,std::ios::binary);
        if(!stream) {
            std::error_code ec;const bool exists=std::filesystem::exists(path,ec);
            return InputFailure{InputCategory::io,"",!ec && !exists?"not_found":"unreadable","readable local scenario file"};
        }
        std::vector<std::byte> bytes;std::array<char,4096> chunk{};
        while(stream) {
            detail::poll(options);
            const auto remaining=options.limits.input_bytes-bytes.size()+1;
            stream.read(chunk.data(),static_cast<std::streamsize>(std::min(remaining,chunk.size())));
            const auto count=static_cast<std::size_t>(stream.gcount());
            if(count>options.limits.input_bytes-bytes.size()) return InputFailure{InputCategory::limit,"","input byte quota exceeded","bounded scenario bytes"};
            for(std::size_t i=0;i<count;++i) bytes.push_back(static_cast<std::byte>(static_cast<unsigned char>(chunk[i])));
        }
        if(!stream.eof() || stream.bad()) return InputFailure{InputCategory::io,"","read_failed","complete readable local scenario file"};
        return detail::load_bytes(bytes,options,path);
    } catch(const InputFailure& f) {return f;}
      catch(const OperationStopped& s) {return s;}
}
} // namespace csl::input
