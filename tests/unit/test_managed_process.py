"""Real Python child processes exercise managed lifecycle without media executables."""

import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from mediatrack_forge.domain.execution import ExecutionFailure
from mediatrack_forge.infrastructure.ffmpeg_process import (
    CAPTURE_LIMIT,
    FFmpegProcessRunner,
    discover_ffmpeg,
)


def test_process_success_and_no_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    popen = Mock(wraps=subprocess.Popen)
    monkeypatch.setattr("mediatrack_forge.infrastructure.ffmpeg_process.subprocess.Popen", popen)
    result = FFmpegProcessRunner().run((sys.executable, "-c", "print('ok')"), 10)
    assert result.error_code is None and result.return_code == 0 and result.safe_to_cleanup
    assert popen.call_args.kwargs["shell"] is False
    assert popen.call_args.kwargs["stdin"] == subprocess.DEVNULL


def test_launch_and_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    result = FFmpegProcessRunner().run(("/missing/native/executable",), 5)
    assert result.error_code == "PROCESS_LAUNCH_FAILED" and result.safe_to_cleanup
    monkeypatch.setattr(
        "mediatrack_forge.infrastructure.ffmpeg_process.shutil.which", lambda _: None
    )
    with pytest.raises(ExecutionFailure, match="MISSING_EXECUTABLE"):
        discover_ffmpeg(None)


@pytest.mark.parametrize("channel", ["stdout", "stderr"])
def test_diagnostics_are_bounded_without_deadlock(channel: str) -> None:
    result = FFmpegProcessRunner().run(
        (
            sys.executable,
            "-c",
            f"import sys; sys.{channel}.write('x'*1000000); sys.{channel}.flush()",
        ),
        10,
    )
    assert result.error_code == "PROCESS_OUTPUT_LIMIT" and result.safe_to_cleanup
    assert result.stdout_bytes <= CAPTURE_LIMIT and result.stderr_bytes <= CAPTURE_LIMIT


def test_nonzero_exit_does_not_expose_raw_metadata() -> None:
    result = FFmpegProcessRunner().run(
        (sys.executable, "-c", "import sys; print('private path',file=sys.stderr); sys.exit(7)"), 10
    )
    assert result.return_code == 7 and result.error_code == "FFMPEG_FAILED"
    assert result.stderr_bytes > 0 and "private path" not in repr(result)


def test_timeout_stops_parent_and_ordinary_child_writers(tmp_path: Path) -> None:
    marker = tmp_path / "child-heartbeat"
    child = tmp_path / "child.py"
    child.write_text(
        "import time,sys\nfrom pathlib import Path\np=Path(sys.argv[1])\n"
        "while True:\n p.write_text(str(time.time_ns()))\n time.sleep(0.03)\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess,sys,time\n"
        "time.sleep(0.2)\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    result = FFmpegProcessRunner().run((sys.executable, str(parent), str(child), str(marker)), 1.5)
    assert result.error_code == "PROCESS_TIMEOUT" and result.safe_to_cleanup
    assert marker.exists(), "Child must actually run before its termination is tested"
    before = marker.read_bytes()
    time.sleep(0.15)
    assert marker.read_bytes() == before
