// Windows stand-in for the two OpenSSL calls crosspoint-simulator's WolfsslCrypto.h makes
// (SHA1, SHA256 one-shot). Plain C++ so no Windows headers leak into firmware code.
// Self-check: tests/sha_check.cpp.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace rsim_sha {
inline uint32_t rol(uint32_t x, int n) { return (x << n) | (x >> (32 - n)); }
inline uint32_t ror(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

// Pads like both algorithms do (big-endian bit length) and feeds 64-byte blocks to f.
template <typename F>
inline void blocks(const unsigned char *d, size_t n, F f) {
  size_t full = n / 64 * 64;
  for (size_t i = 0; i < full; i += 64) f(d + i);
  unsigned char tail[128] = {0};
  size_t r = n - full;
  std::memcpy(tail, d + full, r);
  tail[r] = 0x80;
  size_t t = r < 56 ? 64 : 128;
  uint64_t bits = uint64_t(n) * 8;
  for (int i = 0; i < 8; i++) tail[t - 1 - i] = static_cast<unsigned char>(bits >> (8 * i));
  for (size_t i = 0; i < t; i += 64) f(tail + i);
}
inline uint32_t be(const unsigned char *p) { return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | p[3]; }
inline void put(unsigned char *o, const uint32_t *h, int n) {
  for (int i = 0; i < n; i++) for (int j = 0; j < 4; j++) o[4 * i + j] = static_cast<unsigned char>(h[i] >> (24 - 8 * j));
}
}  // namespace rsim_sha

inline unsigned char *SHA1(const unsigned char *d, size_t n, unsigned char *md) {
  using namespace rsim_sha;
  uint32_t h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};
  blocks(d, n, [&](const unsigned char *p) {
    uint32_t w[80];
    for (int i = 0; i < 16; i++) w[i] = be(p + 4 * i);
    for (int i = 16; i < 80; i++) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    uint32_t a = h[0], b = h[1], c = h[2], e = h[4], dd = h[3];
    for (int i = 0; i < 80; i++) {
      uint32_t f, k;
      if (i < 20) f = (b & c) | (~b & dd), k = 0x5A827999;
      else if (i < 40) f = b ^ c ^ dd, k = 0x6ED9EBA1;
      else if (i < 60) f = (b & c) | (b & dd) | (c & dd), k = 0x8F1BBCDC;
      else f = b ^ c ^ dd, k = 0xCA62C1D6;
      uint32_t t = rol(a, 5) + f + e + k + w[i];
      e = dd; dd = c; c = rol(b, 30); b = a; a = t;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += dd; h[4] += e;
  });
  put(md, h, 5);
  return md;
}

namespace rsim_sha {
inline void sha256_block(uint32_t *h, const unsigned char *p) {
  static const uint32_t K[64] = {
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
  uint32_t w[64];
  for (int i = 0; i < 16; i++) w[i] = be(p + 4 * i);
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = ror(w[i - 15], 7) ^ ror(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = ror(w[i - 2], 17) ^ ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t v[8];
  std::memcpy(v, h, sizeof v);
  for (int i = 0; i < 64; i++) {
    uint32_t t1 = v[7] + (ror(v[4], 6) ^ ror(v[4], 11) ^ ror(v[4], 25)) + ((v[4] & v[5]) ^ (~v[4] & v[6])) + K[i] + w[i];
    uint32_t t2 = (ror(v[0], 2) ^ ror(v[0], 13) ^ ror(v[0], 22)) + ((v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]));
    std::memmove(v + 1, v, 7 * sizeof(uint32_t));
    v[4] += t1;
    v[0] = t1 + t2;
  }
  for (int i = 0; i < 8; i++) h[i] += v[i];
}
}  // namespace rsim_sha

inline unsigned char *SHA256(const unsigned char *d, size_t n, unsigned char *md) {
  using namespace rsim_sha;
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  blocks(d, n, [&](const unsigned char *p) { sha256_block(h, p); });
  put(md, h, 8);
  return md;
}

// Streaming form (CrossMux's simulator mbedtls/sha256.h). Plain data: callers memset it.
struct SHA256_CTX {
  uint32_t h[8];
  uint64_t len;
  unsigned char buf[64];
  size_t n;
};
inline int SHA256_Init(SHA256_CTX *c) {
  static const uint32_t h0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  std::memcpy(c->h, h0, sizeof h0);
  c->len = 0;
  c->n = 0;
  return 1;
}
inline int SHA256_Update(SHA256_CTX *c, const void *data, size_t len) {
  const unsigned char *d = static_cast<const unsigned char *>(data);
  c->len += len;
  while (len) {
    size_t take = 64 - c->n < len ? 64 - c->n : len;
    std::memcpy(c->buf + c->n, d, take);
    c->n += take; d += take; len -= take;
    if (c->n == 64) rsim_sha::sha256_block(c->h, c->buf), c->n = 0;
  }
  return 1;
}
inline int SHA256_Final(unsigned char *md, SHA256_CTX *c) {
  uint64_t bits = c->len * 8;
  c->buf[c->n++] = 0x80;
  if (c->n > 56) {
    std::memset(c->buf + c->n, 0, 64 - c->n);
    rsim_sha::sha256_block(c->h, c->buf);
    c->n = 0;
  }
  std::memset(c->buf + c->n, 0, 56 - c->n);
  for (int i = 0; i < 8; i++) c->buf[63 - i] = static_cast<unsigned char>(bits >> (8 * i));
  rsim_sha::sha256_block(c->h, c->buf);
  rsim_sha::put(md, c->h, 8);
  return 1;
}
