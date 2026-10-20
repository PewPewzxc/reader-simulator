#pragma once
// Windows stand-in for statvfs(): sizes in bytes (block size 1).
#include <filesystem>
#include <system_error>
struct statvfs {
  unsigned long f_bsize = 1, f_frsize = 1;
  unsigned long long f_blocks = 0, f_bfree = 0, f_bavail = 0;
};
inline int statvfs(const char *path, struct statvfs *out) {
  std::error_code error;
  const auto space = std::filesystem::space(path, error);
  if (error) return -1;
  out->f_blocks = space.capacity;
  out->f_bfree = space.free;
  out->f_bavail = space.available;
  return 0;
}
