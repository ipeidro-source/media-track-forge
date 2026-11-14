"""Read-only local path checks; no destination directory or file is created."""

import os
import re
from pathlib import Path, PureWindowsPath


def equivalent_paths(left: Path, right: Path, *, windows: bool | None = None) -> bool:
    """Use Windows case folding on Windows; resolve symlinks before calling."""
    use_windows = os.name == "nt" if windows is None else windows
    if use_windows:
        return PureWindowsPath(str(left)) == PureWindowsPath(str(right))
    return left == right


def destination_path(value: str) -> Path:
    if not value or "\x00" in value or value.startswith(("//", "\\\\")):
        raise ValueError("Provide a nonempty local output path; UNC paths are unsupported.")
    drive = os.name == "nt" and re.match(r"^[a-zA-Z]:[\\/]", value)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) and not drive:
        raise ValueError("Output protocol URLs are unsupported; use a local path.")
    path = Path(value).resolve(strict=False)
    if str(path).startswith(("//", "\\\\")):
        raise ValueError("Network output paths are unsupported.")
    if os.name == "nt":
        for part in path.parts[1:]:
            stem = part.split(".")[0].upper()
            if (
                re.search(r'[<>:"|?*\x00-\x1f]', part)
                or part.endswith((" ", "."))
                or stem in {"CON", "PRN", "AUX", "NUL"}
                or re.fullmatch(r"(?:COM|LPT)[1-9]", stem)
            ):
                raise ValueError("The output contains an invalid Windows path component.")
    return path
