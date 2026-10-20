"""Puts compat/utf8.manifest into program.exe in place of MinGW's default manifest (same type 24, id 1,
language en-US 0x409, so it is replaced rather than added). The UTF-8 code page makes the simulator's char
file calls work in folders with Persian letters, ü, ... (Windows 10 1903+). Run after strip.
    python set_manifest.py <program.exe>"""
import ctypes
import os
import sys

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.BeginUpdateResourceW.restype = ctypes.c_void_p
k.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
k.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort, ctypes.c_char_p, ctypes.c_ulong]
k.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_bool]
data = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "utf8.manifest"), "rb").read()
h = k.BeginUpdateResourceW(sys.argv[1], False)
if not h or not k.UpdateResourceW(h, 24, 1, 0x409, data, len(data)) or not k.EndUpdateResourceW(h, False):
    sys.exit(f"set_manifest: failed ({ctypes.get_last_error()})")
