// g++ -I../compat sha_check.cpp && ./a.exe   (prints OK)
#include <openssl/sha.h>
#include <cstdio>
#include <string>
static std::string hex(const unsigned char *m, int n) { std::string s; char b[3]; for (int i = 0; i < n; i++) { snprintf(b, 3, "%02x", m[i]); s += b; } return s; }
int main() {
  unsigned char m[32];
  std::string a = "abc", l(1000, 'a'), e = "";
  bool ok = hex(SHA1((const unsigned char *)a.data(), 3, m), 20) == "a9993e364706816aba3e25717850c26c9cd0d89d"
    && hex(SHA256((const unsigned char *)a.data(), 3, m), 32) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    && hex(SHA256((const unsigned char *)e.data(), 0, m), 32) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    && hex(SHA1((const unsigned char *)l.data(), 1000, m), 20) == "291e9a6c66994949b57ba5e650361e98fc36b1ba";
  SHA256_CTX c;  // streaming, in uneven pieces: must match the one-shot result
  SHA256_Init(&c);
  for (size_t i = 0; i < 1000; i += 37) SHA256_Update(&c, l.data() + i, i + 37 > 1000 ? 1000 - i : 37);
  unsigned char s[32];
  SHA256_Final(s, &c);
  ok = ok && hex(s, 32) == hex(SHA256((const unsigned char *)l.data(), 1000, m), 32)
    && hex(s, 32) == "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3";
  puts(ok ? "OK" : "FAIL");
  return !ok;
}
