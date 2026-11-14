"""Shell-free external ffprobe adapter with bounded output and a wall-clock timeout."""

import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import BinaryIO

from mediatrack_forge.application.inspection import (
    ExecutableError,
    InvalidInputError,
    ProbeFailedError,
    ProbeResponseError,
    ProbeTimeoutError,
)
from mediatrack_forge.domain.media import MediaAsset, MediaSource
from mediatrack_forge.infrastructure.ffprobe_json import parse_response

MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024


def run_bounded(arguments: list[str], timeout_seconds: float) -> bytes:
    """Drain both pipes concurrently; terminate on timeout or output overflow.

    ffprobe is a single native process. Explicit executable overrides are trusted
    programs, not a sandbox for arbitrary process trees.
    """
    try:
        process = subprocess.Popen(
            arguments,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, ValueError) as exc:
        raise ExecutableError("Cannot launch ffprobe; select a usable native executable.") from exc

    overflow = threading.Event()
    output = bytearray()
    diagnostics = bytearray()

    def drain(pipe: BinaryIO, buffer: bytearray, limit: int) -> None:
        try:
            while chunk := pipe.read(65536):
                remaining = limit - len(buffer)
                buffer.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    return
        finally:
            pipe.close()

    assert process.stdout is not None and process.stderr is not None
    readers = [
        threading.Thread(
            target=drain, args=(process.stdout, output, MAX_STDOUT_BYTES), daemon=True
        ),
        threading.Thread(
            target=drain, args=(process.stderr, diagnostics, MAX_STDERR_BYTES), daemon=True
        ),
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None or any(reader.is_alive() for reader in readers):
            if overflow.is_set():
                raise ProbeResponseError(
                    "ffprobe output exceeded the safety limit; reduce metadata."
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeTimeoutError("ffprobe timed out; retry with a larger --timeout-seconds.")
            overflow.wait(min(remaining, 0.02))
        if overflow.is_set():
            raise ProbeResponseError("ffprobe output exceeded the safety limit; reduce metadata.")
        if process.returncode != 0:
            raise ProbeFailedError(
                f"ffprobe exited with code {process.returncode}; "
                "the media may be unreadable, invalid, unsupported, or require a blocked protocol."
            )
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=1)


class FFprobeAdapter:
    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable

    def inspect(self, source: MediaSource, *, timeout_seconds: float = 30.0) -> MediaAsset:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise InvalidInputError("Timeout must be a finite positive number of seconds.")
        try:
            executable = shutil.which(
                self._executable if self._executable is not None else "ffprobe"
            )
        except (OSError, ValueError) as exc:
            raise ExecutableError("Cannot resolve ffprobe; check the executable path.") from exc
        if executable is None:
            raise ExecutableError("ffprobe was not found; install it on PATH or use --ffprobe.")
        if os.name == "nt" and Path(executable).suffix.lower() not in (".exe", ".com"):
            raise ExecutableError(
                "Select a native ffprobe executable; shell scripts are not allowed."
            )
        arguments = [
            executable,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-of",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-i",
            str(source.path),
        ]
        return parse_response(run_bounded(arguments, timeout_seconds), source)
