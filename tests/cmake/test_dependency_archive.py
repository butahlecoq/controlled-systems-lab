"""Exercise verified archive reuse through real FetchContent configurations."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "cmake/DependencyArchive.cmake"


class DependencyArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.source = self.area / "source"
        self.source.mkdir()
        self.archive = self.area / "remote.tar.gz"
        self.cache = self.area / "cache"

    def make_archive(self, value):
        with tarfile.open(self.archive, "w:gz") as stream:
            info = tarfile.TarInfo("package/value.txt")
            data = value.encode()
            info.size = len(data)
            stream.addfile(info, io.BytesIO(data))
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def configure(self, name, digest, cache=True):
        template = '''cmake_minimum_required(VERSION 3.31)
project(ArchiveFixture NONE)
include("@HELPER@")
csl_dependency_archive_url(archive_url fixture "@URL@" "@HASH@")
include(FetchContent)
FetchContent_Declare(fixture URL "${archive_url}" URL_HASH SHA256=@HASH@
  SOURCE_SUBDIR no-build)
FetchContent_MakeAvailable(fixture)
file(READ "${fixture_SOURCE_DIR}/value.txt" value)
file(WRITE "${CMAKE_BINARY_DIR}/answer.txt" "${value}")
'''
        # FetchContent's Windows local-file handling expects a plain path;
        # file(DOWNLOAD), exercised by the cache, expects the file URI.
        remote = self.archive.as_uri() if cache else self.archive.as_posix()
        cmake = template.replace("@HELPER@", HELPER.as_posix()).replace(
            "@URL@", remote).replace("@HASH@", digest)
        (self.source / "CMakeLists.txt").write_text(cmake, encoding="utf-8")
        build = self.area / name
        command = [sys.executable, "-m", "cmake", "-S", str(self.source), "-B", str(build)]
        if cache:
            command.append("-DCSL_DEPENDENCY_ARCHIVE_CACHE=" + self.cache.as_posix())
        else:
            command.append("-DCSL_DEPENDENCY_ARCHIVE_CACHE=")
        result = subprocess.run(command, text=True, capture_output=True,
                                env={**os.environ, "CSL_DEPENDENCY_ARCHIVE_CACHE":
                                     str(self.area / "inherited-cache")})
        return result, build

    def require_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_miss_then_hit_in_fresh_extraction_without_original_download(self):
        digest = self.make_archive("literal dependency contents")
        first, build = self.configure("first", digest)
        self.require_success(first)
        self.assertEqual((build / "answer.txt").read_text(), "literal dependency contents")
        self.archive.unlink()
        second, fresh = self.configure("second", digest)
        self.require_success(second)
        self.assertEqual((fresh / "answer.txt").read_text(), "literal dependency contents")
        self.assertIn("CSL archive cache hit: fixture", second.stdout)

    def test_changed_pin_populates_distinct_verified_archive(self):
        old = self.make_archive("old pin")
        first, _ = self.configure("old", old)
        self.require_success(first)
        new = self.make_archive("new pin")
        second, build = self.configure("new", new)
        self.require_success(second)
        self.assertEqual((build / "answer.txt").read_text(), "new pin")
        self.archive.unlink()
        old_again, build = self.configure("old-again", old)
        self.require_success(old_again)
        self.assertEqual((build / "answer.txt").read_text(), "old pin")

    def test_corrupt_cached_archive_is_replaced_only_from_verified_source(self):
        digest = self.make_archive("verified")
        first, _ = self.configure("first", digest)
        self.require_success(first)
        archives = list(self.cache.glob("*.tar.gz"))
        self.assertEqual(len(archives), 1)
        archives[0].write_bytes(b"untrusted cached bytes")
        second, build = self.configure("second", digest)
        self.require_success(second)
        self.assertEqual((build / "answer.txt").read_text(), "verified")
        archives[0].write_bytes(b"untrusted bytes again")
        self.archive.unlink()
        failed, build = self.configure("third", digest)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((build / "answer.txt").exists())

    def test_empty_option_retains_direct_pinned_download(self):
        digest = self.make_archive("clean mode")
        result, build = self.configure("clean", digest, cache=False)
        self.require_success(result)
        self.assertEqual((build / "answer.txt").read_text(), "clean mode")
        self.assertFalse(self.cache.exists())
        self.assertFalse((self.area / "inherited-cache").exists())


if __name__ == "__main__":
    unittest.main()
