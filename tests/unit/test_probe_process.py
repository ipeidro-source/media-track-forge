"""Exercise the bounded subprocess runner with Python, never external media tools."""

import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest

from mediatrack_forge.application.control import CancellationToken
from mediatrack_forge.application.inspection import (
    ExecutableError,
    ProbeFailedError,
    ProbeOutputLimitError,
    ProbeResponseError,
    ProbeTimeoutError,
)
from mediatrack_forge.domain.execution import ExecutionFailure
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


def test_packet_probe_cancellation_kills_and_reaps_before_long_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.ffprobe.subprocess.Popen", Mock(return_value=child)
    )
    token = CancellationToken()
    timer = threading.Timer(0.2, token.cancel)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(ExecutionFailure, match="PROCESS_CANCELLED"):
            ffprobe.run_bounded([sys.executable], 300, cancellation=token)
    finally:
        timer.cancel()
        timer.join()
        if child.poll() is None:
            child.kill()
            child.wait()
    assert child.poll() is not None and time.monotonic() - started < 5


def test_cancelled_packet_probe_never_launches(monkeypatch: pytest.MonkeyPatch) -> None:
    popen = Mock()
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.subprocess.Popen", popen)
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ExecutionFailure, match="PROCESS_CANCELLED"):
        ffprobe.run_bounded([sys.executable], 300, cancellation=token)
    popen.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_probe_deadline_never_launches(
    timeout: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mediatrack_forge.application.inspection import InvalidInputError

    popen = Mock()
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffprobe.subprocess.Popen", popen)
    with pytest.raises(InvalidInputError):
        ffprobe.run_bounded([sys.executable], timeout)
    popen.assert_not_called()


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
    with pytest.raises(ProbeOutputLimitError, match="safety limit") as failure:
        ffprobe.run_bounded(
            [sys.executable, "-c", f"import sys; sys.{channel}.write('x' * 1000000)"], 10
        )
    assert isinstance(failure.value, ProbeResponseError) and failure.value.channel == channel
