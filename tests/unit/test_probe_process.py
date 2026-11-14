"""Exercise the bounded subprocess runner with Python, never external media tools."""

import subprocess
import sys
from unittest.mock import Mock

import pytest

from mediatrack_forge.application.inspection import (
    ExecutableError,
    ProbeFailedError,
    ProbeResponseError,
    ProbeTimeoutError,
)
from mediatrack_forge.infrastructure import ffprobe


def test_runner_uses_no_shell_and_detached_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    original = subprocess.Popen
    popen = Mock(wraps=original)
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.subprocess.Popen", popen)
    assert ffprobe.run_bounded([sys.executable, "-c", "print('ok')"], 10).strip() == b"ok"
    assert popen.call_args.kwargs["shell"] is False
    assert popen.call_args.kwargs["stdin"] == subprocess.DEVNULL


def test_unusable_executable() -> None:
    with pytest.raises(ExecutableError):
        ffprobe.run_bounded(["/definitely/not/an/executable"], 5)


def test_timeout_kills_and_reaps_process(monkeypatch: pytest.MonkeyPatch) -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    popen = Mock(return_value=child)
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.subprocess.Popen", popen)
    with pytest.raises(ProbeTimeoutError):
        ffprobe.run_bounded([sys.executable, "-c", "import time; time.sleep(60)"], 0.2)
    # The real child is collected by the runner; no running process is left behind.
    assert child.poll() is not None


def test_nonzero_exit_does_not_leak_diagnostics() -> None:
    with pytest.raises(ProbeFailedError) as exc:
        ffprobe.run_bounded(
            [
                sys.executable,
                "-c",
                "import sys; print('private diagnostic', file=sys.stderr); sys.exit(7)",
            ],
            10,
        )
    assert "7" in str(exc.value)
    assert "private diagnostic" not in str(exc.value)


@pytest.mark.parametrize("channel", ["stdout", "stderr"])
def test_output_is_bounded(channel: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffprobe, "MAX_STDOUT_BYTES", 1024)
    monkeypatch.setattr(ffprobe, "MAX_STDERR_BYTES", 1024)
    with pytest.raises(ProbeResponseError, match="safety limit"):
        ffprobe.run_bounded(
            [sys.executable, "-c", f"import sys; sys.{channel}.write('x' * 1000000)"], 10
        )
