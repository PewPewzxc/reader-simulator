#pragma once
// MinGW's pclose() already returns the child's exit code.
#define WIFEXITED(status) ((status) != -1)
#define WEXITSTATUS(status) (status)
