"""Managed, bounded shell-free process execution; no command strings are accepted."""

import io
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import cast

from mediatrack_forge.application.control import ExecutionControl
from mediatrack_forge.domain.execution import ExecutionFailure, ProcessOutcome
from mediatrack_forge.infrastructure.ffmpeg_progress import ProgressParser
from mediatrack_forge.infrastructure.windows_job import WindowsJob

CAPTURE_LIMIT = 64 * 1024


def discover_ffmpeg(override: str | None) -> str:
    try:
        executable = shutil.which(override if override is not None else "ffmpeg")
    except (ValueError, OSError) as exc:
        raise ExecutionFailure("MISSING_EXECUTABLE") from exc
    if executable is None or (os.name == "nt" and Path(executable).suffix.lower() != ".exe"):
        raise ExecutionFailure("MISSING_EXECUTABLE")
    return executable


def _linux_group_stopped(group: int) -> bool:
    """Zombie processes cannot write; wait for all live group members to terminate."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group and fields[0] not in ("Z", "X"):
                return False
        except (FileNotFoundError, ProcessLookupError):
            continue
    return True


def _stop_group(process: subprocess.Popen[bytes], job: WindowsJob | None) -> bool:
    try:
        if job is not None:
            stopped = job.terminate()
        else:
            if sys.platform == "win32":
                return False
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stopped = False
        process.wait(timeout=5)
        if job is not None:
            return stopped
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _linux_group_stopped(process.pid):
                return True
            time.sleep(0.01)
        return False
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


class FFmpegProcessRunner:
    def run(self, arguments: tuple[str, ...], timeout_seconds: float) -> ProcessOutcome:
        return self.run_controlled(arguments, timeout_seconds, None)

    def run_controlled(
        self, arguments: tuple[str, ...], timeout_seconds: float, control: ExecutionControl | None
    ) -> ProcessOutcome:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            return ProcessOutcome(None, "INVALID_TIMEOUT")
        if control is not None and control.cancellation.requested:
            return ProcessOutcome(None, "PROCESS_CANCELLED")
        job: WindowsJob | None = None
        process: subprocess.Popen[bytes] | None = None
        readers: list[threading.Thread] = []
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()
        code: str | None = None
        safe = True
        parser = ProgressParser()
        progress_lock = threading.Lock()
        last_event = 0.0

        def drain(pipe: io.BufferedReader, target: bytearray) -> None:
            try:
                while chunk := pipe.read1(8192):
                    remaining = CAPTURE_LIMIT - len(target)
                    target.extend(chunk[:remaining])
                    if control is not None and target is buffers[0]:
                        with progress_lock:
                            parser.feed(chunk)
                    elif len(chunk) > remaining:
                        overflow.set()
            except (OSError, ValueError):
                overflow.set()
            finally:
                pipe.close()

        try:
            if os.name == "nt":
                job = WindowsJob()
            process = subprocess.Popen(
                arguments,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name != "nt",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            if job is not None:
                try:
                    job.assign(int(vars(process)["_handle"]))
                except OSError:
                    process.kill()
                    process.wait(timeout=5)
                    return ProcessOutcome(process.returncode, "PROCESS_CONTAINMENT_FAILED", False)
            assert process.stdout is not None and process.stderr is not None
            for pipe, buffer in zip((process.stdout, process.stderr), buffers, strict=True):
                reader = threading.Thread(
                    target=drain, args=(cast(io.BufferedReader, pipe), buffer), daemon=True
                )
                readers.append(reader)
                reader.start()
            deadline = time.monotonic() + timeout_seconds
            while process.poll() is None or any(reader.is_alive() for reader in readers):
                if control is not None:
                    if control.cancellation.requested:
                        control.emit("cancelling")
                        code = "PROCESS_CANCELLED"
                        break
                    if time.monotonic() - last_event >= 0.1:
                        with progress_lock:
                            seconds = parser.seconds
                        control.emit("running", seconds)
                        last_event = time.monotonic()
                if overflow.is_set():
                    code = "PROCESS_OUTPUT_LIMIT"
                    break
                if time.monotonic() >= deadline:
                    code = "PROCESS_TIMEOUT"
                    break
                overflow.wait(0.01)
            if code is None and overflow.is_set():
                code = "PROCESS_OUTPUT_LIMIT"
            if code is None and process.returncode != 0:
                code = "FFMPEG_FAILED"
        except (OSError, ValueError):
            code = "PROCESS_LAUNCH_FAILED"
        except Exception:
            code = "PROCESS_FAILED"
        finally:
            if process is not None:
                safe = _stop_group(process, job)
                if not safe:
                    code = "PROCESS_TERMINATION_FAILED"
                for reader in readers:
                    reader.join(timeout=1)
                if any(reader.is_alive() for reader in readers):
                    safe = False
                    code = "PROCESS_TERMINATION_FAILED"
                if not readers:
                    for remaining_pipe in (process.stdout, process.stderr):
                        if remaining_pipe is not None:
                            remaining_pipe.close()
            if job is not None:
                job.close()
        return ProcessOutcome(
            process.returncode if process is not None else None,
            code,
            safe,
            len(buffers[0]),
            len(buffers[1]),
        )
