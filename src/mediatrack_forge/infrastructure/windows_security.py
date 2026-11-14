"""Narrow Windows security helpers, loaded only on Windows."""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path


def private_directory(path: Path) -> None:
    """Create with a protected owner/SYSTEM-only inheritable DACL from the outset."""
    if sys.platform != "win32":
        raise OSError("Windows security APIs are unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_path = ctypes.create_unicode_buffer(32768)
    get_path = kernel.GetVolumePathNameW
    get_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_path.restype = wintypes.BOOL
    get_volume = kernel.GetVolumeInformationW
    get_volume.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    get_volume.restype = wintypes.BOOL
    flags = wintypes.DWORD()
    if (
        not get_path(str(path.parent), volume_path, len(volume_path))
        or not get_volume(volume_path.value, None, 0, None, None, ctypes.byref(flags), None, 0)
        or flags.value & 0x00400008 != 0x00400008
    ):
        raise OSError("Private staging requires persistent ACLs and hard-link support")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    descriptor = wintypes.LPVOID()
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.DWORD),
    ]
    convert.restype = wintypes.BOOL
    if not convert("D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;OW)", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.DWORD),
            ("descriptor", wintypes.LPVOID),
            ("inherit", wintypes.BOOL),
        ]

    create = kernel.CreateDirectoryW
    create.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(SecurityAttributes)]
    create.restype = wintypes.BOOL
    free = kernel.LocalFree
    free.argtypes = [wintypes.LPVOID]
    free.restype = wintypes.LPVOID
    attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
    try:
        if not create(str(path), ctypes.byref(attributes)):
            error = ctypes.get_last_error()
            if error == 183:
                raise FileExistsError(error, "Private staging name collision")
            raise ctypes.WinError(error)
    finally:
        free(descriptor)
