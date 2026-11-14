"""Narrow native volume classification for local-only output publication."""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path


def require_local_volume(path: Path) -> None:
    """Reject remote/unknown volumes, including mapped drives that retain a letter."""
    if sys.platform != "win32":
        raise OSError("Windows volume classification is unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_volume = kernel.GetVolumePathNameW
    get_volume.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_volume.restype = wintypes.BOOL
    get_type = kernel.GetDriveTypeW
    get_type.argtypes = [wintypes.LPCWSTR]
    get_type.restype = wintypes.UINT
    volume = ctypes.create_unicode_buffer(32768)
    # The parent may not exist yet: locate its closest existing ancestor read-only.
    parent = path.parent
    while not parent.exists() and parent.parent != parent:
        parent = parent.parent
    if not get_volume(str(parent), volume, len(volume)):
        raise ValueError("Cannot establish a local output volume; choose a local destination.")
    if get_type(volume.value) not in (2, 3, 6):  # removable, fixed, RAM disk
        raise ValueError(
            "Network or unverified output volumes are unsupported; choose a local disk."
        )
