// g++ -include ../compat/win_sim_prelude.h binmode_check.cpp -o binmode_check && ./binmode_check
// Files opened without O_BINARY (as the simulator's SD card does) must keep CR LF and 0x1A bytes.
#include <fcntl.h>
#include <unistd.h>
int main() {
  const char data[] = "a\r\nb\x1a" "c";
  int fd = ::open("binmode_check.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0 || ::write(fd, data, 6) != 6) return 2;
  ::close(fd);
  char back[16] = {};
  fd = ::open("binmode_check.tmp", O_RDONLY);
  const int n = fd < 0 ? -1 : ::read(fd, back, sizeof back);
  ::close(fd);
  ::unlink("binmode_check.tmp");
  for (int i = 0; i < 6; ++i)
    if (n != 6 || back[i] != data[i]) return 1;
  return 0;
}
