#pragma once
// Force-included into every file of the Windows simulator build (see build.sh).
// MinGW's <time.h> then declares localtime_r / gmtime_r.
#ifndef _POSIX_THREAD_SAFE_FUNCTIONS
#define _POSIX_THREAD_SAFE_FUNCTIONS 200112L
#endif
typedef unsigned int uint;  // glibc's <sys/types.h> name, used by PNGdec

#ifndef __cplusplus
// expat's winconfig.h includes <memory.h>, which on a case-insensitive disk
// resolves to the firmware's lib/Memory/Memory.h (C++). Do its job here instead.
#define WINCONFIG_H
#define _CRT_RAND_S  // expat seeds its hash with rand_s(); must precede stdlib.h
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX  // QRCode and others define their own max()
#include <windows.h>
#undef WIN32_LEAN_AND_MEAN
#include <string.h>
#endif

#ifdef __cplusplus
#include <cerrno>
#include <cstdint>  // glibc brings it in through other headers; some firmware code relies on that
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <direct.h>
#include <io.h>
#include <sys/stat.h>

// MinGW has neither. Its malloc already returns 16-byte (max_align_t) blocks,
// and the callers free with std::free, so _aligned_malloc cannot be used.
// shortcut: alignments above 16 fail with ENOMEM, upgrade if a screen needs them.
inline int posix_memalign(void **out, size_t alignment, size_t bytes) {
  if (alignment > alignof(std::max_align_t)) return ENOMEM;
  *out = std::malloc(bytes);
  return *out ? 0 : ENOMEM;
}
// BSD string copy (glibc 2.38+ and macOS have it, MinGW does not).
inline size_t strlcpy(char *dst, const char *src, size_t size) {
  const size_t len = std::strlen(src);
  if (size) {
    const size_t n = len < size - 1 ? len : size - 1;
    std::memcpy(dst, src, n);
    dst[n] = '\0';
  }
  return len;
}
// POSIX file calls the simulator's SD-card stand-in uses.
inline int mkdir(const char *path, int /*mode*/) { return _mkdir(path); }
#define lstat stat  // Windows has no symlinks to skip here
inline char *realpath(const char *path, char *out) { return _fullpath(out, path, 260); }
inline int fsync(int fd) { return _commit(fd); }
inline int setenv(const char *name, const char *value, int overwrite) {
  if (!overwrite && std::getenv(name)) return 0;
  return _putenv_s(name, value);
}
inline int unsetenv(const char *name) { return _putenv_s(name, ""); }  // "" removes it on Windows
#include <cstdio>
#include <fcntl.h>
// The SD-card stand-in opens files without O_BINARY. Windows' default text mode turns CR LF into LF and stops
// reading at byte 0x1A, so books (zip files) and caches came back damaged. Binary, like a real SD card.
__attribute__((constructor)) static void winSimBinaryFiles() { _set_fmode(_O_BINARY); }
// std::filesystem::path::c_str() is wchar_t on Windows; firmware test code passes it to fopen (CrossInk 1.6.1).
inline FILE *fopen(const wchar_t *path, const char *mode) {
  wchar_t wmode[16] = {};
  for (int i = 0; i < 15 && mode[i]; ++i) wmode[i] = static_cast<wchar_t>(mode[i]);
  return _wfopen(path, wmode);
}
namespace std {
using ::fopen;
inline void *aligned_alloc(size_t alignment, size_t bytes) {
  return alignment <= alignof(max_align_t) ? malloc(bytes) : nullptr;
}
}  // namespace std
#endif

#ifdef RSIM_CROSSPOINT_COMPAT  // only in builds whose simulator setup adapter.py wrote (CrossPoint)
#include <sys/time.h>
// MinGW has gettimeofday but no settimeofday (CrossPoint 2.0's TrustedTime sets the clock from the
// network); the simulator keeps the PC's clock, so accept and ignore.
static inline int settimeofday(const struct timeval *tv, const void *tz) { (void)tv; (void)tz; return 0; }

#include <ctype.h>
#include <string.h>
// MinGW lacks the GNU strcasestr (AvesO3 uses it).
static inline char *strcasestr(const char *h, const char *n) {
  size_t len = strlen(n);
  for (; *h; h++)
    if (_strnicmp(h, n, len) == 0) return (char *)h;
  return len ? NULL : (char *)h;
}
#endif
