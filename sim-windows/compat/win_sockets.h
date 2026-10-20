#pragma once
// Windows stand-in for the POSIX socket headers the simulator's web server and
// HTTP clients use. It is enough to compile and run them on Winsock; Wi-Fi is
// never started by the screen tests, so WSAStartup is not called.
// shortcut: no WSAStartup and close() is not closesocket(), upgrade before testing file transfer.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif
#ifndef SHUT_RDWR
#define SHUT_RDWR SD_BOTH
#endif
#ifndef F_GETFL
#define F_GETFL 3
#define F_SETFL 4
#endif
#ifndef O_NONBLOCK
#define O_NONBLOCK 0x80000
#endif

// Winsock takes char* buffers and option values; POSIX code passes any pointer.
// Templates win overload resolution over the Winsock functions without
// hijacking calls that already match them exactly.
template <class F, class B, class N>
inline ssize_t send(F fd, const B *buf, N len, int flags) {
  return ::send(static_cast<SOCKET>(fd), reinterpret_cast<const char *>(buf), static_cast<int>(len), flags);
}
template <class F, class B, class N>
inline ssize_t recv(F fd, B *buf, N len, int flags) {
  return ::recv(static_cast<SOCKET>(fd), reinterpret_cast<char *>(buf), static_cast<int>(len), flags);
}
template <class F, class V, class N>
inline int setsockopt(F fd, int level, int name, const V *value, N len) {
  return ::setsockopt(static_cast<SOCKET>(fd), level, name, reinterpret_cast<const char *>(value), static_cast<int>(len));
}
template <class F, class V>
inline int getsockopt(F fd, int level, int name, V *value, socklen_t *len) {
  return ::getsockopt(static_cast<SOCKET>(fd), level, name, reinterpret_cast<char *>(value), len);
}
inline int poll(pollfd *fds, unsigned long count, int timeoutMs) { return WSAPoll(fds, count, timeoutMs); }
template <class T>
inline int ioctl(int fd, long request, T *arg) {
  u_long value = 0;
  const int result = ioctlsocket(static_cast<SOCKET>(fd), request, &value);
  *arg = static_cast<T>(value);
  return result;
}
inline int fcntl(int fd, int cmd, int arg = 0) {
  if (cmd != F_SETFL) return 0;
  u_long nonBlocking = (arg & O_NONBLOCK) ? 1 : 0;
  return ioctlsocket(static_cast<SOCKET>(fd), FIONBIO, &nonBlocking);
}
