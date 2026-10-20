#include <filesystem>
#include <cstdio>
int main(){auto p=std::filesystem::path("a")/"b.txt"; FILE*f=std::fopen(p.c_str(),"wb"); FILE*g=fopen("x","r"); return !f + (g!=nullptr);}
