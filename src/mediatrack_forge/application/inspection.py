"""Local source validation and inspection orchestration with a replaceable probe port."""

import math
import os
import re
import stat
from pathlib import Path
from typing import Protocol

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


class MediaProbe(Protocol):
    def inspect(self, source: MediaSource, *, timeout_seconds: float) -> MediaAsset:
        """Return an immutable snapshot or raise a controlled inspection error."""
        ...


def snapshot_source(path: str | Path) -> MediaSource:
    """Resolve a regular local file; reject protocol URLs and UNC network paths."""
    raw = str(path)
    drive_path = os.name == "nt" and re.match(r"^[a-zA-Z]:[\\/]", raw)
    if (
        not raw
        or "\x00" in raw
        or raw.startswith(("\\\\", "//"))
        or (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw) and not drive_path)
    ):
        raise InvalidInputError(
            "Provide a regular local file path; URLs and UNC paths are blocked."
        )
    try:
        resolved = Path(path).resolve(strict=True)
        if str(resolved).startswith(("\\\\", "//")):
            raise InvalidInputError("Network source paths are not supported.")
        info = resolved.stat()
        if not stat.S_ISREG(info.st_mode):
            raise InvalidInputError("The input must be a regular local file.")
        with resolved.open("rb"):
            pass
    except (OSError, ValueError, RuntimeError) as exc:
        raise InvalidInputError(
            "Cannot read the input file; check its path and permissions."
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
