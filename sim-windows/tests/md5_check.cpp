// g++ -I../compat md5_check.cpp -o md5_check && ./md5_check
#include <openssl/md5.h>
#include <cassert>
#include <cstdio>
#include <string>
static std::string md5(const std::string &s) {
  MD5_CTX c;
  unsigned char d[16];
  char hex[33];
  MD5_Init(&c);
  MD5_Update(&c, s.data(), s.size());
  MD5_Final(d, &c);
  for (int i = 0; i < 16; i++) std::snprintf(hex + i * 2, 3, "%02x", d[i]);
  return hex;
}
int main() {
  assert(md5("") == "d41d8cd98f00b204e9800998ecf8427e");
  assert(md5("abc") == "900150983cd24fb0d6963f7d28e17f72");
  assert(md5(std::string(1000, 'a')) == "cabe45dcc9ae5b66ba86600cca6b8ba8");
  std::puts("md5 ok");
}
