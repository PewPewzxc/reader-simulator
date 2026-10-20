#pragma once
// Windows stand-in for OpenSSL's MD5 (RFC 1321), used by KOReader document ids.
// Self-check: dev/sim-windows/tests/md5_check.cpp.
#include <cstddef>
#include <cstdint>
#include <cstring>

struct MD5_CTX {
  uint32_t state[4];
  uint64_t bytes;
  unsigned char buffer[64];
};

namespace win_sim_md5 {
inline uint32_t rotl(uint32_t x, int c) { return (x << c) | (x >> (32 - c)); }
inline void block(uint32_t s[4], const unsigned char *p) {
  static const uint32_t K[64] = {
      0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
      0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be, 0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
      0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa, 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
      0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed, 0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
      0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c, 0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
      0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
      0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
      0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1, 0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391};
  static const int R[16] = {7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21};
  uint32_t m[16];
  for (int i = 0; i < 16; i++)
    m[i] = uint32_t(p[i * 4]) | uint32_t(p[i * 4 + 1]) << 8 | uint32_t(p[i * 4 + 2]) << 16 | uint32_t(p[i * 4 + 3]) << 24;
  uint32_t a = s[0], b = s[1], c = s[2], d = s[3];
  for (int i = 0; i < 64; i++) {
    uint32_t f;
    int g;
    if (i < 16) f = (b & c) | (~b & d), g = i;
    else if (i < 32) f = (d & b) | (~d & c), g = (5 * i + 1) % 16;
    else if (i < 48) f = b ^ c ^ d, g = (3 * i + 5) % 16;
    else f = c ^ (b | ~d), g = (7 * i) % 16;
    const uint32_t t = d;
    d = c;
    c = b;
    b = b + rotl(a + f + K[i] + m[g], R[(i / 16) * 4 + i % 4]);
    a = t;
  }
  s[0] += a, s[1] += b, s[2] += c, s[3] += d;
}
}  // namespace win_sim_md5

inline int MD5_Init(MD5_CTX *c) {
  c->state[0] = 0x67452301, c->state[1] = 0xefcdab89, c->state[2] = 0x98badcfe, c->state[3] = 0x10325476;
  c->bytes = 0;
  return 1;
}
inline int MD5_Update(MD5_CTX *c, const void *data, size_t len) {
  const auto *p = static_cast<const unsigned char *>(data);
  while (len--) {
    c->buffer[c->bytes++ % 64] = *p++;
    if (c->bytes % 64 == 0) win_sim_md5::block(c->state, c->buffer);
  }
  return 1;
}
inline int MD5_Final(unsigned char *out, MD5_CTX *c) {
  const uint64_t bits = c->bytes * 8;
  const unsigned char pad = 0x80, zero = 0;
  MD5_Update(c, &pad, 1);
  while (c->bytes % 64 != 56) MD5_Update(c, &zero, 1);
  for (int i = 0; i < 8; i++) {
    const unsigned char b = static_cast<unsigned char>(bits >> (8 * i));
    MD5_Update(c, &b, 1);
  }
  for (int i = 0; i < 16; i++) out[i] = static_cast<unsigned char>(c->state[i / 4] >> (8 * (i % 4)));
  return 1;
}
