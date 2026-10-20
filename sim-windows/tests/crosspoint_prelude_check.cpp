// g++ -DRSIM_CROSSPOINT_COMPAT -include ../compat/win_sim_prelude.h crosspoint_prelude_check.cpp && ./a.exe   (prints OK)
#include <cstdio>
int main() {
  bool ok = strcasestr("Hello World", "WORLD") && !strcasestr("abc", "x") && *strcasestr("abc", "") == 'a' &&
            settimeofday(nullptr, nullptr) == 0;
  puts(ok ? "OK" : "FAIL");
  return !ok;
}
