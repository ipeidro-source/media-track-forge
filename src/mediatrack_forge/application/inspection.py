"""Read-only filesystem source inspection, including trusted Windows file shares."""

import math
import os
import re
import stat
from pathlib import Path
from typing import Literal, Protocol

from mediatrack_forge.domain.media import MediaAsset, MediaSource


class InspectionError(Exception):
    """Controlled inspection failure with a stable CLI exit code."""

    exit_code = 4


class InvalidInputError(InspectionError):
    exit_code = 2


class ExecutableError(InspectionError):
    exit_code = 3


class ProbeFailedError(InspectionError):
    exit_code = 4


class ProbeTimeoutError(InspectionError):
    exit_code = 5


class ProbeResponseError(InspectionError):
    exit_code = 6


class ProbeOutputLimitError(ProbeResponseError):
    """A bounded pipe overflow; channel is controlled, never external diagnostic text."""

    def __init__(self, channel: Literal["stdout", "stderr"]) -> None:
        self.channel = channel
        super().__init__(f"ffprobe {channel} exceeded the safety limit.")


class MediaProbe(Protocol):
    def inspect(self, source: MediaSource, *, timeout_seconds: float) -> MediaAsset:
        """Return an immutable snapshot or raise a controlled inspection error."""
        ...


def snapshot_source(path: str | Path) -> MediaSource:
    """Canonicalize a readable regular file; Windows UNC is a file path, not a URL."""
    raw = str(path)
    windows_spelling = raw.replace("/", "\\")
    extended_unc = os.name == "nt" and windows_spelling.upper().startswith("\\\\?\\UNC\\")
    drive_path = os.name == "nt" and re.match(r"^[a-zA-Z]:[\\/]", raw)
    if (
        not raw
        or "\x00" in raw
        or (os.name != "nt" and raw.startswith(("\\\\", "//")))
        or (windows_spelling.startswith(("\\\\?\\", "\\\\.\\")) and not extended_unc)
        or (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw) and not drive_path)
    ):
        raise InvalidInputError(
            "Provide a regular filesystem file path; URLs and device paths are blocked."
        )
    try:
        resolved = Path(path).resolve(strict=True)
        if os.name != "nt" and str(resolved).startswith(("\\\\", "//")):
            raise InvalidInputError("UNC source paths require Windows.")
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode):
            raise InvalidInputError("The input must be a regular file.")
        with resolved.open("rb"):
            pass
    except FileNotFoundError as exc:
        raise InvalidInputError(
            "Cannot find the source file; check the path and mapped drive/share availability."
        ) from exc
    except PermissionError as exc:
        raise InvalidInputError(
            "Source access was denied; check file permissions and network share access."
        ) from exc
    except (OSError, ValueError, RuntimeError) as exc:
        raise InvalidInputError(
            "Cannot read the source file; check its path, permissions and network connection."
        ) from exc
    return MediaSource(resolved, info.st_size, info.st_mtime_ns)


class InspectionService:
    def __init__(self, probe: MediaProbe) -> None:
        self._probe = probe

    def inspect(self, path: str | Path, *, timeout_seconds: float = 30.0) -> MediaAsset:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise InvalidInputError("Timeout must be a finite positive number of seconds.")
        source = snapshot_source(path)
        asset = self._probe.inspect(source, timeout_seconds=timeout_seconds)
        try:
            after = snapshot_source(source.path)
        except InvalidInputError as exc:
            raise ProbeFailedError(
                "The source became unavailable during inspection; retry."
            ) from exc
        if after != source:
            raise ProbeFailedError(
                "The source changed during inspection; retry with a stable file."
            )
        return asset
